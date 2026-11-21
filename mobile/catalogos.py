"""Carga productos del reto, sucursales DENUE y observaciones públicas QQP."""

import argparse
from contextlib import contextmanager
import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sqlite3
import unicodedata
from zipfile import ZipFile

from .db import ROOT, conectar, inicializar


CADENAS = ("Bodega Aurrera", "Walmart", "Chedraui", "Soriana", "Bara", "Neto", "Tiendas 3B", "La Comer", "H-E-B")
ACTIVIDADES_TIENDA = {"461110", "462111", "462112"}
ALIAS = {
    "Bodega Aurrera": r"\bbodega\s*aurrera\b",
    "Walmart": r"\bwal[ -]?mart\b",
    "Chedraui": r"\bchedraui\b",
    "Soriana": r"\bsoriana\b",
    "Bara": r"\b(?:tiendas? bara|bara sucursal|bara super|bara precios)\b|^bara$",
    "Neto": r"\b(?:tiendas? neto|super neto|neto sucursal|neto super precio)\b|^neto$",
    "Tiendas 3B": r"\b(?:tiendas? (?:3b|tres b)|super (?:3b|tres b))\b",
    "La Comer": r"\b(?:la comer|fresko|city market|sumesa)\b",
    "H-E-B": r"\bh[ .-]?e[ .-]?b\b",
}
ALIAS = {cadena: re.compile(patron) for cadena, patron in ALIAS.items()}


def normalizar(texto):
    nfkd = unicodedata.normalize("NFKD", str(texto or "").casefold())
    ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(re.findall(r"[a-z0-9]+", ascii_text))


def cadena_de(nombre, *otros):
    if re.search(r"\bsuper bara 52[a-z0-9]+\b", normalizar(nombre)):
        return "Bara"
    for texto in (nombre, *otros):
        texto = normalizar(texto)
        for cadena, patron in ALIAS.items():
            if patron.search(texto):
                return cadena
    return None


def codigo_busqueda(codigo):
    return str(codigo).strip().lstrip("0")


def centavos(valor):
    dinero = Decimal(str(valor))
    if not dinero.is_finite() or not 0 < dinero <= 999_999 or dinero != dinero.quantize(Decimal(".01")):
        raise ValueError("Usa un precio en pesos mayor a cero con hasta dos decimales.")
    return int(dinero * 100)


def coords(lat, lon):
    lat, lon = float(lat), float(lon)
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Coordenadas inválidas.")
    return lat, lon


@contextmanager
def filas(path, encoding, *, archivo=None):
    if path.suffix.lower() != ".zip":
        with path.open(encoding=encoding, newline="") as lector:
            yield csv.DictReader(lector)
        return
    with ZipFile(path) as zip_file:
        entradas = [n for n in zip_file.namelist() if n.lower().endswith(".csv")
                    and not Path(n).name.startswith((".", "~"))]
        if archivo is None:
            datos = [n for n in entradas if "/conjunto_de_datos/" in "/" + n.lower()]
            entradas = datos or entradas
            if len(entradas) != 1:
                raise ValueError("Indica --archivo con el nombre del CSV de datos dentro del ZIP.")
            archivo = entradas[0]
        with zip_file.open(archivo) as raw:
            with io.TextIOWrapper(raw, encoding=encoding, newline="") as lector:
                yield csv.DictReader(lector)


def cargar_productos(db, path):
    with filas(path, "utf-8-sig") as reader:
        datos = []
        for p in reader:
            codigo = p["product_barcode"].strip()
            datos.append((p["id_product"], codigo, codigo_busqueda(codigo), json.dumps(p, ensure_ascii=False)))
    db.executemany(
        """INSERT INTO productos VALUES (?, ?, ?, ?)
           ON CONFLICT(sku) DO UPDATE SET codigo=excluded.codigo, codigo_busqueda=excluded.codigo_busqueda,
                                           datos=excluded.datos""", datos,
    )
    return len(datos)


