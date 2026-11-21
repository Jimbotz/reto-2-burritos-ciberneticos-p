"""Estudio: ¿Unlimited-OCR (local, MLX en Apple Silicon) ayuda a validar etiquetas y productos?

    .venv/bin/python estudio_ocr.py run --mode 4bit --kinds shelf --caps data/muestra20.json
    .venv/bin/python estudio_ocr.py report
Guarda out/ocr_<mode>.jsonl (una línea por imagen) y reanuda si se corta. Todo local: nada sale de la máquina.
"""
import argparse, json, statistics as st, time
from collections import defaultdict
from pathlib import Path

from ocr_local import crop_box, detok, make_no_repeat_ngram, norm, reads_code, reads_price, prices

REPOS = {"4bit": "sahilchachra/unlimited-ocr-4bit-mlx", "8bit": "sahilchachra/unlimited-ocr-8bit-mlx"}
MAX_TOKENS = 1024


def run(mode, kinds, caps_path, prompt):
    from mlx_vlm import load, generate
    caps = json.loads(Path(caps_path).read_text())
    base, out = Path(caps_path).parent, Path(f"out/ocr_{mode}.jsonl")
    out.parent.mkdir(exist_ok=True)
    done = {(r["capture_id"], r["kind"], r["prompt"]) for r in map(json.loads, out.open())} if out.exists() else set()
    t = time.time()
    model, processor = load(REPOS[mode])
    print(f"[{mode}] modelo cargado en {time.time() - t:.1f}s", flush=True)
    with out.open("a") as fh:
        for c in caps:
            for k in kinds:
                if (c["capture_id"], k, prompt) in done:
                    continue
                t0 = time.time()
                row = dict(capture_id=c["capture_id"], kind=k, prompt=prompt)
                try:
                    res = generate(model, processor, prompt=f"<image>{prompt}", image=str(base / c[f"{k}_file"]),
                                   max_tokens=MAX_TOKENS, verbose=False, repetition_penalty=1.1, repetition_context_size=64,
                                   logits_processors=[make_no_repeat_ngram(35)])
                    row.update(seconds=round(time.time() - t0, 2), tokens=res.generation_tokens,
                               peak_gb=round(res.peak_memory, 2), text=detok(res.text))
                except Exception as e:
                    row.update(seconds=round(time.time() - t0, 2), tokens=0, error=f"{type(e).__name__}: {e}", text="")
                fh.write(json.dumps(row, ensure_ascii=False) + "\n"); fh.flush()
                print(f"[{mode}] {c['capture_id']} {k:7} {row['seconds']:5.1f}s {row['tokens']:4} tok", flush=True)


def analyze(caps, rows):
    """Por captura: ¿leyó el precio capturado en la etiqueta? ¿los dígitos del código? ¿la marca en el producto?"""
    byid = {c["capture_id"]: c for c in caps}
    res = {}
    for r in rows:
        c = byid[r["capture_id"]]
        a = res.setdefault(r["capture_id"], {})
        if r["kind"] == "shelf":
            a.update(precio_estricto=reads_price(c, r["text"]), precio=round(float(c["capture_price"]), 2) in prices(r["text"], False),
                     codigo=reads_code(c, r["text"]))
        else:
            a.update(marca=norm(c["capture_brand"]) in norm(r["text"]))
    return res


def desc_words(cap):
    """Palabras significativas (≥4 letras) del producto esperado y la marca, sin acentos."""
    import re, unicodedata
    s = unicodedata.normalize("NFKD", f"{cap['product_name']} {cap['capture_brand']}").encode("ascii", "ignore").decode().lower()
    return {w for w in re.findall(r"[a-z]{4,}", s)}


def reads_desc(cap, text, k=2):
    """La etiqueta trae el precio capturado y ≥k palabras de la descripción (para etiquetas sin dígitos del código)."""
    import re, unicodedata
    from ocr_local import clean
    t = set(re.findall(r"[a-z]{4,}", unicodedata.normalize("NFKD", clean(text)).encode("ascii", "ignore").decode().lower()))
    return reads_price(cap, text) and len(desc_words(cap) & t) >= min(k, len(desc_words(cap)))


