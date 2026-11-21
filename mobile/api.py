from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import InvalidOperation
from hashlib import sha256
import hmac
from itertools import groupby
import json
from math import cos, radians
import os
import re
from statistics import median
from pathlib import Path
import secrets
import shutil
from tempfile import TemporaryDirectory, mkdtemp
from threading import Event, Thread
from time import time
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool

import geolocalizar
from validat3b import barcodes, load_env, make_client

from .catalogos import CADENAS, OTRA, cargar_productos, centavos, codigo_busqueda, normalizar
from .db import ROOT, all_dicts, conectar, inicializar
from .evidencia import distancia_m, normalizar_foto
from .worker import consumir


COOKIE = "validat3b_sesion"
SESION_SEGUNDOS = 7 * 24 * 3600
RADIO_METROS = 300  # sucursales que se listan para elegir; verificar usa la regla de geolocalizar.py
UNIDADES = {"gramo": ("kg", 1000), "mililitro": ("L", 1000), "pieza": ("pieza", 1)}
RANGO_TAMANO = (0.4, 2.5)  # otras presentaciones: entre 0.4 y 2.5 veces el contenido del producto
MAX_FILAS_NIVEL = 6
RADIO_PRECIOS_METROS = 3000
ARCHIVOS = {"producto": "product.jpg", "etiqueta": "shelf.jpg"}
WEB = ROOT / "mobile/web/dist"


class Posicion(BaseModel):
    lat: float = Field(ge=-90, le=90, allow_inf_nan=False)
    lon: float = Field(ge=-180, le=180, allow_inf_nan=False)
    precision_m: float = Field(ge=0, le=100000, allow_inf_nan=False)
    medida_en: float = Field(gt=0, allow_inf_nan=False)


class VisitaNueva(BaseModel):
    sucursal_id: str | None = Field(default=None, max_length=96)
    cadena: str | None = Field(default=None, max_length=96)
    nombre: str | None = Field(default=None, max_length=160)
    posicion: Posicion | None = None


class SesionNueva(BaseModel):
    clave: str = Field(min_length=1, max_length=180)


class CapturaNueva(BaseModel):
    id: UUID
    visita_id: UUID
    sku: str | None = Field(default=None, max_length=64)
    codigo: str = Field(pattern=r"^[0-9]{8,14}$")
    precio: str = Field(pattern=r"^[0-9]{1,6}(?:\.[0-9]{1,2})?$")
    capturada_en: float = Field(gt=0, allow_inf_nan=False)


class RevisionNueva(BaseModel):
    decision: Literal["aprobada", "rechazada"]
    motivo: str = Field(min_length=3, max_length=500)


def limites_geograficos(lat, lon, radio):
    dlat = radio / 111_000
    dlon = radio / (111_000 * max(0.01, cos(radians(lat))))
    return lat + dlat, lat - dlat, lon + dlon, lon - dlon


def candidatas(db, p):
    resultados = all_dicts(db.execute(
        """SELECT s.id, s.cadena, s.nombre, s.direccion, s.municipio, s.estado, s.fuente, s.lat, s.lon
           FROM sucursales_geo g JOIN sucursales s ON s.rowid=g.rowid
           WHERE g.lat_min <= ? AND g.lat_max >= ? AND g.lon_min <= ? AND g.lon_max >= ? AND s.cadena != ?""",
        (*limites_geograficos(p.lat, p.lon, RADIO_METROS), OTRA),
    ))
    cercanas = []
    for item in resultados:
        distancia = distancia_m(p.lat, p.lon, item.pop("lat"), item.pop("lon"))
        if distancia <= RADIO_METROS:
            item["distancia_m"] = round(distancia, 1)
            cercanas.append(item)
    cercanas.sort(key=lambda item: (item["distancia_m"], item["id"]))
    # Una misma tienda puede existir en ambas fuentes. QQP cubre zonas sin resultados DENUE.
    denue = [item for item in cercanas if item["fuente"] == "INEGI DENUE"]
    return (denue or cercanas)[:3]


def tiendas_denue(db, lat, lon, radio):
    """Tiendas DENUE alrededor del punto, incluidas las de OTRA cadena, para geolocalizar.contrastar."""
    return all_dicts(db.execute(
        """SELECT s.id, s.cadena, s.nombre, s.direccion, s.lat, s.lon
           FROM sucursales_geo g JOIN sucursales s ON s.rowid=g.rowid
           WHERE g.lat_min <= ? AND g.lat_max >= ? AND g.lon_min <= ? AND g.lon_max >= ? AND s.fuente = 'INEGI DENUE'""",
        limites_geograficos(lat, lon, radio),
    ))


