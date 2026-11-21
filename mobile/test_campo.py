"""Fases del capturista de punta a punta (modo local: sin Foundry ni tokens, fotos sintéticas).

1. Entra como operador  2. Abre la visita  3. Envía producto + etiqueta  4. El worker valida
5. Con etiqueta borrosa: rechazo + hallazgos + qué hacer  6. Vuelve a capturar  7. El revisor ve los hallazgos
"""
from io import BytesIO
from tempfile import TemporaryDirectory
from time import sleep, time
from uuid import uuid4

import cv2
import numpy as np
from fastapi.testclient import TestClient

from mobile.api import create_app
from salida_web import ACCIONES


def jpg(nitida):
    img = np.random.default_rng(7).integers(0, 255, (900, 1200, 3), dtype=np.uint8) if nitida else np.full((900, 1200, 3), 128, np.uint8)
    return BytesIO(cv2.imencode(".jpg", img)[1].tobytes())


def enviar(web, visita, producto, etiqueta, extra=', "codigo": "7501234567890", "precio": "30.00"'):
    datos = f'{{"id": "{uuid4()}", "visita_id": "{visita}"{extra}, "capturada_en": {time()}}}'
    r = web.post("/api/capturas", data={"datos": datos},
                 files={"producto": ("p.jpg", producto, "image/jpeg"), "etiqueta": ("e.jpg", etiqueta, "image/jpeg")})
    assert r.status_code == 202, r.text
    for _ in range(100):  # el worker corre en su hilo; esperamos a que la procese
        c = web.get(f"/api/capturas/{r.json()['id']}").json()
        if c["estado"] == "procesada":
            return c
        sleep(0.2)
    raise AssertionError("el worker no procesó la captura")


with TemporaryDirectory() as estado, TestClient(create_app(estado, local=True, operator_key="op-1", reviewer_key="rev-1")) as web:
    assert web.post("/api/sesion", json={"clave": "op-1"}).status_code == 200                       # 1
    visita = web.post("/api/visitas", json={"cadena": "Soriana", "nombre": "Soriana de prueba"})     # 2
    assert visita.status_code == 201, visita.text
    v = visita.json()["id"]

    c = enviar(web, v, jpg(True), jpg(False))                                                       # 3-4
    r = c["resultado"]
    assert r["decision"] == "rechazada" and r["reason_code"] == "CAPTURA_BORROSA"                    # 5
    assert any(h["fuente"] == "nitidez" and h["nivel"] == "falla" for h in r["hallazgos"])
    assert r["accion_sugerida"] == ACCIONES["CAPTURA_BORROSA"]

    c2 = enviar(web, v, jpg(True), jpg(True))                                                       # 6
    r2 = c2["resultado"]
    assert r2["decision"] == "revision_manual" and r2["hallazgos"] and r2["accion_sugerida"]  # local: sin modelo, a revisión

    c3 = enviar(web, v, jpg(True), jpg(True), extra="")  # solo las dos fotos: sin código ni precio
    assert c3["resultado"]["decision"] == "revision_manual" and c3["precio_centavos"] == 0

    web.delete("/api/sesion")                                                                       # 7
    web.post("/api/sesion", json={"clave": "rev-1"})
    bandeja = web.get("/api/revision").json()
    assert any(x["id"] == c2["id"] and x["resultado"]["hallazgos"] for x in bandeja)
print("ok")
