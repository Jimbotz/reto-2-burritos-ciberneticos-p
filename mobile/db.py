from contextlib import contextmanager
from pathlib import Path
import sqlite3


ROOT = Path(__file__).resolve().parent.parent
SCHEMA = """
CREATE TABLE IF NOT EXISTS sucursales (
    id TEXT NOT NULL UNIQUE, clee TEXT, cadena TEXT NOT NULL, nombre TEXT NOT NULL,
    direccion TEXT NOT NULL, municipio TEXT NOT NULL, estado TEXT NOT NULL,
    lat REAL NOT NULL, lon REAL NOT NULL, fuente TEXT NOT NULL, edicion TEXT NOT NULL,
    busqueda TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS sucursales_geo USING rtree(rowid, lat_min, lat_max, lon_min, lon_max);
CREATE TABLE IF NOT EXISTS productos (
    sku TEXT PRIMARY KEY, codigo TEXT NOT NULL, codigo_busqueda TEXT NOT NULL UNIQUE, datos TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS precios_qqp (
    producto TEXT NOT NULL, marca TEXT NOT NULL, presentacion TEXT NOT NULL,
    sucursal_id TEXT NOT NULL REFERENCES sucursales(id), fecha TEXT NOT NULL,
    precio_centavos INTEGER NOT NULL, archivo TEXT NOT NULL,
    PRIMARY KEY (producto, marca, presentacion, sucursal_id, fecha, precio_centavos)
);
CREATE INDEX IF NOT EXISTS precios_qqp_sucursal ON precios_qqp(sucursal_id, fecha DESC);
CREATE TABLE IF NOT EXISTS equivalencias_qqp (
    sku TEXT NOT NULL REFERENCES productos(sku), producto TEXT NOT NULL, marca TEXT NOT NULL,
    presentacion TEXT NOT NULL, PRIMARY KEY (sku, producto, marca, presentacion)
);
CREATE TABLE IF NOT EXISTS enlaces_qqp (
    denue_id TEXT NOT NULL REFERENCES sucursales(id),
    qqp_id TEXT NOT NULL REFERENCES sucursales(id), PRIMARY KEY (denue_id, qqp_id)
);
CREATE TABLE IF NOT EXISTS sesiones (
    token_hash TEXT PRIMARY KEY, rol TEXT NOT NULL, vence REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS visitas (
    id TEXT PRIMARY KEY, sucursal_id TEXT REFERENCES sucursales(id), cadena TEXT NOT NULL,
    nombre TEXT NOT NULL, ubicacion TEXT NOT NULL, lat REAL, lon REAL, precision_m REAL,
    medida_en REAL, creada REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS capturas (
    id TEXT PRIMARY KEY, visita_id TEXT NOT NULL REFERENCES visitas(id),
    sku TEXT REFERENCES productos(sku), creada REAL NOT NULL, precio_centavos INTEGER NOT NULL,
    datos TEXT NOT NULL, evidencia TEXT NOT NULL, huella TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'pendiente', intentos INTEGER NOT NULL DEFAULT 0,
    disponible REAL NOT NULL, lease REAL, resultado TEXT, tokens INTEGER NOT NULL DEFAULT 0,
    revision TEXT
);
CREATE INDEX IF NOT EXISTS capturas_cola ON capturas(estado, disponible, creada);
"""


@contextmanager
def conectar(path):
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    try:
        with db:
            yield db
    finally:
        db.close()


def inicializar(path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with conectar(path) as db:
        db.execute("PRAGMA journal_mode = WAL")
        db.executescript(SCHEMA)


def all_dicts(cursor):
    return [dict(row) for row in cursor]
