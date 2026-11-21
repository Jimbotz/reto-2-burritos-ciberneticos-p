from validat3b import apply_rules, cost

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
print("ok")
