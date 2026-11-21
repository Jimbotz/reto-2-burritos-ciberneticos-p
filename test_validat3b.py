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
assert apply_rules(cap, {**dudosa, "reason_code": "SIN_PRECIO_UNITARIO"})["decision"] == "rechazada"
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
print("ok")
