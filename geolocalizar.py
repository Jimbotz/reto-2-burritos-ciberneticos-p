"""Geolocaliza una foto: GPS del EXIF → sucursal DENUE más cercana → contraste con la cadena declarada.

Es la única regla de "GPS → tienda": la usan validat3b.py (fachada) y la app móvil (sugerir la sucursal de la visita y
verificar las fotos de producto y etiqueta).

Uso:
    python geolocalizar.py data/capturas.json [datasets/denue_autoservicio_462111_462112.csv]
Imprime, por foto de fachada, el estado y la sucursal estimada. validat3b.py usa `ubicar` en cada captura.
"""
import heapq, json, sys
from collections import Counter
from functools import cache
from pathlib import Path

from PIL import Image

import ocr_local
from mobile.catalogos import cadena_de, fichas_denue, filas, normalizar
from mobile.evidencia import distancia_m, gps_exif, precision_exif

DENUE = next(Path(__file__).with_name("datasets").glob("denue_autoservicio_462111_462112*.csv"),
             Path(__file__).with_name("datasets") / "denue_autoservicio_462111_462112.csv")
# Error típico de GPS de teléfono en ciudad (10–50 m) + estacionamiento de una tienda grande.
RADIO_M = 150
MARGEN_M = 25  # diferencia mínima con la segunda sucursal de la cadena (+ 2 × precisión del GPS, si se conoce)
PRECISION_MAX_M = 50  # con más error el GPS no basta para nombrar una sucursal


@cache
def sucursales(path=DENUE):
    with filas(Path(path), "utf-8-sig") as reader:
        return tuple(fichas_denue(reader, ""))


def contrastar(gps, declarada, tiendas, precision_m=None, radio=RADIO_M):
    """Sucursal DENUE más cercana al GPS, prefiriendo la cadena declarada dentro del radio (plazas con varias tiendas).
    tiendas: dicts con id, cadena, nombre, lat, lon (direccion opcional). precision_m: error del GPS, si se conoce."""
    # shortcut: búsqueda lineal (~45 mil tiendas, decenas de ms); la app le pasa solo las del R-tree de mobile/db.py.
    cerca = [dict(t, distancia_m=round(distancia_m(*gps, t["lat"], t["lon"]))) for t in tiendas]
    # 15 y no 5: en ciudad los OXXO del radio podrían dejar fuera a la tienda declarada
    cerca = [t for t in heapq.nsmallest(15, cerca, key=lambda t: t["distancia_m"]) if t["distancia_m"] <= radio]
    if not cerca:
        return {"estado": "sin_sucursal_cercana", "gps": gps}
    propias = [t for t in cerca if t["cadena"] == declarada]
    if not propias:
        return {"estado": "otra_cadena", "gps": gps, "tienda": cerca[0], "candidatas": cerca}
    propia, margen = propias[0], MARGEN_M + 2 * (precision_m or 0)
    # El GPS no basta para elegir si otra tienda está más cerca que la declarada (7-Eleven frente a Tiendas 3B) o si hay
    # otra de la misma cadena casi a la misma distancia (BA Express pegadas). A menos de 30 m entre sí son el mismo
    # local registrado dos veces en DENUE.
    ambigua = (precision_m or 0) > PRECISION_MAX_M or any(
        t["cadena"] != declarada and t["distancia_m"] < propia["distancia_m"] for t in cerca) or any(
        t["distancia_m"] - propia["distancia_m"] < margen
        and distancia_m(t["lat"], t["lon"], propia["lat"], propia["lon"]) > 30 for t in propias[1:])
    return {"estado": "coincide", "gps": gps, "tienda": propia, "ambigua": ambigua, "candidatas": cerca}


# Palabras que no distinguen una sucursal de otra; la cadena se compara aparte con cadena_de.
GENERICAS = set("""super hiper mega express expres sucursal tienda tiendas bodega aurrera ba bae mb mi sc supercenter
    de del la las el los y plaza centro walmart wal mart soriana neto bara chedraui fresko comer precio precios
    suc tres general avenida calle colonia seccion boulevard calzada calz privada cerrada andador carretera""".split())


def palabras(texto):
    # números de un dígito fuera: "07:00 hrs" del horario empataba con el "7" de "7 ELEVEN"
    numeros = {p.lstrip("0") for p in normalizar(texto).split() if p.isdigit()}
    return {n for n in numeros if len(n) >= 2} | {
        p for p in normalizar(texto).split() if not p.isdigit() and len(p) >= 3 and p not in GENERICAS}


def desempatar(geo, declarada, texto):
    """Con varias sucursales en el radio (plaza grande, BA Express pegadas), el texto de la fachada leído por OCR elige
    la que nombra: número de sucursal, colonia o cadena. Si nadie gana claro, deja lo que dijo el GPS."""
    texto = ocr_local.clean(texto)  # quita las cajas <|det|> con coordenadas: sus números no son de la fachada
    leidas, vista = palabras(texto), cadena_de(texto)
    puntos = [(len(palabras(f"{t['nombre']} {t.get('direccion', '')}") & leidas) + (t["cadena"] == vista), t)
              for t in geo["candidatas"]]
    mejor = max(p for p, _ in puntos)
    ganadoras = [t for p, t in puntos if p == mejor]
    if mejor == 0 or len({t["id"] for t in ganadoras}) > 1:
        return geo
    t = ganadoras[0]
    return {**geo, "estado": "coincide" if t["cadena"] == declarada else "otra_cadena", "tienda": t,
            "ambigua": False, "por_ocr": True}


def ubicar(foto, declarada, tiendas=None, ocr=None):
    """ocr: función perezosa que devuelve el texto de la fachada; solo se llama si el GPS quedó ambiguo."""
    try:
        with Image.open(foto) as img:
            gps, precision = gps_exif(img), precision_exif(img)
    except OSError:
        gps = None
    if gps is None:
        return {"estado": "sin_gps"}
    geo = contrastar(gps, declarada, sucursales() if tiendas is None else tiendas, precision)
    if ocr is not None and geo.get("ambigua"):
        geo = desempatar(geo, declarada, ocr())
    return geo


def main(capturas, denue=DENUE):
    caps = json.loads(Path(capturas).read_text())
    base, tiendas, vistas = Path(capturas).parent, sucursales(Path(denue)), {}
    for cap in caps:  # varias capturas comparten la misma foto de fachada
        clave = (cap["facade_file"], cap.get("capture_store_name"))
        if clave not in vistas:
            vistas[clave] = ubicar(base / cap["facade_file"], clave[1], tiendas)
    print(f"{len(tiendas)} tiendas DENUE · {len(vistas)} fachadas distintas")
    print(Counter(g["estado"] for g in vistas.values()))
    for (foto, declarada), g in vistas.items():
        if "tienda" in g:
            t = g["tienda"]
            print(f"{foto}: {g['estado']} · declarada {declarada} · {t['nombre']} ({t['cadena']}, {t['municipio']}) a {t['distancia_m']} m")


if __name__ == "__main__":
    main(*sys.argv[1:3])
