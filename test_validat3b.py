from geolocalizar import contrastar, desempatar
from mobile.catalogos import cadena_de
from validat3b import MOBILE_PROMPT, PROMPT, apply_rules, cost

cap = {"capture_id": "X", "capture_price": 30.0, "min_product_price": 20.0, "max_product_price": 40.0,
       "capture_barcode": 750, "product_barcode": 750}
ok = {"decision": "aprobada", "confidence_score": 0.95, "reason_code": "OK", "precio_detectado": "30.00",
      "validaciones": {"tienda_fachada": "ok", "producto": "ok", "evidencia_precio": "ok"}}

# formato oficial: exactamente estas llaves, validaciones en "ok"/"falla"
out = apply_rules(cap, ok)
assert set(out) == {"capture_id", "decision", "confidence_score", "reason_code", "validaciones",
                    "precio_detectado", "codigo_barras_detectado", "explicacion"}
assert out["validaciones"] == {"tienda_fachada": "ok", "producto": "ok", "codigo_barras": "ok", "evidencia_precio": "ok"}
assert out["decision"] == "aprobada"
otra = apply_rules(cap, ok, geo={"estado": "otra_cadena", "tienda": {
    "id": "2", "cadena": "Soriana", "nombre": "SORIANITA CENTRO", "municipio": "Morelia",
    "lat": 19.7, "lon": -101.2, "distancia_m": 23,
}})
assert otra["decision"] == "revision_manual" and otra["validaciones"]["tienda_fachada"] == "falla"
assert "[geo: el GPS ubica la foto a 23 m de SORIANITA CENTRO (Soriana)]" in otra["explicacion"]
coincide = apply_rules(cap, ok, geo={"estado": "coincide", "tienda": {
    "id": "1", "cadena": "Tiendas 3B", "nombre": "TIENDAS 3B CENTRO", "municipio": "Morelia",
    "lat": 19.7, "lon": -101.2, "distancia_m": 18,
}})
assert coincide["decision"] == "aprobada" and set(coincide) == set(out)
assert "[geo: sucursal TIENDAS 3B CENTRO, Morelia, a 18 m]" in coincide["explicacion"]
assert apply_rules(cap, {**ok, "validaciones": {**ok["validaciones"], "producto": "falla"}})["decision"] == "revision_manual"
assert apply_rules(cap, {**ok, "precio_detectado": 32})["reason_code"] == "PRECIO_NO_COINCIDE"
assert apply_rules(cap, {**ok, "precio_detectado": None})["decision"] == "revision_manual"
assert apply_rules(cap, {**ok, "confidence_score": 0.6})["decision"] == "revision_manual"
assert apply_rules(cap, {**ok, "decision": "quizas"})["decision"] == "revision_manual"
assert apply_rules({**cap, "product_barcode": 751}, ok)["decision"] == "revision_manual"
assert apply_rules({**cap, "capture_price": 50.0}, {**ok, "precio_detectado": 50})["decision"] == "revision_manual"
assert apply_rules(cap, {**ok, "reason_code": "INVENTADO"})["reason_code"] == "DUDOSO"
assert apply_rules(cap, {})["decision"] == "revision_manual"
# cadenas con código interno en la etiqueta: nunca se aprueban
assert apply_rules({**cap, "capture_store_name": "Walmart"}, ok)["decision"] == "revision_manual"
assert apply_rules({**cap, "capture_store_name": "Soriana"}, ok)["decision"] == "aprobada"
# la etiqueta trae el código del producto: una duda del modelo sin fallas se aprueba...
dudosa = {**ok, "decision": "revision_manual", "confidence_score": 0.6}
assert apply_rules(cap, dudosa, {"750"})["decision"] == "aprobada"
assert apply_rules(cap, dudosa, {"750"})["codigo_barras_detectado"] == "750"
# ...pero no si el código es otro, si el precio no cuadra, si hay una falla o si es cadena sin verificación
assert apply_rules(cap, dudosa, {"401999"})["decision"] == "revision_manual"
assert apply_rules(cap, {**dudosa, "precio_detectado": 31}, {"750"})["decision"] == "revision_manual"
assert apply_rules(cap, {**dudosa, "validaciones": {**ok["validaciones"], "producto": "falla"}}, {"750"})["decision"] == "revision_manual"
assert apply_rules({**cap, "capture_store_name": "Bara"}, dudosa, {"750"})["decision"] == "revision_manual"
assert cost("aprobada", "rechazada") == 3 and cost("rechazada", "aprobada") == 10 and cost("aprobada", "revision_manual") == 1
movil = apply_rules(cap, ok, store_verified=True)
assert movil["decision"] == "aprobada" and movil["validaciones"]["sucursal"] == "ok"
assert "tienda_fachada" not in movil["validaciones"]
assert apply_rules(cap, ok, store_verified=False)["decision"] == "revision_manual"
assert apply_rules(cap, dudosa, {"750"}, store_verified=False)["decision"] == "revision_manual"
assert apply_rules({**cap, "product_barcode": None, "capture_barcode": None},
                   ok, store_verified=True)["decision"] == "revision_manual"
