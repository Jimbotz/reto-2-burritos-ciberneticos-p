"""OCR local de etiquetas con Unlimited-OCR 4bit (MLX, Apple Silicon). Cero tokens; las imágenes no salen de la máquina.

Si mlx-vlm no está instalado (fuera de Mac), available() es False, read_text() devuelve "" y la regla de
corroboración simplemente no aprueba sin zxing: falla hacia revisión manual, nunca hacia aprobar.
"""
import re, threading, time, unicodedata
from concurrent.futures import ThreadPoolExecutor
from functools import cache

REPO = "sahilchachra/unlimited-ocr-4bit-mlx"  # ganó en estudio_ocr.py: más precios leídos y más rápido que 8bit
PROMPT = "<image>Free OCR."
MAX_TOKENS = 1024  # ver estudio: 17 de 100 etiquetas normales pasan de 450 tokens, no recortar a ciegas

# --- copiado de Unlimited-OCR/benchmark/run_benchmark_mlx.py (detok + anti-repetición) ---
def _byte_decoder():
    bs = list(range(ord("!"), ord("~") + 1)) + list(range(ord("¡"), ord("¬") + 1)) + list(range(ord("®"), ord("ÿ") + 1))
    cs, n = bs[:], 0
    for b in range(256):
        if b not in bs:
            bs.append(b); cs.append(256 + n); n += 1
    return {chr(c): b for b, c in zip(bs, cs)}


_U2B = _byte_decoder()


def detok(text):
    """mlx-vlm 0.6.3 devuelve BPE byte-level crudo para este modelo (Ġ=espacio, Ċ=salto)."""
    return bytearray(_U2B[c] for c in text if c in _U2B).decode("utf-8", errors="replace")


def make_no_repeat_ngram(n):
    import mlx.core as mx

    def proc(tokens, logits):
        t = tokens.tolist()
        if len(t) < n:
            return logits
        prefix = tuple(t[-(n - 1):])
        banned = {t[i + n - 1] for i in range(len(t) - n + 1) if tuple(t[i:i + n - 1]) == prefix}
        if banned:
            logits[:, mx.array(list(banned))] = -float("inf")
        return logits

    return proc
# --- fin de lo copiado ---


def clean(text):
    text = re.sub(r"<\|det\|>.*?<\|/det\|>", " ", text)  # cajas con coordenadas: no son precios ni códigos
    # centavos en superíndice: "$25\( ^{50} \)" o "25^{50}" → "25.50"
    return re.sub(r"\s*\\\(\s*\^\{?(\d{1,2})\}?\s*\\\)|\^\{(\d{1,2})\}", lambda m: "." + (m.group(1) or m.group(2)), text)


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", s)


PRICE_RE = re.compile(r"(\$)?\s*(\d{1,4})(?:\s?[.,]\s?(\d{1,2}))?(?!\d)")


def prices(text, strict):
    """Números que parecen precio. strict: solo con '$' o con centavos (evita '30' de '30 pzas')."""
    out = set()
    for dollar, ent, dec in PRICE_RE.findall(clean(text)):
        if strict and not (dollar or dec):
            continue
        out.add(round(float(f"{ent}.{(dec or '0').ljust(2, '0')}"), 2))
    return out


def reads_price(cap, text):
    return round(float(cap["capture_price"]), 2) in prices(text, strict=True)


def reads_code(cap, text):
    return norm(cap["product_barcode"])[-6:] in norm(clean(text))


def confirms(cap, text):
    """La etiqueta trae el precio capturado Y los últimos 6 dígitos del código del producto."""
    return reads_price(cap, text) and reads_code(cap, text)


@cache
def available():
    try:
        import mlx_vlm  # noqa: F401
        return True
    except ImportError:
        return False


_pool = ThreadPoolExecutor(max_workers=1)  # MLX: el modelo se carga y se usa siempre en el mismo hilo
_model = None
stats = {"n": 0, "seconds": 0.0}
_lock = threading.Lock()


def _run(path):
    global _model
    from mlx_vlm import generate, load
    if _model is None:
        _model = load(REPO)
    t = time.time()
    res = generate(*_model, prompt=PROMPT, image=str(path), max_tokens=MAX_TOKENS, verbose=False,
                   repetition_penalty=1.1, repetition_context_size=64, logits_processors=[make_no_repeat_ngram(35)])
    with _lock:
        stats["n"] += 1
        stats["seconds"] += time.time() - t
    return detok(res.text)


def read_text(path):
    """Texto de la imagen; "" si no hay OCR disponible. Seguro de llamar desde varios hilos."""
    return _pool.submit(_run, path).result() if available() else ""


DET_RE = re.compile(r"<\|det\|>\w+ \[(\d+), (\d+), (\d+), (\d+)\]<\|/det\|>([^<\n]*)")


def crop_box(text, margin=0.08):
    """Caja (0–1) que une las regiones de texto con números (precio, código); None si no hay o ya es casi toda la foto."""
    boxes = [tuple(int(v) / 999 for v in m[:4]) for m in DET_RE.findall(text) if any(ch.isdigit() for ch in m[4])]
    if not boxes:
        return None
    x1, y1 = max(0, min(b[0] for b in boxes) - margin), max(0, min(b[1] for b in boxes) - margin)
    x2, y2 = min(1, max(b[2] for b in boxes) + margin), min(1, max(b[3] for b in boxes) + margin)
    return None if (x2 - x1) * (y2 - y1) > 0.8 else (x1, y1, x2, y2)


def read_label(cap, path):
    """1a lectura de la etiqueta; si no corrobora, 2a lectura del recorte ampliado de la zona con números
    (estudio en dev: 10 → 12 válidas corroboradas, 0 no válidas). Devuelve el texto que corroboró, o el de la 1a."""
    text = read_text(path)
    if confirms(cap, text) or not (box := crop_box(text)):
        return text
    import tempfile
    import cv2
    img = cv2.imread(str(path))
    h, w = img.shape[:2]
    crop = img[int(box[1] * h):int(box[3] * h), int(box[0] * w):int(box[2] * w)]
    s = 1280 / max(crop.shape[:2])  # lado mayor a 1280 px
    crop = cv2.resize(crop, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC if s > 1 else cv2.INTER_AREA)
    with tempfile.NamedTemporaryFile(suffix=".jpg") as f:  # local y se borra al salir
        cv2.imwrite(f.name, crop)
        second = read_text(f.name)
    return second if confirms(cap, second) else text
