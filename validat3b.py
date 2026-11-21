"""Validat3B: valida capturas de precio de campo.

Uso:
    python validat3b.py ping                                   # prueba la conexión al endpoint
    python validat3b.py data/capturas.json out/resultados.json [N]   # N = solo las primeras N capturas
Lee .env (Endpoint, API_KEY, MODEL) y LLAMA AL MODELO. Agrega --local para correr solo los filtros locales (cero tokens).
Si las capturas traen `decision_esperada`, imprime costo operativo y precisión.
"""
import base64, json, os, re, sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from functools import cache
from pathlib import Path

import cv2
import zxingcpp
from anthropic import AnthropicFoundry

import geolocalizar
import ocr_local

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
# Política del equipo: evidencia de mala calidad se rechaza para volver a capturar, no se manda a revisión.
# ponytail: busca la duda visual en la explicación libre del modelo; cambiar a un campo estructurado del modelo
# (calidad de cada foto) cuando se valide con una corrida. Dudas de contenido (vigencia, oferta) NO entran aquí.
DUDA_VISUAL = re.compile(r"peque|lejos|lejan|borros|desenfoc|ilegible|no se (lee|ve\b|distingue|alcanza)"
                         r"|no (es|son|está|están) (legible|visible)|no se puede (leer|asociar|distinguir|ver\b)"
                         r"|no queda claro|tapad|cortad|no se aprecia", re.I)
# ponytail: en dev 0 de 52 aprobadas en estas cadenas; su etiqueta trae código interno (400…/401…), no el del producto,
# así que no se puede verificar. No aprobar cuesta 1 punto, aprobar mal cuesta 10. Revalidar si el set ciego trae otras cadenas.
NO_APPROVE_CHAINS = {"Walmart", "Bodega Aurrera", "Bara"}

PROMPT = """Eres analista senior de auditoría de precios de Tiendas 3B. Revisas capturas de precio hechas en campo en tiendas de la competencia. Cada captura trae 3 fotos (fachada de la tienda, producto, etiqueta de precio en anaquel) y los metadatos del producto esperado.

Revisa tres frentes:
A. Identidad del producto: ¿la foto corresponde al producto esperado (marca, descripción, contenido)? ¿se ve completo y legible?
B. Calidad de evidencia: ¿la fachada corresponde a la cadena indicada? ¿las fotos son nítidas y cercanas? ¿alguna es foto de la pantalla de otro dispositivo?
C. Evidencia de precio: ¿hay etiqueta de precio visible y legible? ¿qué precio dice? ¿es regular, oferta o por volumen?

Aprueba solo si los tres frentes son claramente correctos. Si algo falla claramente, rechaza. Si no puedes asegurarlo, revision_manual. Aprobar una captura mala es el peor error posible.
confidence_score es tu certeza (0 a 1) en la decisión. validaciones: "ok" o "falla" por frente. explicacion: 1-2 frases en español; si hay precio, di si es regular, oferta o por volumen.

reason_code válidos:
""" + "\n".join(f"- {k}: {v}" for k, v in REASON_CODES.items())

# Versiones del prompt (elegir con VERSION=… en el entorno; resultados comparados en resultados/resumen.json):
#   v1   = prompt original.
#   v2   = v1 + equivalencias de medidas + usar la etiqueta del producto correcto (rechazó 1 válida de más y dejó de
#          rechazar fotos lejanas que v1 rechazaba "por falta de precio unitario").
#   v2.2 = v2.1 + el modelo califica cada foto (calidad_fotos: buena/lejana/borrosa/tapada) y la regla de rechazo
#          usa ese campo en lugar de buscar palabras en la explicación.
#   v2.1 = v1 + equivalencias de medidas + reconocer la foto lejana como CAPTURA_LEJANA (sin lo de la etiqueta vecina).
#          Default: con la regla de rechazo por mala calidad es la de menor costo (47 o 63 según cuánto cueste rechazar
#          una 'revisión' del analista; v1 da 52 o 67).
VERSION = os.environ.get("VERSION", "v2.1")
EQUIVALENCIAS = ("Contenido: 1 kg = 1000 g y 1 L = 1000 ml (por ejemplo, 1.1 L = 1100 ml). El empaque puede mostrar contenido "
                 "neto y masa drenada; cualquiera de los dos puede ser el esperado. Un extra de promoción (por ejemplo «400 g + "
                 "30 g gratis») es el mismo producto. Compara en la misma unidad antes de marcar falla.\n")