def sugerida(db, p, ahora):
    """Sucursal que la ubicación del teléfono deja verificada: la más cercana, si es de una cadena soportada, está a
    100 m o menos y geolocalizar.contrastar no la ve ambigua (misma regla que el motor para la fachada)."""
    if not -60 <= ahora - p.medida_en <= 120:
        return None
    tiendas = tiendas_denue(db, p.lat, p.lon, geolocalizar.RADIO_M)
    if not tiendas:
        return None
    cercana = min(tiendas, key=lambda t: distancia_m(p.lat, p.lon, t["lat"], t["lon"]))
    if cercana["cadena"] == OTRA:
        return None
    geo = geolocalizar.contrastar((p.lat, p.lon), cercana["cadena"], tiendas, p.precision_m)
    if geo["estado"] != "coincide" or geo["ambigua"] or geo["tienda"]["distancia_m"] > 100:
        return None
    return geo["tienda"]["id"]


def foto_en_sucursal(db, foto, visita):
    """La foto (GPS y precisión del EXIF) se tomó en la sucursal de la visita y no frente a otra tienda."""
    (lat, lon), precision = foto
    # 250 m: una foto dentro de una tienda grande puede quedar lejos del punto DENUE
    geo = geolocalizar.contrastar((lat, lon), visita["cadena"], tiendas_denue(db, lat, lon, 250), precision, radio=250)
    return geo["estado"] == "coincide" and not geo["ambigua"] and geo["tienda"]["id"] == visita["sucursal_id"]


def captura_publica(item):
    return dict(id=item["id"], estado=item["estado"], resultado=json.loads(item["resultado"] or "null"),
                revision=json.loads(item["revision"] or "null"), visita_id=item["visita_id"],
                sku=item["sku"], precio_centavos=item["precio_centavos"], creada=item["creada"])


def referencia_qqp(db, sku, sucursal_id, fecha):
    fila = db.execute(
        """SELECT p.producto, p.marca, p.presentacion, p.precio_centavos, p.fecha, p.archivo,
                  s.nombre AS sucursal, s.direccion FROM equivalencias_qqp e
           JOIN precios_qqp p USING (producto, marca, presentacion)
           JOIN sucursales s ON s.id=p.sucursal_id
           WHERE e.sku=? AND p.fecha<=? AND (p.sucursal_id=? OR p.sucursal_id IN
              (SELECT qqp_id FROM enlaces_qqp WHERE denue_id=?))
           ORDER BY p.fecha DESC, p.precio_centavos LIMIT 2""", (sku, fecha, sucursal_id, sucursal_id),
    ).fetchall()
    if not fila or (len(fila) == 2 and fila[0]["fecha"] == fila[1]["fecha"]
                    and (fila[0]["precio_centavos"], fila[0]["sucursal"]) !=
                        (fila[1]["precio_centavos"], fila[1]["sucursal"])):
        return None
    return dict(fila[0])


def contenido(presentacion, unidad):
    """Contenido en g, ml o piezas leído de una presentación QQP ("Botella 1.5 Lt.", "Paquete C/12"), o None."""
    texto = presentacion.lower()
    if unidad == "pieza":
        m = re.search(r"c/\s*(\d+)|(\d+)\s*(?:piezas|pzas|pz|hojas)\b", texto)
        return float(m.group(1) or m.group(2)) if m else None
    patron = {"gramo": r"(\d+(?:[.,]\d+)?)\s*(kg|gr|g)\b", "mililitro": r"(\d+(?:[.,]\d+)?)\s*(lt|l|ml)\b"}.get(unidad)
    m = patron and re.search(patron, texto)
    if not m:
        return None
    numero, medida = m.groups()
    if medida in ("gr", "g", "ml") and re.fullmatch(r"\d+\.\d{3}", numero):
        numero = numero.replace(".", "")  # "3.564 Gr." son 3564 g: punto de miles
    valor = float(numero.replace(",", "."))
    return valor * 1000 if medida in ("kg", "lt", "l") else valor