# corroboración local: con ocr, aprobar exige zxing O (precio + últimos 6 dígitos del código en el texto OCR)
cap13 = {**cap, "product_barcode": 7501234567890, "capture_barcode": 7501234567890}
assert apply_rules(cap13, ok, ocr=lambda: "ARROZ $30.00 7501234567890")["decision"] == "aprobada"
assert apply_rules(cap13, ok, ocr=lambda: "ARROZ $30.00")["decision"] == "revision_manual"      # falta el código
assert apply_rules(cap13, ok, ocr=lambda: "ARROZ 567890 $31.00")["decision"] == "revision_manual"  # otro precio
assert apply_rules(cap13, ok, ocr=lambda: "")["decision"] == "revision_manual"                    # sin OCR → no aprueba
assert apply_rules(cap13, ok, {"7501234567890"}, ocr=lambda: "")["decision"] == "aprobada"         # zxing basta
llamadas = []
apply_rules(cap13, {**ok, "confidence_score": 0.5}, ocr=lambda: llamadas.append(1) or "")
assert not llamadas  # el OCR (caro) no corre si otra regla ya la mandó a revisión
# falta etiqueta o precio unitario (dicho por el modelo) → rechazo; la misma etiqueta puesta por nuestra regla → revisión
assert apply_rules(cap, {**dudosa, "reason_code": "SIN_PRECIO_UNITARIO", "precio_detectado": None})["decision"] == "rechazada"
assert apply_rules(cap, {**dudosa, "reason_code": "SIN_ETIQUETA_PRECIO"})["decision"] == "rechazada"
sin_precio = apply_rules(cap, {**ok, "precio_detectado": None})
assert sin_precio["decision"] == "revision_manual" and sin_precio["reason_code"] == "SIN_ETIQUETA_PRECIO"
# la app móvil arma su prompt reemplazando estas frases: si cambian, su prompt se queda viejo sin avisar
for frase in ("Cada captura trae 3 fotos (fachada de la tienda, producto, etiqueta de precio en anaquel)",
              "¿la fachada corresponde a la cadena indicada? ", "Aprueba solo si los tres frentes son claramente correctos."):
    assert frase in PROMPT and frase not in MOBILE_PROMPT, frase
from ocr_local import crop_box
box = crop_box("<|det|>text [100, 200, 300, 400]<|/det|>$30.00\n<|det|>text [0, 0, 999, 50]<|/det|>OFERTA")
assert box and abs(box[0] - (100 / 999 - 0.08)) < 1e-9 and abs(box[3] - (400 / 999 + 0.08)) < 1e-9  # solo la caja con números
assert crop_box("<|det|>text [0, 0, 999, 999]<|/det|>$30.00") is None  # ya es toda la foto: no vale la pena recortar
assert crop_box("sin cajas") is None
# dudas del modelo corroboradas por el OCR local → aprobar; sin corroborar → revisión; el OCR corre una sola vez
duda13 = {**ok, "decision": "revision_manual", "confidence_score": 0.6}
lecturas = []
leer = lambda: lecturas.append(1) or "ARROZ $30.00 7501234567890"
assert apply_rules(cap13, duda13, ocr=leer)["decision"] == "aprobada" and len(lecturas) == 1
assert apply_rules(cap13, duda13, ocr=lambda: "ARROZ $30.00")["decision"] == "revision_manual"
assert apply_rules({**cap13, "capture_store_name": "Walmart"}, duda13, ocr=leer)["decision"] == "revision_manual"
assert len(lecturas) == 1  # en cadena sin verificación ni se intenta el OCR
# contenido esperado legible y con equivalencia (el modelo se confundía con L/ml y kg/g)
from validat3b import contenido, metadata
assert contenido({"unit_product": "mililitro", "unit_quantity_product": 1100.0}) == "1100 ml (= 1.1 L)"
assert contenido({"unit_product": "gramo", "unit_quantity_product": 1000.0}) == "1000 g (= 1 kg)"
assert contenido({"unit_product": "gramo", "unit_quantity_product": 485.0}) == "485 g"
assert contenido({"unit_product": "pieza", "unit_quantity_product": 4.0}) == "4 pieza"
assert contenido({}) is None
m = metadata({"capture_price": 30.0, "unit_product": "gramo", "unit_quantity_product": 1000.0}, "v2")
assert metadata({"unit_product": "gramo", "unit_quantity_product": 5.0}, "v1")["unit_quantity_product"] == 5.0
assert m["contenido_esperado"] == "1000 g (= 1 kg)" and "unit_product" not in m
# salida web: campos de capturas.json + resultado oficial + hallazgos y acción sugerida
import salida_web
cw = {**cap13, "capture_store_name": "Soriana", "product_name": "Arroz", "min_product_price": 20.0, "max_product_price": 40.0}
borrosa = apply_rules(cw, {"decision": "rechazada", "confidence_score": 0.9, "reason_code": "CAPTURA_BORROSA",
                           "explicacion": "Foto shelf borrosa (nitidez 12 < 35)"})