ETIQUETA_VECINA = ("La foto de la etiqueta puede mostrar varias etiquetas y productos vecinos: usa la etiqueta cuya descripción "
                   "corresponde al producto esperado e ignora las demás. Solo si ninguna lo describe, marca falla en evidencia de precio.\n")
LEJANA = ("Si la etiqueta o el producto se ven pequeños dentro de su foto (tomados de lejos, con mucho anaquel alrededor) y por eso "
          "no se leen bien, es rechazo con CAPTURA_LEJANA. Usa SIN_PRECIO_UNITARIO solo si la etiqueta se lee bien de cerca y de "
          "verdad no trae el precio unitario.\n")
CALIDAD = ("calidad_fotos: califica la foto del producto y la de la etiqueta SOLO por cómo se tomaron: buena (de cerca, enfocada, "
           "se lee), lejana (el objeto se ve pequeño y por eso no se lee), borrosa (desenfocada o movida) o tapada (algo cubre la "
           "parte importante). Que a la etiqueta le falte una leyenda (oferta, volumen, precio unitario) o que haya otras etiquetas "
           "cerca NO es mala calidad de foto.\n")
EXTRA = {"v1": "", "v2": EQUIVALENCIAS + ETIQUETA_VECINA, "v2.1": EQUIVALENCIAS + LEJANA, "v2.2": EQUIVALENCIAS + LEJANA + CALIDAD}
if VERSION not in EXTRA:
    raise SystemExit(f"VERSION={VERSION!r} no existe; usa una de {sorted(EXTRA)}")
C_LINE = "¿qué precio dice? ¿es regular, oferta o por volumen?\n"
assert C_LINE in PROMPT
PROMPT = PROMPT.replace(C_LINE, C_LINE + EXTRA[VERSION], 1)


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
             "product_group", "product_line")
UNITS = {"gramo": ("g", "kg"), "mililitro": ("ml", "L")}

MOBILE_PROMPT = PROMPT.replace(
    "Cada captura trae 3 fotos (fachada de la tienda, producto, etiqueta de precio en anaquel)",
    "Cada captura trae 2 fotos (producto y etiqueta de precio en anaquel)",
).replace(
    "¿la fachada corresponde a la cadena indicada? ", "",
).replace(
    "Aprueba solo si los tres frentes son claramente correctos.",
    "Evalúa solo la evidencia de las dos fotos. La API verifica la sucursal por separado. "
    "Aprueba si todos los frentes de las fotos son claramente correctos.",
)
CALIDADES = ["buena", "lejana", "borrosa", "tapada"]
if VERSION == "v2.2":
    SCHEMA["properties"]["calidad_fotos"] = {"type": "object", "additionalProperties": False, "required": ["producto", "etiqueta"],
                                             "properties": {k: {"type": "string", "enum": CALIDADES} for k in ("producto", "etiqueta")}}
    SCHEMA["required"].append("calidad_fotos")
MOBILE_SCHEMA = json.loads(json.dumps(SCHEMA))
MOBILE_CHECKS = ("sucursal", "producto", "codigo_barras", "evidencia_precio")
MOBILE_SCHEMA["properties"]["validaciones"]["properties"].pop("tienda_fachada")
MOBILE_SCHEMA["properties"]["validaciones"]["required"].remove("tienda_fachada")