def unidad_comparable(datos):
    """('kg' | 'L' | 'pieza', factor de precio de empaque a precio por unidad, contenido). Usa el peso
    total si el nombre lo trae ("Atún 90g (total: 130g)"), porque QQP publica el peso total de la lata."""
    etiqueta, base = UNIDADES.get(datos.get("unit_product"), (None, 0))
    total = re.search(r"\(total:\s*(\d+(?:\.\d+)?)\s*(?:g|ml)\)", str(datos.get("product_name", "")).lower())
    cantidad = float(total.group(1)) if total else float(datos.get("unit_quantity_product") or 0)
    return (etiqueta, base / cantidad, cantidad) if etiqueta and cantidad > 0 else (None, None, None)


def cumple(filtro, texto):
    """Filtro de variante sobre marca + presentación: palabras obligatorias, -palabra excluida, _ une frases."""
    texto = normalizar(texto)
    for palabra in filtro.split():
        if palabra.startswith("-") == (normalizar(palabra.lstrip("-").replace("_", " ")) in texto):
            return False
    return True


def ultimos_precios(db, estado, municipio, condicion, params):
    """Precio más reciente de cada tienda Profeco de la alcaldía o municipio, por marca y presentación."""
    filas = db.execute(
        f"""SELECT s.id, s.cadena, p.marca, p.presentacion, p.precio_centavos, p.fecha
            FROM precios_qqp p JOIN sucursales s ON s.id=p.sucursal_id
            WHERE s.estado=? AND s.municipio=? AND {condicion} ORDER BY p.fecha, p.precio_centavos""",
        (estado, municipio, *params),
    ).fetchall()
    return list({(f["id"], f["marca"], f["presentacion"]): dict(f) for f in filas}.values())


def agrupar(filas, campos):
    grupos = {}
    for f in filas:
        grupos.setdefault(tuple(f[c] for c in campos), []).append(f)
    return [{**dict(zip(campos, llave)), "mediana_centavos": round(median(t["precio_centavos"] for t in tiendas)),
             "tiendas": len(tiendas), "fecha": max(t["fecha"] for t in tiendas)} for llave, tiendas in grupos.items()]


def por_cadena(db, estado, municipio, condicion, params):
    """Por cadena, mediana del precio más reciente de cada tienda de la zona, de la más barata a la más cara."""
    exactas = ultimos_precios(db, estado, municipio, condicion, params)
    por_tienda = {f["id"]: f for f in sorted(exactas, key=lambda f: f["fecha"])}
    return sorted(agrupar(por_tienda.values(), ("cadena",)), key=lambda r: (r["mediana_centavos"], r["cadena"]))


def ranking_cadenas(db, estado, municipio):
    """Qué tan cara sale cada cadena de la zona: en cada producto exacto que venden al menos dos cadenas,
    el % sobre la cadena más barata; luego el promedio por cadena."""
    sobre, baratas, productos, fecha = {}, {}, 0, ""
    for e in db.execute("SELECT DISTINCT producto, marca, presentacion FROM equivalencias_qqp").fetchall():
        filas = por_cadena(db, estado, municipio, "p.producto=? AND p.marca=? AND p.presentacion=?", tuple(e))
        if len(filas) < 2:
            continue
        productos += 1
        minimo = filas[0]["mediana_centavos"]
        for f in filas:
            sobre.setdefault(f["cadena"], []).append(f["mediana_centavos"] / minimo - 1)
            baratas[f["cadena"]] = baratas.get(f["cadena"], 0) + (f["mediana_centavos"] == minimo)
            fecha = max(fecha, f["fecha"])
    cadenas = [{"cadena": c, "sobre_mas_barata_pct": round(100 * sum(v) / len(v), 1), "productos": len(v),
                "mas_barata": baratas[c]} for c, v in sobre.items()]
    return {"productos": productos, "fecha": fecha or None,
            "cadenas": sorted(cadenas, key=lambda r: (r["sobre_mas_barata_pct"], r["cadena"]))}