def guardar_sucursal(db, ficha):
    ficha["busqueda"] = normalizar(" ".join(ficha[k] for k in ("cadena", "nombre", "direccion", "municipio", "estado")))
    db.execute(
        """INSERT INTO sucursales (id, clee, cadena, nombre, direccion, municipio, estado, lat, lon,
                                   fuente, edicion, busqueda)
           VALUES (:id, :clee, :cadena, :nombre, :direccion, :municipio, :estado, :lat, :lon,
                   :fuente, :edicion, :busqueda)
           ON CONFLICT(id) DO UPDATE SET clee=excluded.clee, cadena=excluded.cadena, nombre=excluded.nombre,
                direccion=excluded.direccion, municipio=excluded.municipio, estado=excluded.estado,
                lat=excluded.lat, lon=excluded.lon, edicion=excluded.edicion, busqueda=excluded.busqueda""",
        ficha,
    )
    db.execute(
        """INSERT OR REPLACE INTO sucursales_geo
           SELECT rowid, lat, lat, lon, lon FROM sucursales WHERE id = ?""", (ficha["id"],),
    )


def cargar_denue(db, path, encoding, archivo, edicion):
    total = 0
    with filas(path, encoding, archivo=archivo) as reader:
        columnas = {normalizar(k).replace(" ", "_"): k for k in reader.fieldnames or []}
        if not {"id", "nom_estab", "latitud", "longitud"} <= columnas.keys():
            raise ValueError("Se esperaban las columnas DENUE id, nom_estab, latitud y longitud.")
        for row in reader:
            def valor(k):
                return (row.get(columnas.get(k)) or "").strip()

            actividad = valor("codigo_act")
            if actividad and actividad not in ACTIVIDADES_TIENDA:
                continue
            nombre, razon, id_denue = valor("nom_estab"), valor("raz_social"), valor("id")
            cadena = cadena_de(nombre, razon)
            if not cadena or not id_denue:
                continue
            try:
                lat, lon = coords(valor("latitud"), valor("longitud"))
            except (ValueError, TypeError):
                continue
            direccion = ", ".join(filter(None, [
                " ".join(filter(None, (valor("tipo_vial"), valor("nom_vial"), valor("numero_ext")))),
                valor("nomb_asent"), valor("cod_postal"),
            ]))
            guardar_sucursal(db, dict(id=f"denue:{id_denue}", clee=valor("clee"), cadena=cadena,
                                      nombre=nombre or razon, direccion=direccion, municipio=valor("municipio"),
                                      estado=valor("entidad"), lat=lat, lon=lon, fuente="INEGI DENUE", edicion=edicion))
            total += 1
    return total


def cargar_qqp(db, path, encoding, edicion, estados, *, solo_sucursales=False):
    sucursales = set()
    precios = []
    with filas(path, encoding) as reader:
        required = {"producto", "marca", "presentacion", "precio", "fecha_registro", "cadena_comercial",
                    "nombre_comercial", "direccion", "municipio", "estado", "latitud", "longitud"}
        if not required <= set(reader.fieldnames or []):
            raise ValueError("El CSV no contiene las columnas de observaciones de QQP.")
        for row in reader:
            estado = normalizar(row["estado"])
            if estados and estado not in estados:
                continue
            cadena = cadena_de(row["cadena_comercial"], row["nombre_comercial"])
            if not cadena:
                continue
            try:
                lat, lon = coords(row["latitud"], row["longitud"])
                precio = centavos(row["precio"])
                fecha = datetime.strptime(row["fecha_registro"], "%Y/%m/%d").date().isoformat()
            except (ValueError, InvalidOperation, TypeError):
                continue
            identidad = "|".join(normalizar(row[k]) for k in ("nombre_comercial", "direccion", "municipio", "estado"))
            id_qqp = "qqp:" + hashlib.sha256(identidad.encode()).hexdigest()[:24]
            if id_qqp not in sucursales:
                guardar_sucursal(db, dict(id=id_qqp, clee=None, cadena=cadena, nombre=row["nombre_comercial"],
                                          direccion=row["direccion"], municipio=row["municipio"], estado=row["estado"],
                                          lat=lat, lon=lon, fuente="Profeco QQP", edicion=edicion))
                sucursales.add(id_qqp)
            if not solo_sucursales:
                precios.append((row["producto"], row["marca"], row["presentacion"], id_qqp, fecha, precio, edicion))
    db.executemany("INSERT OR IGNORE INTO precios_qqp VALUES (?, ?, ?, ?, ?, ?, ?)", precios)
    return len(sucursales), len(precios)