def load_env(path=Path(__file__).with_name(".env")):
    if path.exists():
        for line in path.read_text().splitlines():
            k, sep, v = line.partition("=")
            if sep and not k.strip().startswith("#"):
                os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


def contenido(cap):
    """Contenido esperado legible y con su equivalencia (p. ej. "1100 ml (= 1.1 L)"): el modelo confundía L con ml y kg con g."""
    q, u = num(cap.get("unit_quantity_product")), cap.get("unit_product")
    if q is None:
        return None
    if u not in UNITS:
        return f"{q:g} {u}"
    small, big = UNITS[u]
    base = f"{q:g} {small}" + (f" (= {q / 1000:g} {big})" if q >= 1000 else "")
    if m := re.search(r"\(total:\s*([\d.,]+)\s*(g|gr|ml|kg|l)\b", str(cap.get("product_name") or ""), re.I):
        return f"{base} de masa drenada; {m.group(1)} {m.group(2).lower()} de contenido neto (cualquiera de los dos vale)"
    return base


def metadata(cap, version=None):
    meta = {k: cap.get(k) for k in META_KEYS}
    if (version or VERSION) == "v1":  # v1: unidad y cantidad crudas, como en la corrida original
        return {**meta, "unit_product": cap.get("unit_product"), "unit_quantity_product": cap.get("unit_quantity_product")}
    if (c := contenido(cap)) is not None:
        meta["contenido_esperado"] = c
    return meta


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


def barcodes(path):
    """Códigos de barras legibles en la foto (lectura local con zxing-cpp, cero tokens)."""
    return {b.text.lstrip("0") for b in zxingcpp.read_barcodes(read(path)) if b.text.isdigit()}


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


def ask_model(client, cap, base, *, mobile=False):
    content = []
    # ponytail: fachada a 512px (solo identifica la cadena), producto/etiqueta a 1024px para leer texto
    images = (("product", 1024), ("shelf", 1024))
    if not mobile:
        images = (("facade", 512), *images)
    for kind, side in images:
        content += [{"type": "text", "text": f"Foto {kind}:"},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                 "data": img_b64(base / cap[f"{kind}_file"], side)}}]
    content.append({"type": "text", "text": "Metadatos:\n" + json.dumps(metadata(cap), ensure_ascii=False)})
    r = client.messages.create(
        model=os.environ["MODEL"],
        max_tokens=16000,
        system=MOBILE_PROMPT if mobile else PROMPT,
        messages=[{"role": "user", "content": content}],
        output_config={"effort": os.environ.get("EFFORT", "low"),
                       "format": {"type": "json_schema", "schema": MOBILE_SCHEMA if mobile else SCHEMA}},
    )
    if r.stop_reason != "end_turn":
        raise RuntimeError(f"stop_reason={r.stop_reason}")
    return json.loads(next(b.text for b in r.content if b.type == "text")), r.usage.input_tokens + r.usage.output_tokens


