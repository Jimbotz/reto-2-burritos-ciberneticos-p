import json
import logging
from time import time

from anthropic import APIConnectionError, InternalServerError, RateLimitError

import salida_web
from validat3b import apply_rules, decide

from .db import conectar


logger = logging.getLogger(__name__)
MAX_INTENTOS = 3
LEASE_SEGUNDOS = 75


def reclamar(path):
    now = time()
    with conectar(path) as db:
        db.execute("BEGIN IMMEDIATE")
        item = db.execute(
            """SELECT * FROM capturas WHERE (estado = 'pendiente' AND disponible <= ?)
                    OR (estado = 'validando' AND lease <= ?) ORDER BY creada LIMIT 1""", (now, now),
        ).fetchone()
        if not item:
            return None, None
        lease = now + LEASE_SEGUNDOS
        db.execute("UPDATE capturas SET estado='validando', lease=?, intentos=intentos+1 WHERE id=?",
                   (lease, item["id"]))
        return item, lease


def procesar_una(path, fotos, client):
    item, lease = reclamar(path)
    if not item:
        return False
    datos = json.loads(item["datos"])
    verificada = datos.pop("sucursal_verificada")
    senales, incompleta = {}, None
    try:
        if item["intentos"] >= MAX_INTENTOS:
            raise RuntimeError("Se agotaron los intentos de validación.")
        resultado, tokens = decide(datos, fotos / item["evidencia"], client, store_verified=verificada, senales=senales)
    except (APIConnectionError, InternalServerError, RateLimitError):
        if item["intentos"] + 1 < MAX_INTENTOS:
            with conectar(path) as db:
                db.execute("""UPDATE capturas SET estado='pendiente', disponible=?, lease=NULL
                              WHERE id=? AND lease=?""", (time() + 4 * (2 ** item["intentos"]), item["id"], lease))
            return True
        incompleta = "El modelo no respondió tras varios intentos."
        resultado, tokens = apply_rules(datos, {"explicacion": "Foundry no respondió tras varios intentos."},
                                        store_verified=verificada), 0
    except Exception as error:
        logger.warning("Captura %s requiere revisión (%s)", item["id"], type(error).__name__)
        incompleta = "La validación automática quedó incompleta."
        resultado, tokens = apply_rules(datos, {"explicacion": "La validación automática quedó incompleta."},
                                        store_verified=verificada), 0
    if not verificada and resultado["decision"] == "revision_manual":
        razon = "La sucursal requiere confirmación con la evidencia disponible."
        resultado["explicacion"] = (resultado["explicacion"] + " " + razon).strip()
    # para el capturista y el revisor: qué se revisó, qué falló y qué hacer (misma lógica que la salida web)
    resultado["hallazgos"] = salida_web.hallazgos(datos, resultado, senales)
    if incompleta:
        resultado["hallazgos"].insert(0, salida_web.h("evidencia", "motor", "aviso", incompleta + " Un analista la revisará."))
    resultado["accion_sugerida"] = salida_web.accion_sugerida(datos, resultado)
    with conectar(path) as db:
        db.execute("""UPDATE capturas SET estado='procesada', resultado=?, tokens=?, lease=NULL
                      WHERE id=? AND lease=?""",
                   (json.dumps(resultado, ensure_ascii=False), tokens, item["id"], lease))
    return True


def consumir(path, fotos, client, stop):
    while not stop.is_set():
        try:
            if procesar_una(path, fotos, client):
                continue
        except Exception as error:
            logger.warning("La cola se reintentará (%s)", type(error).__name__)
        stop.wait(1)