def cargar_equivalencias(db, path):
    with filas(path, "utf-8-sig") as reader:
        datos = []
        for row in reader:
            sku = row.get("sku")
            if not sku:
                codigo = row["codigo"]
                producto = db.execute("SELECT sku FROM productos WHERE codigo_busqueda=?",
                                      (codigo_busqueda(codigo),)).fetchone()
                if not producto:
                    raise ValueError(f"El código {codigo} no está en el catálogo local de productos.")
                sku = producto["sku"]
            datos.append((sku, row["producto"], row["marca"], row["presentacion"]))
    db.executemany("INSERT OR IGNORE INTO equivalencias_qqp VALUES (?, ?, ?, ?)", datos)
    return len(datos)


def cargar_familias(db, path):
    """sku → tipo de producto, marca y filtro de variante en QQP, para comparar otras presentaciones y marcas."""
    with filas(path, "utf-8-sig") as reader:
        datos = [(r["sku"], r["producto"], r.get("marca") or "", r.get("filtro") or "") for r in reader]
    faltan = [sku for sku, *_ in datos if not db.execute("SELECT 1 FROM productos WHERE sku=?", (sku,)).fetchone()]
    if faltan:
        raise ValueError(f"SKU fuera del catálogo local: {', '.join(faltan)}")
    db.executemany("INSERT OR REPLACE INTO familias_qqp VALUES (?, ?, ?, ?)", datos)
    return len(datos)


def cargar_enlaces(db, path):
    with filas(path, "utf-8-sig") as reader:
        datos = [(r["denue_id"], r["qqp_id"]) for r in reader]
    for denue_id, qqp_id in datos:
        if not denue_id.startswith("denue:") or not qqp_id.startswith("qqp:"):
            raise ValueError("Usa IDs con los prefijos denue: y qqp:.")
    db.executemany("INSERT OR IGNORE INTO enlaces_qqp VALUES (?, ?)", datos)
    return len(datos)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--db", type=Path, default=ROOT / "out/mobile/campo.sqlite")
    origenes = cli.add_mutually_exclusive_group(required=True)
    for origen in ("productos", "denue", "qqp", "equivalencias", "familias", "enlaces"):
        origenes.add_argument(f"--{origen}", type=Path)
    cli.add_argument("--edicion", help="Edición oficial o identificador del archivo")
    cli.add_argument("--archivo", help="CSV de datos dentro del ZIP de DENUE")
    cli.add_argument("--encoding", help="Codificación del CSV")
    cli.add_argument("--estado", action="append", default=[])
    cli.add_argument("--solo-sucursales", action="store_true")
    args = cli.parse_args()
    inicializar(args.db)
    try:
        with conectar(args.db) as db:
            if args.productos:
                mensaje = f"{cargar_productos(db, args.productos)} productos"
            elif args.denue:
                total = cargar_denue(db, args.denue, args.encoding or "utf-8-sig", args.archivo,
                                     args.edicion or args.denue.name)
                mensaje = f"{total} sucursales DENUE"
            elif args.qqp:
                sucursales, precios = cargar_qqp(db, args.qqp, args.encoding or "utf-8-sig",
                                                 args.edicion or args.qqp.name,
                                                 set(map(normalizar, args.estado)),
                                                 solo_sucursales=args.solo_sucursales)
                mensaje = f"{sucursales} sucursales QQP, {precios} observaciones leídas"
            elif args.equivalencias:
                mensaje = f"{cargar_equivalencias(db, args.equivalencias)} equivalencias de producto"
            elif args.familias:
                mensaje = f"{cargar_familias(db, args.familias)} familias de producto"
            else:
                mensaje = f"{cargar_enlaces(db, args.enlaces)} vínculos de sucursal"
        print(mensaje)
    except (OSError, UnicodeError, ValueError, KeyError, sqlite3.Error) as error:
        cli.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