def run_crop(caps_path="data/capturas.json"):
    """Segunda lectura sobre el recorte ampliado de la zona con números. Solo donde la 1a lectura no corroboró."""
    import cv2
    import ocr_local
    caps = json.loads(Path(caps_path).read_text())
    txt, out = shelf_texts(), Path("out/ocr_4bit_crop.jsonl")
    done = {r["capture_id"] for r in map(json.loads, out.open())} if out.exists() else set()
    Path("out/crops").mkdir(parents=True, exist_ok=True)
    with out.open("a") as fh:
        for c in caps:
            i = c["capture_id"]
            if i in done or i not in txt or ocr_local.confirms(c, txt[i]) or not (box := crop_box(txt[i])):
                continue
            img = cv2.imread(f"data/{c['shelf_file']}")
            h, w = img.shape[:2]
            crop = img[int(box[1] * h):int(box[3] * h), int(box[0] * w):int(box[2] * w)]
            s = 1280 / max(crop.shape[:2])  # ampliar (o reducir) el recorte a 1280 px de lado mayor
            crop = cv2.resize(crop, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC if s > 1 else cv2.INTER_AREA)
            path = Path(f"out/crops/{i}.jpg")
            cv2.imwrite(str(path), crop)
            t0 = time.time()
            text = ocr_local.read_text(path)
            row = dict(capture_id=i, seconds=round(time.time() - t0, 2), box=[round(v, 3) for v in box], text=text)
            fh.write(json.dumps(row, ensure_ascii=False) + "\n"); fh.flush()
            print(f"[crop] {i} {row['seconds']:5.1f}s confirma={ocr_local.confirms(c, text)}", flush=True)


def shelf_texts(path="out/ocr_4bit.jsonl", prompt="Free OCR."):
    """capture_id → texto OCR de la etiqueta (para simular sin volver a correr el OCR)."""
    return {r["capture_id"]: r["text"] for r in map(json.loads, open(path)) if r["prompt"] == prompt and r["kind"] == "shelf"}


def report():
    caps = json.loads(Path("data/capturas.json").read_text())
    cat = lambda c: c["decision_esperada"] + (f" · {c['motivo_rechazo']}" if c["motivo_rechazo"] else "")
    byid = {c["capture_id"]: c for c in caps}
    for f in sorted(Path("out").glob("ocr_*.jsonl")):
        allrows = [json.loads(l) for l in f.open()]
        for prompt in sorted({r["prompt"] for r in allrows}):
            rows = [r for r in allrows if r["prompt"] == prompt]
            secs = [r["seconds"] for r in rows if not r.get("error")]
            print(f"\n=== {f.stem} · prompt '{prompt}' · {len(rows)} imágenes")
            if secs:
                q = st.quantiles(secs, n=10) if len(secs) > 1 else [secs[0]] * 9
                print(f"tiempo/imagen: media {st.mean(secs):.1f}s · mediana {st.median(secs):.1f}s · p90 {q[8]:.1f}s · máx {max(secs):.1f}s"
                      f" · errores {sum(1 for r in rows if r.get('error'))} · topó {MAX_TOKENS} tok: {sum(r['tokens'] >= MAX_TOKENS for r in rows)}"
                      f" · vacías: {sum(len(r['text'].strip()) < 3 for r in rows)}")
            a = analyze(caps, rows)
            groups = defaultdict(list)
            for i, x in a.items():
                groups[cat(byid[i])].append(x)
            cols = [k for k in ("precio_estricto", "precio", "codigo", "marca") if any(k in x for v in groups.values() for x in v)]
            print(f"{'categoría':45} {'n':>3}  " + "  ".join(f"{k:>15}" for k in cols))
            for g, xs in sorted(groups.items()):
                cells = []
                for k in cols:
                    v = [x[k] for x in xs if k in x]
                    cells.append(f"{sum(v):>3}/{len(v):<3} {sum(v) / len(v):5.0%}" if v else f"{'—':>15}")
                print(f"{g:45} {len(xs):>3}  " + "  ".join(f"{c:>15}" for c in cells))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--mode", choices=tuple(REPOS), required=True)
    r.add_argument("--kinds", nargs="+", default=["shelf"], choices=["shelf", "product", "facade"])
    r.add_argument("--caps", default="data/muestra20.json")
    r.add_argument("--prompt", default="Free OCR.")
    sub.add_parser("report")
    a = ap.parse_args()
    if a.cmd == "run":
        run(a.mode, a.kinds, a.caps, a.prompt)
    else:
        report()