w = salida_web.registro(cw, borrosa, {"nitidez": {"shelf": 12.0}})
assert w["product_name"] == "Arroz" and w["decision"] == "rechazada" and w["accion_sugerida"] == salida_web.ACCIONES["CAPTURA_BORROSA"]
assert any(x["fuente"] == "nitidez" and x["nivel"] == "falla" for x in w["hallazgos"])
otro = apply_rules(cw, {**ok, "precio_detectado": 31})
w = salida_web.registro(cw, otro, {"nitidez": {"shelf": 90, "product": 90}, "codigos_etiqueta": [], "modelo": True})
assert any("$31.00" in x["mensaje"] and x["nivel"] == "falla" for x in w["hallazgos"])
assert w["accion_sugerida"] == salida_web.ACCIONES["PRECIO_NO_COINCIDE"]
cadena = salida_web.registro({**cw, "capture_store_name": "Walmart"}, apply_rules({**cw, "capture_store_name": "Walmart"}, ok),
                             {"nitidez": {}, "codigos_etiqueta": ["401013049343"], "modelo": True})
assert any("código interno" in x["mensaje"] for x in cadena["hallazgos"]) and "analista" in cadena["accion_sugerida"]
assert salida_web.registro(cw, apply_rules(cw, ok, {"7501234567890"}), {"modelo": True})["accion_sugerida"] is None
# política: duda del modelo por mala calidad de foto → rechazo para recapturar; duda de contenido → sigue en revisión
duda_foto = {**dudosa, "explicacion": "La etiqueta está pequeña y no se lee bien el precio unitario."}
r_foto = apply_rules(cap, duda_foto)
assert r_foto["decision"] == "rechazada" and r_foto["reason_code"] == "CAPTURA_LEJANA"
assert apply_rules(cap, {**dudosa, "explicacion": "La foto del producto está borrosa."})["reason_code"] == "CAPTURA_BORROSA"
assert apply_rules(cap, {**dudosa, "explicacion": "No se puede confirmar si la oferta sigue vigente."})["decision"] == "revision_manual"
assert apply_rules({**cap, "capture_store_name": "Walmart"}, ok)["decision"] == "revision_manual"  # el texto de la regla de cadena no cuenta

