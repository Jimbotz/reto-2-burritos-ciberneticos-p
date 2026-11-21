"""Prueba de la comparación de precios Profeco por zona. Uso: python -m mobile.test_comparar"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from mobile.api import comparar_qqp, contenido, cumple, ranking_cadenas, unidad_comparable
from mobile.catalogos import guardar_sucursal
from mobile.db import conectar, inicializar

CDMX = "Ciudad de México"


def tienda(db, id_, cadena, municipio="Coyoacán"):
    guardar_sucursal(db, dict(id=id_, clee=None, cadena=cadena, nombre=id_, direccion="", municipio=municipio,
                              estado=CDMX, lat=19.35, lon=-99.16, fuente="Profeco QQP", edicion="t"))


def precio(db, producto, marca, presentacion, sucursal, fecha, centavos):
    db.execute("INSERT INTO precios_qqp VALUES (?, ?, ?, ?, ?, ?, 't')",
               (producto, marca, presentacion, sucursal, fecha, centavos))


with TemporaryDirectory() as folder:
    path = Path(folder) / "t.sqlite"
    inicializar(path)
    with conectar(path) as db:
        tienda(db, "qqp:sor1", "Soriana")
        tienda(db, "qqp:sor2", "Soriana")
        tienda(db, "qqp:wal", "Walmart")
        tienda(db, "qqp:lejos", "Chedraui", "Tlalpan")  # otra alcaldía: fuera de la zona
        db.execute("INSERT INTO productos VALUES ('7', '750', '750', ?)",
                   (json.dumps({"product_name": "Leche condensada", "unit_product": "gramo",
                                "unit_quantity_product": "375.0"}),))
        db.execute("INSERT INTO equivalencias_qqp VALUES ('7', 'Leche Condensada', 'Lechera', 'Lata 375 Gr.')")
        L = ("Leche Condensada", "Lechera", "Lata 375 Gr.")
        precio(db, *L, "qqp:sor1", "2026-03-01", 2600)  # precio viejo: lo reemplaza el más reciente de la tienda
        precio(db, *L, "qqp:sor1", "2026-03-20", 2000)
        precio(db, *L, "qqp:sor2", "2026-03-25", 2200)
        precio(db, *L, "qqp:wal", "2026-03-18", 1900)
        precio(db, *L, "qqp:lejos", "2026-03-18", 1000)

        # Sin familia solo hay nivel 1
        r = comparar_qqp(db, "7", CDMX, "Coyoacán")
        assert [x["cadena"] for x in r["exacto"]] == ["Walmart", "Soriana"], r
        assert r["exacto"][1] == {"cadena": "Soriana", "mediana_centavos": 2100, "tiendas": 2, "fecha": "2026-03-25"}
        assert r["presentaciones"] == [] and r["alternativas"] == []
        assert comparar_qqp(db, "7", CDMX, "Tlalpan")["exacto"] == [
            {"cadena": "Chedraui", "mediana_centavos": 1000, "tiendas": 1, "fecha": "2026-03-18"}]
        assert comparar_qqp(db, "7", CDMX, "Xochimilco")["exacto"] == [] and comparar_qqp(db, "x", CDMX, "Coyoacán")["exacto"] == []

        # Familia: misma marca en otra presentación (nivel 2) y otras marcas (nivel 3), por precio unitario
        db.execute("INSERT INTO familias_qqp VALUES ('7', 'Leche Condensada', 'Lechera', '-cero')")
        precio(db, "Leche Condensada", "Lechera", "Botella 335 Gr.", "qqp:sor1", "2026-03-20", 2400)
        precio(db, "Leche Condensada", "Lechera", "Lata 100 Gr.", "qqp:sor1", "2026-03-20", 1200)  # 0.27×: fuera de rango
        precio(db, "Leche Condensada", "Nutri", "Lata 380 Gr.", "qqp:wal", "2026-03-18", 1500)
        precio(db, "Leche Condensada", "Nutri", "Lata 380 Gr.", "qqp:sor2", "2026-03-25", 1700)
        precio(db, "Leche Condensada", "Lechera Cero", "Lata 385 Gr.", "qqp:wal", "2026-03-18", 1000)  # excluida por filtro
        precio(db, "Mayonesa", "Nutri", "Frasco 380 Gr.", "qqp:wal", "2026-03-18", 900)  # otro tipo de producto
        r = comparar_qqp(db, "7", CDMX, "Coyoacán")
        assert r["presentaciones"] == [{"marca": "Lechera", "presentacion": "Botella 335 Gr.", "cadena": "Soriana",
                                        "mediana_centavos": 2400, "tiendas": 1, "fecha": "2026-03-20",
                                        "por_unidad_centavos": 7164}], r["presentaciones"]
        assert [(x["marca"], x["cadena"], x["por_unidad_centavos"]) for x in r["alternativas"]] == [
            ("Nutri", "Walmart", 3947), ("Nutri", "Soriana", 4474)], r["alternativas"]

        # Ranking de cadenas: % sobre la más barata en cada producto exacto, promediado por cadena
        for sku in ("8", "9"):
            db.execute("INSERT INTO productos VALUES (?, ?, ?, '{}')", (sku, sku * 3, sku * 3))
        db.execute("INSERT INTO equivalencias_qqp VALUES ('8', 'Mayonesa', 'Nutri', 'Frasco 380 Gr.')")
        db.execute("INSERT INTO equivalencias_qqp VALUES ('9', 'Leche Condensada', 'Lechera', 'Lata 375 Gr.')")  # mismo producto que el SKU 7: cuenta una vez
        precio(db, "Mayonesa", "Nutri", "Frasco 380 Gr.", "qqp:sor1", "2026-03-20", 800)
        k = ranking_cadenas(db, CDMX, "Coyoacán")
        assert k["productos"] == 2 and k["fecha"] == "2026-03-25", k
        assert [(c["cadena"], c["productos"], c["mas_barata"]) for c in k["cadenas"]] == [
            ("Soriana", 2, 1), ("Walmart", 2, 1)], k  # Soriana: +10.5% y 0% → 5.3%; Walmart: 0% y +12.5% → 6.2%
        assert k["cadenas"][0]["sobre_mas_barata_pct"] == 5.3
        assert ranking_cadenas(db, CDMX, "Tlalpan") == {"productos": 0, "fecha": None, "cadenas": []}

assert contenido("Botella 1.5 Lt.", "mililitro") == 1500 and contenido("Botella 740ml. Fresca", "mililitro") == 740
assert contenido("Bolsa 3.564 Gr. Polvo", "gramo") == 3564 and contenido("Caja 257.6 Gr. Chips", "gramo") == 257.6
assert contenido("Bote 338 Gr./400 Ml.", "gramo") == 338 and contenido("Bote 338 Gr./400 Ml.", "mililitro") == 400
assert contenido("Paquete C/12 Blanco", "pieza") == 12 and contenido("Paquete 250 Hojas", "pieza") == 250
assert contenido("Lata 360 Gr.", "mililitro") is None and contenido("Pieza Grande", "gramo") is None
assert cumple("refritos bayo", "La Sierra Bolsa 430 Gr. Refritos. Bayos") and not cumple("refritos bayo", "Isadora Refritos Negros")
assert cumple("super_extra -integral -extra_verde", "Verde Valle Bolsa 1 Kg. Super Extra")
assert not cumple("super_extra -integral", "Sos Bolsa 1 Kg. Super Extra. Integral")
assert not cumple("-extra_verde", "Schettino Bolsa 900 Gr. Super Extra. Verde") and cumple("", "lo que sea")
assert unidad_comparable({"unit_product": "gramo", "unit_quantity_product": "375.0"}) == ("kg", 1000 / 375, 375)
assert unidad_comparable({"product_name": "Atún en aceite 90g (total: 130g)", "unit_product": "gramo",
                          "unit_quantity_product": "90"}) == ("kg", 1000 / 130, 130)
assert unidad_comparable({"unit_product": "pieza", "unit_quantity_product": "250"}) == ("pieza", 1 / 250, 250)
assert unidad_comparable({"unit_product": "gramo", "unit_quantity_product": "0"}) == (None, None, None)
print("ok")