def comparar_qqp(db, sku, estado, municipio):
    """Precios Profeco en la zona en tres niveles: el mismo producto por cadena, la misma marca en otra
    presentación y otras marcas del mismo tipo; los dos últimos por precio unitario."""
    resultado = {"exacto": por_cadena(db, estado, municipio, "(p.producto, p.marca, p.presentacion) IN "
                                      "(SELECT producto, marca, presentacion FROM equivalencias_qqp WHERE sku=?)", (sku,)),
                 "presentaciones": [], "alternativas": []}
    familia = db.execute("SELECT producto, marca, filtro FROM familias_qqp WHERE sku=?", (sku,)).fetchone()
    producto = db.execute("SELECT datos FROM productos WHERE sku=?", (sku,)).fetchone()
    datos = json.loads(producto["datos"]) if producto else {}
    unidad, _, cantidad = unidad_comparable(datos)
    if not familia or not unidad:
        return resultado
    base = UNIDADES[datos["unit_product"]][1]
    exactos = {(e["marca"], e["presentacion"]) for e in
               db.execute("SELECT marca, presentacion FROM equivalencias_qqp WHERE sku=?", (sku,))}
    otras = []
    for f in ultimos_precios(db, estado, municipio, "p.producto=?", (familia["producto"],)):
        c = contenido(f["presentacion"], datos["unit_product"])
        if ((f["marca"], f["presentacion"]) not in exactos and c and RANGO_TAMANO[0] <= c / cantidad <= RANGO_TAMANO[1]
                and cumple(familia["filtro"], f"{f['marca']} {f['presentacion']}")):
            otras.append({**f, "contenido": c})
    for fila in agrupar(otras, ("marca", "presentacion", "cadena", "contenido")):
        fila["por_unidad_centavos"] = round(fila["mediana_centavos"] * base / fila.pop("contenido"))
        nivel = "presentaciones" if familia["marca"] and fila["marca"] == familia["marca"] else "alternativas"
        resultado[nivel].append(fila)
    for nivel in ("presentaciones", "alternativas"):
        resultado[nivel] = sorted(resultado[nivel], key=lambda r: (r["por_unidad_centavos"], r["marca"],
                                                                     r["cadena"]))[:MAX_FILAS_NIVEL]
    return resultado
def precios_qqp_cercanos(db, sku, sucursal_id, fecha, lat, lon):
    filas = all_dicts(db.execute(
        """SELECT s.id, s.cadena, s.nombre AS sucursal, s.direccion, s.municipio, s.lat, s.lon,
                  p.presentacion, p.precio_centavos, p.fecha, p.archivo
           FROM equivalencias_qqp e JOIN precios_qqp p USING (producto, marca, presentacion)
           JOIN sucursales s ON s.id=p.sucursal_id JOIN sucursales_geo g ON g.rowid=s.rowid
           WHERE e.sku=? AND p.fecha<=? AND s.id IS NOT ?
             AND s.id NOT IN (SELECT qqp_id FROM enlaces_qqp WHERE denue_id=?)
             AND g.lat_min<=? AND g.lat_max>=? AND g.lon_min<=? AND g.lon_max>=?
           ORDER BY s.id, p.fecha DESC, p.precio_centavos, p.presentacion""",
        (sku, fecha, sucursal_id, sucursal_id, *limites_geograficos(lat, lon, RADIO_PRECIOS_METROS)),
    ))
    cercanos = []
    for _, observaciones in groupby(filas, key=lambda fila: fila["id"]):
        reciente = next(observaciones)
        if any(otra["fecha"] == reciente["fecha"] and otra["precio_centavos"] != reciente["precio_centavos"]
               for otra in observaciones):
            continue
        distancia = distancia_m(lat, lon, reciente.pop("lat"), reciente.pop("lon"))
        if distancia <= RADIO_PRECIOS_METROS:
            reciente["distancia_m"] = round(distancia)
            cercanos.append(reciente)
    return sorted(cercanos, key=lambda fila: (fila["distancia_m"], fila["id"]))[:5]


