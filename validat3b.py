"""Validat3B: valida capturas de precio de campo.

Uso:
    python validat3b.py ping                                   # prueba la conexión al endpoint
    python validat3b.py data/capturas.json out/resultados.json [N]   # N = solo las primeras N capturas
Lee .env (Endpoint, API_KEY, MODEL) y LLAMA AL MODELO. Agrega --local para correr solo los filtros locales (cero tokens).
Si las capturas traen `decision_esperada`, imprime costo operativo y precisión.
"""
import base64, json, os, sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
from anthropic import AnthropicFoundry

DECISIONS = ("aprobada", "rechazada", "revision_manual")
CHECKS = ("tienda_fachada", "producto", "codigo_barras", "evidencia_precio")
MODEL_CHECKS = ("tienda_fachada", "producto", "evidencia_precio")  # codigo_barras se verifica con metadatos

# ponytail: lista provisional; reemplazar por la oficial que llega con los datos del kickoff
REASON_CODES = {
    "OK": "Captura válida",
    "CAPTURA_BORROSA": "Capturas borrosas",
    "CAPTURA_LEJANA": "Capturas lejanas",
    "FOTO_DE_PANTALLA": "Foto de la pantalla de otro dispositivo",
    "FACHADA_INCORRECTA": "La fachada no corresponde a la cadena",
    "DESCRIPCION_INCOMPLETA": "Descripción de producto incompleta",
    "PRODUCTO_NO_COINCIDE": "El producto no coincide con la descripción",
    "CONTRATIPO_INVALIDO": "Contratipo no válido",
    "PRODUCTO_NO_VISIBLE": "Producto no visible",
    "SIN_ETIQUETA_PRECIO": "Sin etiqueta de precio",
    "SIN_PRECIO_UNITARIO": "Falta precio unitario",
    "PRECIO_NO_COINCIDE": "El precio de la etiqueta no coincide con el capturado",
    "DUDOSO": "Evidencia insuficiente para decidir",
}

# ponytail: calibrado en dev (aprobadas: nitidez mín 38 shelf, 31 product). Re-tunear con el set de validación.
BLUR_REJECT = {"shelf": 35.0, "product": 25.0}
APPROVE_MIN = 0.85  # aprobar con menos confianza que esto → revision_manual (gate de precisión ≥97%)

PROMPT = """Eres analista senior de auditoría de precios de Tiendas 3B. Revisas capturas de precio hechas en campo en tiendas de la competencia. Cada captura trae 3 fotos (fachada de la tienda, producto, etiqueta de precio en anaquel) y los metadatos del producto esperado.

Revisa tres frentes:
A. Identidad del producto: ¿la foto corresponde al producto esperado (marca, descripción, contenido)? ¿se ve completo y legible?
B. Calidad de evidencia: ¿la fachada corresponde a la cadena indicada? ¿las fotos son nítidas y cercanas? ¿alguna es foto de la pantalla de otro dispositivo?
C. Evidencia de precio: ¿hay etiqueta de precio visible y legible? ¿qué precio dice? ¿es regular, oferta o por volumen?

Aprueba solo si los tres frentes son claramente correctos. Si algo falla claramente, rechaza. Si no puedes asegurarlo, revision_manual. Aprobar una captura mala es el peor error posible.
confidence_score es tu certeza (0 a 1) en la decisión. validaciones: "ok" o "falla" por frente. explicacion: 1-2 frases en español; si hay precio, di si es regular, oferta o por volumen.

reason_code válidos:
""" + "\n".join(f"- {k}: {v}" for k, v in REASON_CODES.items())


def nullable(schema):
    return {"anyOf": [schema, {"type": "null"}]}


SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": list(DECISIONS)},
        "confidence_score": {"type": "number"},
        "reason_code": {"type": "string", "enum": list(REASON_CODES)},
        "validaciones": {"type": "object", "properties": {k: {"type": "string", "enum": ["ok", "falla"]} for k in MODEL_CHECKS},
                         "required": list(MODEL_CHECKS), "additionalProperties": False},
        "precio_detectado": nullable({"type": "number"}),
        "codigo_barras_detectado": nullable({"type": "string"}),
        "explicacion": {"type": "string"},
    },
    "required": ["decision", "confidence_score", "reason_code", "validaciones", "precio_detectado",
                 "codigo_barras_detectado", "explicacion"],
    "additionalProperties": False,
}

