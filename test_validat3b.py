from validat3b import apply_rules, cost

cap = {"capture_id": "X", "capture_price": 30.0, "min_product_price": 20.0, "max_product_price": 40.0,
       "capture_barcode": 750, "product_barcode": 750}
ok = {"decision": "aprobada", "confidence_score": 0.95, "reason_code": "OK", "precio_detectado": "30.00",
      "validaciones": {"tienda_fachada": True, "producto": True, "evidencia_precio": True}}

assert apply_rules(cap, ok)["decision"] == "aprobada"
assert apply_rules(cap, {**ok, "precio_detectado": 32})["reason_code"] == "PRECIO_NO_COINCIDE"
assert apply_rules(cap, {**ok, "precio_detectado": None})["decision"] == "revision_manual"
assert apply_rules(cap, {**ok, "confidence_score": 0.6})["decision"] == "revision_manual"
assert apply_rules(cap, {**ok, "decision": "quizas"})["decision"] == "revision_manual"
assert apply_rules({**cap, "product_barcode": 751}, ok)["decision"] == "revision_manual"
assert apply_rules({**cap, "capture_price": 50.0}, {**ok, "precio_detectado": 50})["decision"] == "revision_manual"
assert apply_rules(cap, {**ok, "reason_code": "INVENTADO"})["reason_code"] == "DUDOSO"
assert apply_rules(cap, {})["decision"] == "revision_manual"
assert cost("aprobada", "rechazada") == 3 and cost("rechazada", "aprobada") == 10 and cost("aprobada", "revision_manual") == 1
print("ok")