def apply_rules(cap, r, label_codes=(), *, store_verified=None, ocr=None, geo=None):
    """Normaliza la respuesta del modelo al formato oficial (ver #foundry en la página del reto) y aplica reglas duras.
    ocr: función que devuelve el texto OCR de la etiqueta; si se pasa, aprobar exige que zxing o el OCR la corroboren.
    Se llama solo si todo lo demás ya pasó (es lo caro)."""
    v = r.get("validaciones") or {}
    res = {
        "capture_id": cap["capture_id"],
        "decision": r.get("decision") if r.get("decision") in DECISIONS else "revision_manual",
        "confidence_score": max(0.0, min(1.0, num(r.get("confidence_score")) or 0.0)),
        "reason_code": r.get("reason_code") if r.get("reason_code") in REASON_CODES else "DUDOSO",
        "validaciones": {k: "ok" if v.get(k) == "ok" else "falla"
                         for k in CHECKS if store_verified is None or k != "tienda_fachada"},
        "precio_detectado": num(r.get("precio_detectado")),
        "codigo_barras_detectado": r.get("codigo_barras_detectado"),
        "explicacion": str(r.get("explicacion") or ""),
    }
    # el código de barras lo escanea la app: se verifica contra el esperado, no con la foto
    same = str(cap.get("capture_barcode")) == str(cap.get("product_barcode"))
    if store_verified is not None:
        res["validaciones"] = {
            k: ("ok" if store_verified else "falla") if k == "sucursal" else res["validaciones"][k]
            for k in MOBILE_CHECKS
        }
        captured = str(cap.get("capture_barcode", "")).lstrip("0")
        expected = str(cap.get("product_barcode", "")).lstrip("0")
        same = captured.isdigit() and captured == expected
    res["validaciones"]["codigo_barras"] = "ok" if same else "falla"

    p0, cp0 = res["precio_detectado"], num(cap.get("capture_price"))
    precio_cuadra = p0 is not None and cp0 is not None and abs(p0 - cp0) <= 0.01
    # criterio del equipo: el precio regular cuenta como precio unitario (por pieza) salvo que la etiqueta diga otra
    # cosa; si el precio cuadra, que no traiga precio por kilo o por litro no es motivo de rechazo.
    if res["reason_code"] == "SIN_PRECIO_UNITARIO" and precio_cuadra and res["decision"] != "aprobada":
        res.update(decision="revision_manual", reason_code="DUDOSO", explicacion=f"{res['explicacion']} "
                   "[regla: el precio regular cuenta como precio unitario; la etiqueta solo no trae precio por kilo o litro]".strip())
    # criterio del equipo: si el producto trae masa drenada y contenido neto, con que uno coincida no se rechaza
    if (res["decision"] == "rechazada" and res["reason_code"] == "PRODUCTO_NO_COINCIDE"
            and "total:" in str(cap.get("product_name") or "").lower()):
        res.update(decision="revision_manual", reason_code="DUDOSO", explicacion=f"{res['explicacion']} "
                   "[regla: el producto trae masa drenada y contenido neto; uno puede coincidir, lo revisa un analista]".strip())

    # sin etiqueta o sin precio unitario es motivo oficial de rechazo (frente C), no de revisión. Solo sobre lo que
    # dijo el modelo: nuestras reglas de abajo también usan SIN_ETIQUETA_PRECIO, pero para mandar a revisión.
    if r.get("decision") == "revision_manual" and res["reason_code"] in ("SIN_PRECIO_UNITARIO", "SIN_ETIQUETA_PRECIO"):
        res["decision"] = "rechazada"

    # código leído en la etiqueta: si es el del producto, la etiqueta es de ese producto (prueba fuerte)
    exp = str(cap.get("product_barcode")).lstrip("0")
    label_ok = exp in label_codes
    if label_codes:
        res["codigo_barras_detectado"] = exp if label_ok else sorted(label_codes)[0]
    p, cp = res["precio_detectado"], num(cap.get("capture_price"))

    if geo and geo.get("estado") in ("otra_cadena", "coincide"):
        tienda, ocr_txt = geo["tienda"], "; confirmada por el texto de la fachada" if geo.get("por_ocr") else ""
        if geo["estado"] == "otra_cadena" and "tienda_fachada" in res["validaciones"]:
            res["validaciones"]["tienda_fachada"] = "falla"
            res["explicacion"] = (f"{res['explicacion']} [geo: el GPS ubica la foto a {tienda['distancia_m']} m "
                                  f"de {tienda['nombre']} ({tienda['cadena']}){ocr_txt}]").strip()
        elif geo["estado"] == "coincide":
            res["explicacion"] = (f"{res['explicacion']} [geo: sucursal {tienda['nombre']}, "
                                  f"{tienda['municipio']}, a {tienda['distancia_m']} m"
                                  f"{'; hay otra tienda igual o más cerca' if geo.get('ambigua') else ''}"
                                  f"{ocr_txt}]").strip()

    if ocr is not None:
        ocr = cache(ocr)  # la promoción y la verificación de abajo pueden pedirlo: el OCR corre una sola vez

    # el modelo dudó, pero no vio fallas, el precio cuadra y la etiqueta está corroborada (zxing u OCR local) → aprobar.
    # ponytail: en dev (simulado con respuestas reales) el costo bajó de 59 a 57 con 14/14 aprobadas bien.
    if (res["decision"] == "revision_manual" and p is not None and cp is not None and abs(p - cp) <= 0.01
            and all(x == "ok" for x in res["validaciones"].values())
            and cap.get("capture_store_name") not in NO_APPROVE_CHAINS):
        if label_ok:
            why_up = "el código de la etiqueta coincide con el producto"
        elif ocr is not None and ocr_local.confirms(cap, ocr()):
            why_up = "el OCR local leyó en la etiqueta el precio y el código del producto"
        else:
            why_up = None
        if why_up:
            res.update(decision="aprobada", confidence_score=max(res["confidence_score"], APPROVE_MIN), reason_code="OK",
                       explicacion=f"{res['explicacion']} [regla: el modelo dudó, pero {why_up}]".strip())

    # el modelo dudó por la calidad de la foto → rechazar para recapturar. v2.2 trae calidad_fotos (estructurado);
    # las versiones anteriores no, y ahí se busca la duda en el texto (DUDA_VISUAL, que confunde "no existe" con "no se ve").
    cal, code = r.get("calidad_fotos"), None
    if res["decision"] == "revision_manual" and r.get("decision") == "revision_manual":
        if isinstance(cal, dict):
            malas = {k: q for k, q in cal.items() if q in ("borrosa", "lejana", "tapada")}
            if "borrosa" in malas.values():
                code = "CAPTURA_BORROSA"
            elif "lejana" in malas.values():
                code = "CAPTURA_LEJANA"
            elif malas:
                code = "PRODUCTO_NO_VISIBLE" if "producto" in malas else "SIN_ETIQUETA_PRECIO"
        elif DUDA_VISUAL.search(str(r.get("explicacion") or "")):
            code = "CAPTURA_BORROSA" if re.search(r"borros|desenfoc", str(r.get("explicacion")), re.I) else "CAPTURA_LEJANA"
    if code:
        res.update(decision="rechazada", reason_code=code,
                   explicacion=f"{res['explicacion']} [regla: evidencia de mala calidad: se rechaza para volver a capturar]".strip())

    if res["decision"] == "aprobada":
        lo, hi = num(cap.get("min_product_price")), num(cap.get("max_product_price"))
        why = None
        if store_verified is False:
            why = ("DUDOSO", "la ubicación no permitió verificar la sucursal")
        elif cap.get("capture_store_name") in NO_APPROVE_CHAINS:
            why = ("DUDOSO", "la etiqueta de esta cadena trae código interno, no se puede verificar el producto")
        elif res["confidence_score"] < APPROVE_MIN:
            why = ("DUDOSO", "confianza baja")
        elif any(x != "ok" for x in res["validaciones"].values()):
            why = ("DUDOSO", "alguna validación no pasó")
        elif p is None:
            why = ("SIN_ETIQUETA_PRECIO", "no se leyó precio en la etiqueta")
        elif cp is not None and abs(p - cp) > 0.01:
            why = ("PRECIO_NO_COINCIDE", f"etiqueta {p} vs capturado {cp}")
        elif cp is not None and lo is not None and hi is not None and not lo <= cp <= hi:
            why = ("DUDOSO", f"precio {cp} fuera de rango {lo}-{hi}")
        # ponytail: en dev esta corroboración llevó la precisión de 92% a 100% (10/10); es lo que pasa el gate de 97%
        elif ocr is not None and not label_ok and not ocr_local.confirms(cap, ocr()):
            why = ("DUDOSO", "ni el código de barras ni el OCR local confirmaron precio y código en la etiqueta")
        if why:
            res.update(decision="revision_manual", reason_code=why[0], explicacion=f"{res['explicacion']} [regla: {why[1]}]".strip())
    return res