META_KEYS = ("capture_store_name", "capture_date", "capture_price", "capture_brand", "product_name",
             "unit_product", "unit_quantity_product", "product_group", "product_line")


def load_env(path=Path(__file__).with_name(".env")):
    if path.exists():
        for line in path.read_text().splitlines():
            k, sep, v = line.partition("=")
            if sep and not k.strip().startswith("#"):
                os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def read(path):
    img = cv2.imread(str(path))
    if img is None:
        raise ValueError(f"no se pudo leer {path}")
    return img


def blur_score(path):
    g = cv2.cvtColor(read(path), cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    g = cv2.resize(g, (1000, round(h * 1000 / w)))  # la varianza del Laplaciano depende de la resolución
    return cv2.Laplacian(g, cv2.CV_64F).var()


def img_b64(path, max_side):
    img = read(path)
    s = max_side / max(img.shape[:2])
    if s < 1:
        img = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    return base64.standard_b64encode(cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])[1]).decode()


def make_client():
    if not os.environ.get("API_KEY"):
        return None
    return AnthropicFoundry(api_key=os.environ["API_KEY"], base_url=os.environ["Endpoint"].rstrip("/") + "/", max_retries=6)


def ask_model(client, cap, base):
    content = []
    # ponytail: fachada a 512px (solo identifica la cadena), producto/etiqueta a 1024px para leer texto
    for kind, side in (("facade", 512), ("product", 1024), ("shelf", 1024)):
        content += [{"type": "text", "text": f"Foto {kind}:"},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                 "data": img_b64(base / cap[f"{kind}_file"], side)}}]
    content.append({"type": "text", "text": "Metadatos:\n" + json.dumps({k: cap.get(k) for k in META_KEYS}, ensure_ascii=False)})
    r = client.messages.create(
        model=os.environ["MODEL"],
        max_tokens=16000,
        system=PROMPT,
        messages=[{"role": "user", "content": content}],
        output_config={"effort": os.environ.get("EFFORT", "low"), "format": {"type": "json_schema", "schema": SCHEMA}},
    )
    if r.stop_reason != "end_turn":
        raise RuntimeError(f"stop_reason={r.stop_reason}")
    return json.loads(next(b.text for b in r.content if b.type == "text")), r.usage.input_tokens + r.usage.output_tokens


def apply_rules(cap, r):
    """Normaliza la respuesta del modelo al formato oficial (ver #foundry en la página del reto) y aplica reglas duras."""
    v = r.get("validaciones") or {}
    res = {
        "capture_id": cap["capture_id"],
        "decision": r.get("decision") if r.get("decision") in DECISIONS else "revision_manual",
        "confidence_score": max(0.0, min(1.0, num(r.get("confidence_score")) or 0.0)),
        "reason_code": r.get("reason_code") if r.get("reason_code") in REASON_CODES else "DUDOSO",
        "validaciones": {k: "ok" if v.get(k) == "ok" else "falla" for k in CHECKS},
        "precio_detectado": num(r.get("precio_detectado")),
        "codigo_barras_detectado": r.get("codigo_barras_detectado"),
        "explicacion": str(r.get("explicacion") or ""),
    }
    # el código de barras lo escanea la app: se verifica contra el esperado, no con la foto
    same = str(cap.get("capture_barcode")) == str(cap.get("product_barcode"))
    res["validaciones"]["codigo_barras"] = "ok" if same else "falla"

    if res["decision"] == "aprobada":
        p, cp = res["precio_detectado"], num(cap.get("capture_price"))
        lo, hi = num(cap.get("min_product_price")), num(cap.get("max_product_price"))
        why = None
        if res["confidence_score"] < APPROVE_MIN:
            why = ("DUDOSO", "confianza baja")
        elif any(x != "ok" for x in res["validaciones"].values()):
            why = ("DUDOSO", "alguna validación no pasó")
        elif p is None:
            why = ("SIN_ETIQUETA_PRECIO", "no se leyó precio en la etiqueta")
        elif cp is not None and abs(p - cp) > 0.01:
            why = ("PRECIO_NO_COINCIDE", f"etiqueta {p} vs capturado {cp}")
        elif cp is not None and lo is not None and hi is not None and not lo <= cp <= hi:
            why = ("DUDOSO", f"precio {cp} fuera de rango {lo}-{hi}")
        if why:
            res.update(decision="revision_manual", reason_code=why[0], explicacion=f"{res['explicacion']} [regla: {why[1]}]".strip())
    return res


