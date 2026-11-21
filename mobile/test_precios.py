from pathlib import Path
from tempfile import TemporaryDirectory

from mobile.api import precios_qqp_cercanos
from mobile.catalogos import guardar_sucursal
from mobile.db import conectar, inicializar


with TemporaryDirectory() as temporal:
    path = Path(temporal) / "campo.sqlite"
    inicializar(path)
    with conectar(path) as db:
        for id_tienda, lat, fuente in [
            ("denue:1", 19.4, "INEGI DENUE"),
            ("qqp:elegida", 19.4, "Profeco QQP"),
            ("qqp:primera", 19.405, "Profeco QQP"),
            ("qqp:conflicto", 19.41, "Profeco QQP"),
            ("qqp:segunda", 19.415, "Profeco QQP"),
            ("qqp:lejos", 19.45, "Profeco QQP"),
        ]:
            guardar_sucursal(db, dict(id=id_tienda, clee=None, cadena="Soriana", nombre=id_tienda,
                                      direccion="", municipio="CDMX", estado="Ciudad de México",
                                      lat=lat, lon=-99.15, fuente=fuente, edicion="prueba"))
        db.execute("INSERT INTO productos VALUES ('7', '12345678', '12345678', '{}')")
        db.execute("INSERT INTO equivalencias_qqp VALUES ('7', 'Leche', 'Marca', '360 g')")
        db.execute("INSERT INTO enlaces_qqp VALUES ('denue:1', 'qqp:elegida')")
        obs = [
            ("qqp:elegida", "2026-01-15", 1000),
            ("qqp:primera", "2026-01-13", 1500),
            ("qqp:primera", "2026-01-15", 2000),
            ("qqp:primera", "2026-11-22", 2200),
            ("qqp:conflicto", "2026-01-15", 3000),
            ("qqp:conflicto", "2026-01-15", 3100),
            ("qqp:segunda", "2026-01-04", 2500),
            ("qqp:lejos", "2026-01-15", 900),
        ]
        db.executemany("INSERT INTO precios_qqp VALUES ('Leche', 'Marca', '360 g', ?, ?, ?, 'prueba')", obs)
        precios = precios_qqp_cercanos(db, "7", "denue:1", "2026-11-21", 19.4, -99.15)
        assert [(fila["id"], fila["precio_centavos"]) for fila in precios] == [
            ("qqp:primera", 2000), ("qqp:segunda", 2500),
        ]
        assert 0 < precios[0]["distancia_m"] < precios[1]["distancia_m"] <= 3000
        assert not precios_qqp_cercanos(db, "sin-mapeo", "denue:1", "2026-11-21", 19.4, -99.15)
print("ok")