def geo_fachada(cap, base):
    """GPS de la fachada → sucursal DENUE (geolocalizar.py); el OCR de la fachada solo corre si el GPS quedó ambiguo."""
    if not geolocalizar.DENUE.exists():
        return None
    foto = base / cap["facade_file"]
    return geolocalizar.ubicar(foto, cap.get("capture_store_name"), ocr=lambda: ocr_local.read_facade(foto))


def decide(cap, base, client, *, store_verified=None, senales=None):
    """senales (opcional): dict que se llena con lo medido localmente, para la salida web descriptiva (salida_web.py)."""
    senales = {} if senales is None else senales
    senales["nitidez"] = {}
    for kind in ("shelf", "product"):
        s = blur_score(base / cap[f"{kind}_file"])
        senales["nitidez"][kind] = round(s, 1)
        if s < BLUR_REJECT[kind]:
            return apply_rules(cap, {"decision": "rechazada", "confidence_score": 0.9, "reason_code": "CAPTURA_BORROSA",
                                     "explicacion": f"Foto {kind} borrosa (nitidez {s:.0f} < {BLUR_REJECT[kind]:.0f})"},
                               store_verified=store_verified), 0
    geo = senales["geo"] = geo_fachada(cap, base) if store_verified is None else None
    label = barcodes(base / cap["shelf_file"])
    senales["codigos_etiqueta"] = sorted(label)
    if client is None:
        return apply_rules(cap, {"explicacion": "Sin modelo: pasó los filtros locales"}, label,
                           store_verified=store_verified, geo=geo), 0
    r, tokens = ask_model(client, cap, base, mobile=store_verified is not None)
    # ponytail: la app móvil (store_verified) aún no usa la corroboración OCR; agregarla si su servidor corre en Mac
    senales["modelo"] = True
    if r.get("calidad_fotos"):
        senales["calidad_fotos"] = r["calidad_fotos"]
    ocr = None if store_verified is not None else cache(lambda: ocr_local.read_label(cap, base / cap["shelf_file"]))
    res = apply_rules(cap, r, label, store_verified=store_verified, ocr=ocr, geo=geo)
    if ocr is not None and ocr.cache_info().currsize:  # solo si la regla llegó a necesitar el OCR
        senales["ocr"] = ocr()
    return res, tokens