def create_app(state_dir=None, *, local=False, operator_key=None, reviewer_key=None):
    load_env()
    state = Path(state_dir or os.getenv("MOBILE_STATE_DIR") or ROOT / "out/mobile")
    path = state / "campo.sqlite"
    fotos = state / "evidencias"
    roles = {"operador": operator_key or os.getenv("MOBILE_OPERATOR_KEY"),
             "revisor": reviewer_key or os.getenv("MOBILE_REVIEW_KEY")}
    if not roles["operador"] or roles["operador"] == roles["revisor"]:
        raise ValueError("Configura una clave de operador y una clave de revisor distinta para la red.")

    @asynccontextmanager
    async def lifespan(_app):
        inicializar(path)
        fotos.mkdir(exist_ok=True, mode=0o700)
        with conectar(path) as db:
            catalogo = ROOT / "data/catalogo_productos.csv"
            if catalogo.exists() and not db.execute("SELECT 1 FROM productos LIMIT 1").fetchone():
                cargar_productos(db, catalogo)
        client = None if local else make_client()
        if client:
            client = client.with_options(max_retries=0, timeout=25)
        stop = Event()
        thread = Thread(target=consumir, args=(path, fotos, client, stop), daemon=True, name="validat3b-worker")
        thread.start()
        _app.state.foundry = client is not None
        try:
            yield
        finally:
            stop.set()
            await run_in_threadpool(thread.join, 3)

    app = FastAPI(title="Validat3B Campo", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.middleware("http")
    async def cabeceras(request, call_next):
        if request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            if request.method in {"POST", "PUT", "DELETE"} and origin and origin != str(request.base_url).rstrip("/"):
                return Response(status_code=403)
            length = request.headers.get("content-length")
            if length and length.isdecimal() and int(length) > 25 * 1024 * 1024:
                return Response(status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def rol(request: Request):
        token = request.cookies.get(COOKIE, "")
        if token:
            with conectar(path) as db:
                item = db.execute("SELECT rol FROM sesiones WHERE token_hash=? AND vence>?",
                                  (sha256(token.encode()).hexdigest(), time())).fetchone()
            if item:
                return item["rol"]
        raise HTTPException(401, "Inicia sesión para continuar.")

    def operador(actor=Depends(rol)):
        if actor != "operador":
            raise HTTPException(403, "Esta acción requiere la clave de operador.")
        return actor

    def revisor(actor=Depends(rol)):
        if actor != "revisor":
            raise HTTPException(403, "Esta acción requiere la clave de revisión.")
        return actor

    @app.get("/api/salud")
    def salud():
        return {"ok": True}

    @app.post("/api/sesion")
    def iniciar(body: SesionNueva, request: Request, response: Response):
        actor = next((name for name, secret in roles.items()
                      if secret and hmac.compare_digest(body.clave.encode(), secret.encode())), None)
        if not actor:
            raise HTTPException(401, "La clave no es válida.")
        token = secrets.token_urlsafe(32)
        with conectar(path) as db:
            db.execute("DELETE FROM sesiones WHERE vence<=?", (time(),))
            db.execute("INSERT INTO sesiones VALUES (?, ?, ?)",
                       (sha256(token.encode()).hexdigest(), actor, time() + SESION_SEGUNDOS))
        response.set_cookie(COOKIE, token, max_age=SESION_SEGUNDOS, httponly=True, samesite="strict",
                            secure=request.url.scheme == "https")
        return {"rol": actor}

    @app.get("/api/sesion")
    def sesion(actor=Depends(rol)):
        return {"rol": actor}

    @app.delete("/api/sesion")
    def cerrar(request: Request, response: Response):
        token = request.cookies.get(COOKIE, "")
        if token:
            with conectar(path) as db:
                db.execute("DELETE FROM sesiones WHERE token_hash=?", (sha256(token.encode()).hexdigest(),))
        response.delete_cookie(COOKIE)
        return {"ok": True}

    @app.get("/api/config")
    def config(_=Depends(rol)):
        with conectar(path) as db:
            fuentes = dict(db.execute("SELECT fuente, count(*) FROM sucursales GROUP BY fuente").fetchall())
        return {"cadenas": CADENAS, "fuentes": fuentes, "foundry": app.state.foundry}

    @app.post("/api/sucursales/cercanas")
    def cercanas(posicion: Posicion, _=Depends(operador)):
        with conectar(path) as db:
            opciones = candidatas(db, posicion)
            return {"candidatas": opciones, "sugerida_id": sugerida(db, posicion, time())}

    @app.get("/api/sucursales")
    def buscar_sucursales(q: str = Query(min_length=2, max_length=120), _=Depends(rol)):
        palabras = normalizar(q).split()[:8]
        if not palabras:
            return []
        where = " AND ".join("busqueda LIKE ?" for _ in palabras)
        with conectar(path) as db:
            return all_dicts(db.execute(
                f"""SELECT id, cadena, nombre, direccion, municipio, estado, fuente FROM sucursales
                    WHERE {where} AND cadena != ? ORDER BY fuente, estado, municipio, nombre LIMIT 25""",
                (*(f"%{word}%" for word in palabras), OTRA),
            ))

    @app.post("/api/visitas", status_code=201)
    def visita(body: VisitaNueva, _=Depends(operador)):
        ahora, id_visita = time(), str(uuid4())
        ubicacion, p = "manual", body.posicion
        with conectar(path) as db:
            if body.sucursal_id:
                item = db.execute("SELECT * FROM sucursales WHERE id=?", (body.sucursal_id,)).fetchone()
                if not item or item["cadena"] == OTRA:
                    raise HTTPException(404, "No encontramos esa sucursal.")
                cadena, nombre = item["cadena"], item["nombre"]
                if p and sugerida(db, p, ahora) == item["id"]:
                    ubicacion = "verificada"
            else:
                cadena, nombre = body.cadena, (body.nombre or "").strip()
                if cadena not in CADENAS or len(nombre) < 3:
                    raise HTTPException(422, "Elige la cadena y escribe la dirección o el nombre de la sucursal.")
            db.execute("INSERT INTO visitas VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       (id_visita, body.sucursal_id, cadena, nombre, ubicacion, p.lat if p else None,
                        p.lon if p else None, p.precision_m if p else None, p.medida_en if p else None, ahora))
        return {"id": id_visita, "cadena": cadena, "nombre": nombre, "ubicacion": ubicacion}

    @app.get("/api/productos")
    def productos(codigo: str | None = Query(default=None, pattern=r"^[0-9]{8,14}$"),
                  q: str = Query(default="", max_length=100), _=Depends(rol)):
        with conectar(path) as db:
            if codigo:
                filas = db.execute("SELECT datos FROM productos WHERE codigo_busqueda=?", (codigo_busqueda(codigo),))
            else:
                filas = db.execute("SELECT datos FROM productos ORDER BY sku")
            resultados = [json.loads(item["datos"]) for item in filas]
        if not codigo:
            palabras = normalizar(q).split()
            resultados = [p for p in resultados if all(w in normalizar(p["product_name"]) for w in palabras)]
            if not palabras:
                return []
        return resultados[:20]

    @app.post("/api/codigos/leer")
    def leer_codigo(foto: Annotated[UploadFile, File()], _=Depends(operador)):
        try:
            normalizada, _, _ = normalizar_foto(foto.file)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        with TemporaryDirectory() as folder:
            imagen = Path(folder) / "codigo.jpg"
            imagen.write_bytes(normalizada)
            return {"codigos": sorted(barcodes(imagen))}

    @app.get("/api/precios/qqp")
    def precios_qqp(sku: str, visita_id: UUID, _=Depends(operador)):
        with conectar(path) as db:
            item = db.execute("SELECT sucursal_id FROM visitas WHERE id=?", (str(visita_id),)).fetchone()
            if not item:
                raise HTTPException(404, "Visita no encontrada.")
            return referencia_qqp(db, sku, item["sucursal_id"], datetime.now(timezone.utc).date().isoformat())

    @app.get("/api/precios/comparar")
    def precios_comparar(sku: str = Query(max_length=64), estado: str = Query(max_length=96),
                         municipio: str = Query(max_length=96), _=Depends(rol)):
        with conectar(path) as db:
            if not db.execute("SELECT 1 FROM sucursales WHERE fuente='Profeco QQP' AND estado=? AND municipio=?",
                              (estado, municipio)).fetchone():
                raise HTTPException(404, "Profeco no tiene tiendas registradas en esa zona.")
            producto = db.execute("SELECT datos FROM productos WHERE sku=?", (sku,)).fetchone()
            if not producto:
                raise HTTPException(404, "Producto no encontrado en el catálogo.")
            unidad, factor, _ = unidad_comparable(json.loads(producto["datos"]))
            niveles = comparar_qqp(db, sku, estado, municipio)
        return {"zona": {"estado": estado, "municipio": municipio}, "unidad": unidad, "factor": factor, **niveles}

    @app.get("/api/precios/cadenas")
    def precios_cadenas(estado: str = Query(max_length=96), municipio: str = Query(max_length=96), _=Depends(rol)):
        with conectar(path) as db:
            return ranking_cadenas(db, estado, municipio)

    @app.get("/api/zonas")
    def zonas(_=Depends(rol)):
        """Alcaldías o municipios con tiendas Profeco que tienen precios cargados."""
        with conectar(path) as db:
            return all_dicts(db.execute(
                """SELECT s.estado, s.municipio, count(*) AS tiendas, group_concat(DISTINCT s.cadena) AS cadenas
                   FROM sucursales s WHERE s.fuente='Profeco QQP'
                   AND EXISTS (SELECT 1 FROM precios_qqp p WHERE p.sucursal_id=s.id)
                   GROUP BY s.estado, s.municipio ORDER BY s.estado, s.municipio"""))
    @app.get("/api/precios/qqp/comparacion")
    def comparar_precios_qqp(visita_id: UUID, sku: str = Query(min_length=1, max_length=64), _=Depends(operador)):
        with conectar(path) as db:
            visita = db.execute(
                """SELECT v.sucursal_id, COALESCE(s.lat,v.lat) AS lat, COALESCE(s.lon,v.lon) AS lon
                   FROM visitas v LEFT JOIN sucursales s ON s.id=v.sucursal_id WHERE v.id=?""",
                (str(visita_id),),
            ).fetchone()
            if not visita:
                raise HTTPException(404, "Visita no encontrada.")
            resultado = {"referencia": None, "cercanos": [], "radio_m": RADIO_PRECIOS_METROS, "estado": "ok"}
            if not db.execute("SELECT 1 FROM equivalencias_qqp WHERE sku=? LIMIT 1", (sku,)).fetchone():
                return {**resultado, "estado": "sin_equivalencia"}
            if visita["lat"] is None or visita["lon"] is None:
                return {**resultado, "estado": "sin_ubicacion"}
            fecha = datetime.now(timezone.utc).date().isoformat()
            resultado["referencia"] = referencia_qqp(db, sku, visita["sucursal_id"], fecha)
            resultado["cercanos"] = precios_qqp_cercanos(
                db, sku, visita["sucursal_id"], fecha, visita["lat"], visita["lon"],
            )
            return resultado

    @app.post("/api/capturas", status_code=202)
    def registrar(datos: Annotated[str, Form(max_length=4096)], producto: Annotated[UploadFile, File()],
                  etiqueta: Annotated[UploadFile, File()], _=Depends(operador)):
        try:
            body = CapturaNueva.model_validate_json(datos)
            precio = centavos(body.precio)
        except (ValidationError, ValueError, InvalidOperation) as error:
            raise HTTPException(422, "Verifica el código, el SKU seleccionado y el precio en pesos.") from error
        id_captura = str(body.id)
        with conectar(path) as db:
            v = db.execute("""SELECT v.*, s.lat AS tienda_lat, s.lon AS tienda_lon
                              FROM visitas v LEFT JOIN sucursales s ON s.id=v.sucursal_id WHERE v.id=?""",
                           (str(body.visita_id),)).fetchone()
            if body.sku:
                p = db.execute("SELECT sku, datos FROM productos WHERE sku=?", (body.sku,)).fetchone()
            else:
                p = db.execute("SELECT sku, datos FROM productos WHERE codigo_busqueda=?",
                               (codigo_busqueda(body.codigo),)).fetchone()
        if not v:
            raise HTTPException(404, "Selecciona la tienda antes de enviar la captura.")
        if body.sku and not p:
            raise HTTPException(422, "El SKU ya no está disponible en el catálogo.")
        if not v["creada"] - 300 <= body.capturada_en <= time() + 300:
            raise HTTPException(422, "La hora de captura no corresponde a la visita. Revisa la hora del teléfono.")
        try:
            img_producto, hash_producto, gps_producto = normalizar_foto(producto.file)
            img_etiqueta, hash_etiqueta, gps_etiqueta = normalizar_foto(etiqueta.file)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        huella = sha256(json.dumps([str(body.visita_id), body.sku, body.codigo, precio, hash_producto, hash_etiqueta])
                        .encode()).hexdigest()
        verificada = v["ubicacion"] == "verificada" and body.capturada_en - v["creada"] <= 4 * 3600
        if verificada and (ubicaciones_fotos := [gps for gps in (gps_producto, gps_etiqueta) if gps]):
            with conectar(path) as db:
                verificada = all(foto_en_sucursal(db, gps, v) for gps in ubicaciones_fotos)
        cap = json.loads(p["datos"]) if p else {}
        cap.update(capture_id=id_captura, capture_store_name=v["cadena"],
                   capture_date=datetime.fromtimestamp(body.capturada_en, timezone.utc).isoformat(),
                   capture_price=precio / 100, capture_barcode=body.codigo,
                   product_file=ARCHIVOS["producto"], shelf_file=ARCHIVOS["etiqueta"],
                   sucursal_verificada=verificada)
        carpeta = None
        try:
            with conectar(path) as db:
                db.execute("BEGIN IMMEDIATE")
                anterior = db.execute("SELECT * FROM capturas WHERE id=?", (id_captura,)).fetchone()
                if anterior:
                    if anterior["huella"] != huella:
                        raise HTTPException(409, "El identificador ya corresponde a una captura distinta.")
                    return captura_publica(anterior)
                carpeta = Path(mkdtemp(prefix="captura-", dir=fotos))
                (carpeta / ARCHIVOS["producto"]).write_bytes(img_producto)
                (carpeta / ARCHIVOS["etiqueta"]).write_bytes(img_etiqueta)
                db.execute(
                    """INSERT INTO capturas (id, visita_id, sku, creada, precio_centavos, datos, evidencia,
                                              huella, disponible) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (id_captura, str(body.visita_id), p["sku"] if p else None, body.capturada_en, precio,
                     json.dumps(cap, ensure_ascii=False), carpeta.name, huella, time()),
                )
                fila = db.execute("SELECT * FROM capturas WHERE id=?", (id_captura,)).fetchone()
        except Exception:
            if carpeta:
                shutil.rmtree(carpeta, ignore_errors=True)
            raise
        return captura_publica(fila)

    @app.get("/api/capturas/{id_captura}")
    def consultar(id_captura: UUID, _=Depends(rol)):
        with conectar(path) as db:
            item = db.execute("SELECT * FROM capturas WHERE id=?", (str(id_captura),)).fetchone()
        if not item:
            raise HTTPException(404, "Captura no encontrada.")
        return captura_publica(item)

    @app.get("/api/revision")
    def bandeja(_=Depends(revisor)):
        with conectar(path) as db:
            items = db.execute(
                """SELECT c.*, v.cadena, v.nombre FROM capturas c JOIN visitas v ON v.id=c.visita_id
                   WHERE c.estado='procesada' AND c.revision IS NULL
                   AND json_extract(c.resultado, '$.decision')='revision_manual'
                   ORDER BY c.creada DESC LIMIT 50""",
            ).fetchall()
        return [{**captura_publica(item), "cadena": item["cadena"], "sucursal": item["nombre"]} for item in items]

    @app.get("/api/comparativo")
    def comparativo(_=Depends(revisor)):
        # Analista vs versiones del motor, por captura. Trae datos de 3B: solo con clave de revisión y solo el archivo
        # local que genera comparativo.py (out/ está fuera de git); al repo público va únicamente resultados/resumen.json.
        archivo = ROOT / "out/comparativo.json"
        if not archivo.is_file():
            raise HTTPException(404, "Aún no hay comparativo. Genera out/comparativo.json con comparativo.py.")
        return FileResponse(archivo, media_type="application/json")

    @app.get("/api/capturas/{id_captura}/foto/{tipo}")
    def ver_foto(id_captura: UUID, tipo: Literal["producto", "etiqueta"], _=Depends(revisor)):
        with conectar(path) as db:
            item = db.execute("SELECT evidencia FROM capturas WHERE id=?", (str(id_captura),)).fetchone()
        if not item:
            raise HTTPException(404, "Captura no encontrada.")
        return FileResponse(fotos / item["evidencia"] / ARCHIVOS[tipo], media_type="image/jpeg")

    @app.post("/api/capturas/{id_captura}/revision")
    def revisar(id_captura: UUID, body: RevisionNueva, _=Depends(revisor)):
        if len(body.motivo.strip()) < 3:
            raise HTTPException(422, "Describe el motivo de la revisión.")
        decision = {"decision": body.decision, "motivo": body.motivo.strip(), "fecha": time(), "rol": "revisor"}
        with conectar(path) as db:
            resultado = db.execute(
                """UPDATE capturas SET revision=? WHERE id=? AND revision IS NULL AND estado='procesada'
                   AND json_extract(resultado, '$.decision')='revision_manual'""",
                (json.dumps(decision, ensure_ascii=False), str(id_captura)),
            )
        if resultado.rowcount != 1:
            raise HTTPException(409, "La captura ya no está pendiente de revisión.")
        return decision

    if WEB.is_dir():
        app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")

        @app.get("/", include_in_schema=False)
        @app.get("/revisar", include_in_schema=False)
        @app.get("/comparar", include_in_schema=False)
        @app.get("/corregidos", include_in_schema=False)
        @app.get("/comparativo", include_in_schema=False)
        def pantalla():
            return FileResponse(WEB / "index.html", headers={"Cache-Control": "no-cache"})

        @app.get("/{archivo}", include_in_schema=False)
        def archivo_pwa(archivo: Literal["manifest.webmanifest", "sw.js", "icon.svg"]):
            return FileResponse(WEB / archivo, headers={"Cache-Control": "no-cache"})
    return app
