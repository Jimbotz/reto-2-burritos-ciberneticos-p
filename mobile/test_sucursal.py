"""Sugerencia de sucursal y verificación de fotos en la app: misma regla que el motor (geolocalizar.contrastar).
Coordenadas reales de la visita de campo a Mariano Escobedo (fotos de test/)."""
import csv
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from time import time

from mobile.api import Posicion, candidatas, foto_en_sucursal, sugerida
from mobile.catalogos import fichas_denue, guardar_sucursal
from mobile.db import conectar, inicializar

COLUMNAS = "id,nom_estab,raz_social,codigo_act,tipo_vial,nom_vial,numero_ext,nomb_asent,cod_postal,municipio,entidad,latitud,longitud"
FILAS = [
    "1,TIENDAS TRES B,TIENDAS TRES B,462111,CALLE,GENERAL MARIANO ESCOBEDO,555,POLANCO V SECCIÓN,11560,Miguel Hidalgo,CDMX,19.43108792,-99.18107449",
    "2,7 ELEVEN SUC 0739 RUBEN DARÍO,7-ELEVEN MEXICO,462112,CALLE,MARIANO ESCOBEDO,525,BOSQUE,11580,Miguel Hidalgo,CDMX,19.43071982,-99.18090758",
    "3,TIENDAS TRES B OFICINAS EJECUTIVAS,TIENDAS TRES B,462111,CALLE,X,1,Y,1,Miguel Hidalgo,CDMX,19.4313,-99.1815",
    "4,MISCELANEA LUPITA,,461110,CALLE,X,2,Y,1,Miguel Hidalgo,CDMX,19.4309,-99.1810",
]
fichas = list(fichas_denue(csv.DictReader(io.StringIO("\n".join([COLUMNAS, *FILAS]))), "prueba"))
assert [(f["id"], f["cadena"]) for f in fichas] == [("denue:1", "Tiendas 3B"), ("denue:2", "Otra")]  # sin oficinas ni miscelánea
assert fichas[0]["direccion"] == "CALLE GENERAL MARIANO ESCOBEDO 555, POLANCO V SECCIÓN, 11560"

with TemporaryDirectory() as temporal:
    path = Path(temporal) / "campo.sqlite"
    inicializar(path)
    with conectar(path) as db:
        for ficha in fichas:
            guardar_sucursal(db, ficha)

    with conectar(path) as db:
        def pos(lat, lon, precision):
            return Posicion(lat=lat, lon=lon, precision_m=precision, medida_en=time())

        # dentro de la 3B (IMG_4021, ±22 m): se sugiere; el 7-Eleven no se lista para elegir
        dentro = pos(19.431044, -99.181069, 22)
        assert sugerida(db, dentro, time()) == "denue:1"
        assert [c["id"] for c in candidatas(db, dentro)] == ["denue:1"]
        # frente al 7-Eleven (IMG_4031): la más cercana es de otra cadena, no se sugiere nada
        assert sugerida(db, pos(19.430886, -99.180497, 14), time()) is None
        # GPS impreciso (IMG_4030, ±172 m): no alcanza para verificar
        assert sugerida(db, pos(19.431033, -99.180917, 172), time()) is None

        visita = {"cadena": "Tiendas 3B", "sucursal_id": "denue:1"}
        assert foto_en_sucursal(db, ((19.431069, -99.181083), 21.2), visita)       # IMG_4022, producto dentro de la 3B
        assert not foto_en_sucursal(db, ((19.430839, -99.180847), 24.0), visita)   # IMG_4032, Doritos en el 7-Eleven
        assert not foto_en_sucursal(db, ((19.431033, -99.180917), 172.5), visita)  # IMG_4030, GPS de ±172 m
print("ok")