tiendas = [
    {"id": "otra", "cadena": "Soriana", "nombre": "SORIANITA", "municipio": "Morelia", "lat": 19.0, "lon": -99.0001},
    {"id": "propia", "cadena": "Neto", "nombre": "NETO CENTRO", "municipio": "Morelia", "lat": 19.0, "lon": -99.0005},
]
geo = contrastar((19.0, -99.0), "Neto", tiendas)
assert geo["estado"] == "coincide" and geo["tienda"]["id"] == "propia"
assert contrastar((19.0, -99.0), "Neto", [{**tiendas[1], "lon": -99.002}])["estado"] == "sin_sucursal_cercana"
assert geo["ambigua"] is True  # la Soriana está más cerca que la Neto declarada: el GPS no basta
assert contrastar((19.0, -99.0), "Neto", tiendas[1:])["ambigua"] is False
gemela = {**tiendas[1], "id": "gemela", "lon": -98.9995}  # otra Neto a ~53 m, del otro lado del GPS
assert contrastar((19.0, -99.0), "Neto", tiendas[1:] + [gemela])["ambigua"] is True
duplicada = {**tiendas[1], "id": "duplicada", "lat": 19.0001}  # mismo local registrado dos veces (~11 m)
assert contrastar((19.0, -99.0), "Neto", tiendas[1:] + [duplicada])["ambigua"] is False
assert cadena_de("CEDIS MONTERREY T493", "TIENDAS CHEDRAUI") is None
assert cadena_de("TIENDAS TRES B OFICINAS EJECUTIVAS", "TIENDAS TRES B") is None
# desempate por OCR de la fachada entre varias sucursales del radio
netos = contrastar((19.0, -99.0), "Neto", [
    {"id": "jal", "cadena": "Neto", "nombre": "650121 NETO JALACINGO", "municipio": "M", "lat": 19.0, "lon": -99.0002},
    {"id": "zap", "cadena": "Neto", "nombre": "650348 NETO ZAPATA 2", "municipio": "M", "lat": 19.0, "lon": -98.9997},
])
assert netos["ambigua"] and netos["tienda"]["id"] == "jal"
zapata = desempatar(netos, "Neto", "<|det|>text [650121, 1, 2, 3]<|/det|>TIENDAS NETO\n<|det|>text [1, 2, 3, 4]<|/det|>ZAPATA")
assert zapata["tienda"]["id"] == "zap" and zapata["por_ocr"] and not zapata["ambigua"]  # los números de las cajas no cuentan
assert desempatar(netos, "Neto", "TIENDAS NETO") is netos  # empate: se queda lo que dijo el GPS
plaza = contrastar((19.0, -99.0), "Soriana", [
    {"id": "fre", "cadena": "La Comer", "nombre": "439 FRESKO ESFERA", "municipio": "M", "lat": 19.0, "lon": -99.0001},
    {"id": "sor", "cadena": "Soriana", "nombre": "SORIANA SUPER PLAZA SERENA SUCURSAL 0673", "municipio": "M",
     "lat": 19.0, "lon": -99.0008},
])
assert plaza["estado"] == "coincide" and plaza["ambigua"]  # el GPS solo prefiere la cadena declarada...
assert desempatar(plaza, "Soriana", "FRESKO La Comer")["estado"] == "otra_cadena"  # ...la fachada dice otra tienda
assert desempatar(plaza, "Soriana", "SORIANA sucursal 673")["tienda"]["id"] == "sor"
assert cadena_de("1234 BA EXPRESS CENTRO", "NUEVA WAL MART DE MEXICO") == "Bodega Aurrera"
assert cadena_de("SUPERCENTER X", "NUEVA WAL MART DE MEXICO") == "Walmart"
assert cadena_de("SAMS CLUB 1", "NUEVA WAL MART DE MEXICO") is None
assert cadena_de("650110 NETO CENTRO", "TIENDAS SUPER PRECIO") == "Neto"
# fachadas reales (Mariano Escobedo, CDMX): 7-Eleven más cerca que la Tiendas 3B declarada; el texto decide
escobedo = contrastar((19.430886, -99.180497), "Tiendas 3B", [
    {"id": "3b", "cadena": "Tiendas 3B", "nombre": "TIENDAS TRES B", "municipio": "Miguel Hidalgo",
     "direccion": "GENERAL MARIANO ESCOBEDO 555 POLANCO V SECCIÓN", "lat": 19.43108792, "lon": -99.18107449},
    {"id": "7e", "cadena": "Otra", "nombre": "7 ELEVEN SUC 0739 RUBEN DARÍO", "municipio": "Miguel Hidalgo",
     "direccion": "MARIANO ESCOBEDO 525 DEL BOSQUE DE CHAPULTEPEC I SECCION", "lat": 19.43071982, "lon": -99.18090758},
])
assert escobedo["estado"] == "coincide" and escobedo["ambigua"]
assert desempatar(escobedo, "Tiendas 3B", "ABIERTO 24 HORAS ELEVEN")["estado"] == "otra_cadena"
assert desempatar(escobedo, "Tiendas 3B", "Tiendas 3B Tu Despensa Inteligente MARIANO ESCOBEDO 555 ENTRADA")["tienda"]["id"] == "3b"
# texto real del OCR local (fragmento): el "07:00 hrs" del horario no debe empatar con el "7" de 7 ELEVEN
real_3b = "icar 3B\n<|det|>text [136, 205, 415, 407]<|/det|>Kundas 3B\n<|det|>text [420, 240, 999, 350]<|/det|>MARIANO ESCOBEDO 555\nDE: 07:00 hrs a 22:00 hrs"
assert desempatar(escobedo, "Tiendas 3B", real_3b)["tienda"]["id"] == "3b"
assert desempatar(escobedo, "Tiendas 3B", "icarico\n A BIERTO\n 24\n HORAS") is escobedo  # lo que el OCR leyó del 7-Eleven
# precisión del GPS: más de 50 m no nombra sucursal; el margen con la gemela de la cadena crece 2 × precisión
cerca_lejos = [{"id": "a", "cadena": "Neto", "nombre": "NETO A", "municipio": "M", "lat": 19.0, "lon": -99.00019},  # ~20 m
               {"id": "b", "cadena": "Neto", "nombre": "NETO B", "municipio": "M", "lat": 19.0, "lon": -98.99943}]  # ~60 m