def safe_decide(cap, base, client, senales=None):
    try:
        return decide(cap, base, client, senales=senales)
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
        sen = {c["capture_id"]: {} for c in todo}
        rows = list(ex.map(lambda c: safe_decide(c, base, client, sen[c["capture_id"]]), todo))
    results, tokens = [r for r, _ in rows], sum(t for _, t in rows)
    Path(outp).parent.mkdir(parents=True, exist_ok=True)
    Path(outp).write_text(json.dumps(results, ensure_ascii=False, indent=1))  # salida oficial del hackathon
    import salida_web  # salida para la página: campos de capturas.json + resultado + hallazgos (local, trae datos de 3B)
    web = [salida_web.registro(c, r, sen[c["capture_id"]]) for c, r in zip(todo, results)]
    Path(outp).with_suffix(".web.json").write_text(json.dumps(web, ensure_ascii=False, indent=1))
    print(f"{len(results)} capturas · {tokens} tokens ({tokens / len(results):.0f}/captura) · modelo: {'sí' if client else 'no'} → {outp}")
    n, s = ocr_local.stats["n"], ocr_local.stats["seconds"]
    print(f"OCR local: {n} etiquetas" + (f" · {s / n:.1f}s/etiqueta" if n else "") + ("" if ocr_local.available() else " (no disponible: sin mlx-vlm)"))
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