def decide(cap, base, client):
    for kind in ("shelf", "product"):
        s = blur_score(base / cap[f"{kind}_file"])
        if s < BLUR_REJECT[kind]:
            return apply_rules(cap, {"decision": "rechazada", "confidence_score": 0.9, "reason_code": "CAPTURA_BORROSA",
                                     "explicacion": f"Foto {kind} borrosa (nitidez {s:.0f} < {BLUR_REJECT[kind]:.0f})"}), 0
    if client is None:
        return apply_rules(cap, {"explicacion": "Sin modelo: pasó los filtros locales"}), 0
    r, tokens = ask_model(client, cap, base)
    return apply_rules(cap, r), tokens


def safe_decide(cap, base, client):
    try:
        return decide(cap, base, client)
    except Exception as e:  # nunca perder una captura: el gate pide JSON válido en ≥99%
        print(f"{cap.get('capture_id')}: {e!r}", file=sys.stderr)
        return apply_rules(cap, {"explicacion": f"Error interno: {type(e).__name__}"}), 0


# ponytail: costo cuando esperada=revision_manual es supuesto (validar con las reglas oficiales)
def cost(expected, predicted):
    if predicted == "revision_manual":
        return 1
    if predicted == "aprobada":
        return 0 if expected == "aprobada" else 10
    return 3 if expected == "aprobada" else 0


def evaluate(caps, results):
    exp = {c["capture_id"]: c["decision_esperada"] for c in caps}
    pairs = [(exp[r["capture_id"]], r["decision"]) for r in results]
    approved = [e for e, p in pairs if p == "aprobada"]
    print(f"costo operativo: {sum(cost(e, p) for e, p in pairs)}  (todo a revisión manual = {len(pairs)})")
    if approved:
        print(f"precisión de aprobación: {sum(e == 'aprobada' for e in approved) / len(approved):.1%} de {len(approved)} (gate ≥97%)")
    print("esperada → predicha:")
    for (e, p), n in sorted(Counter(pairs).items()):
        print(f"  {e:16} → {p:16} {n:3}  costo {cost(e, p) * n}")


def ping():
    client = make_client()
    if client is None:
        sys.exit("Falta API_KEY en .env")
    r = client.messages.create(model=os.environ["MODEL"], max_tokens=1024, output_config={"effort": "low"},
                               messages=[{"role": "user", "content": "Responde solo: pong"}])
    text = next((b.text for b in r.content if b.type == "text"), "")
    print(f"{r.model} · {r.stop_reason} · {text!r} · {r.usage.input_tokens}+{r.usage.output_tokens} tokens")


def main(inp, outp, limit=None):
    caps = json.loads(Path(inp).read_text())
    todo = caps[:int(limit)] if limit else caps
    base, client = Path(inp).parent, make_client()
    with ThreadPoolExecutor(int(os.environ.get("WORKERS", 4))) as ex:
        rows = list(ex.map(lambda c: safe_decide(c, base, client), todo))
    results, tokens = [r for r, _ in rows], sum(t for _, t in rows)
    Path(outp).parent.mkdir(parents=True, exist_ok=True)
    Path(outp).write_text(json.dumps(results, ensure_ascii=False, indent=1))
    print(f"{len(results)} capturas · {tokens} tokens ({tokens / len(results):.0f}/captura) · modelo: {'sí' if client else 'no'} → {outp}")
    if all("decision_esperada" in c for c in caps):
        evaluate(caps, results)


if __name__ == "__main__":
    load_env()
    if "--local" in sys.argv:  # solo filtros locales, cero tokens
        sys.argv.remove("--local")
        os.environ.pop("API_KEY", None)
    if sys.argv[1:2] == ["ping"]:
        ping()
    else:
        main(*sys.argv[1:4])