assert contrastar((19.0, -99.0), "Neto", cerca_lejos)["ambigua"] is False
assert contrastar((19.0, -99.0), "Neto", cerca_lejos, precision_m=15)["ambigua"] is True
assert contrastar((19.0, -99.0), "Neto", cerca_lejos[:1], precision_m=60)["ambigua"] is True
# salida web: hallazgo del GPS de la fachada
import salida_web
assert salida_web.hallazgos_geo("Neto", {"estado": "sin_gps"}) == []
assert salida_web.hallazgos_geo("Tiendas 3B", escobedo)[0]["nivel"] == "aviso"
assert salida_web.hallazgos_geo("Tiendas 3B", desempatar(escobedo, "Tiendas 3B", "ABIERTO 24 HORAS ELEVEN"))[0]["nivel"] == "falla"
assert "confirma" in salida_web.hallazgos_geo("Tiendas 3B", desempatar(escobedo, "Tiendas 3B", real_3b))[0]["mensaje"]
# v2.2: con calidad_fotos decide el campo, no el texto
ausencia = {**dudosa, "explicacion": "Es precio regular, no se ve leyenda de oferta ni de volumen.",
            "calidad_fotos": {"producto": "buena", "etiqueta": "buena"}}
assert apply_rules(cap, ausencia)["decision"] == "revision_manual"  # "no se ve leyenda" ya no rechaza
lejos = apply_rules(cap, {**dudosa, "calidad_fotos": {"producto": "buena", "etiqueta": "lejana"}})
assert lejos["decision"] == "rechazada" and lejos["reason_code"] == "CAPTURA_LEJANA"
assert apply_rules(cap, {**dudosa, "calidad_fotos": {"producto": "tapada", "etiqueta": "buena"}})["reason_code"] == "PRODUCTO_NO_VISIBLE"
assert "calidad_fotos" not in apply_rules(cap, ausencia)  # no sale en el JSON oficial
# criterio del equipo: precio regular = precio unitario si cuadra; dos pesos (drenado/neto) → revisión, no rechazo
sin_unit = {**dudosa, "decision": "rechazada", "reason_code": "SIN_PRECIO_UNITARIO", "precio_detectado": 30.0}
assert apply_rules(cap, sin_unit)["decision"] == "revision_manual"
assert apply_rules(cap, {**sin_unit, "precio_detectado": 32.0})["decision"] == "rechazada"     # si no cuadra, sí se rechaza
assert apply_rules(cap, {**sin_unit, "decision": "revision_manual"})["decision"] == "revision_manual"
doble = {**cap, "product_name": "Chiles chipotles adobados 120g (total: 210g)"}
no_coincide = {**dudosa, "decision": "rechazada", "reason_code": "PRODUCTO_NO_COINCIDE"}
assert apply_rules(doble, no_coincide)["decision"] == "revision_manual"
assert apply_rules(cap, no_coincide)["decision"] == "rechazada"                                # un solo peso: sí se rechaza
assert "210 g de contenido neto" in contenido({"unit_product": "gramo", "unit_quantity_product": 120.0,
                                                 "product_name": "Chiles chipotles adobados 120g (total: 210g)"})
print("ok")
