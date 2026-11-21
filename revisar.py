"""Página local para revisar capturas a mano.

Uso:
    python revisar.py           → errores del modelo (aprobó lo que no debía)       · notas en out/notas.json
    python revisar.py manual    → las que el motor manda a revisión manual, por motivo · notas en out/notas_manual.json
    python revisar.py final     → las 100 del motor final (out/sim_final.json) por decisión · notas en out/notas_final.json
Abre http://127.0.0.1:8765. Todo corre en tu máquina: las imágenes de 3B no salen de aquí.
"""
import html, json, re, sys, webbrowser
from collections import Counter, defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parent
DATA, OUT = ROOT / "data", ROOT / "out"
MODE = next((m for m in ("manual", "final") if m in sys.argv[1:]), "errores")
NOTES = OUT / {"manual": "notas_manual.json", "final": "notas_final.json"}.get(MODE, "notas.json")
RESULTS = OUT / {"manual": "sim_ocr.json", "final": "sim_final.json"}.get(MODE, "local.json")
PORT = 8765
HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
IMG_RE = re.compile(r"CAP-\d+_(facade|product|shelf)\.jpg")
TAGS = ["Foto lejana", "Foto borrosa", "Etiqueta ilegible o cortada", "Precio no coincide", "Producto distinto o contratipo",
        "Descripción incompleta", "Fachada no corresponde", "Foto de otra pantalla", "Parece válida", "Otro"]
DECISIONES = (("aprobar", "Aprobar"), ("rechazar", "Rechazar"), ("revision", "Dejar en revisión"))
ORDEN = {"aprobada": 0, "rechazada": 1, "revision_manual": 2}


def load(p, default=None):
    return json.loads(Path(p).read_text()) if Path(p).exists() else default


def why_manual(r):
    """Agrupa por la regla que la mandó a revisión (la última [regla: …]) o por el motivo del modelo."""
    tags = re.findall(r"\[regla: (.*?)\]", r["explicacion"])
    t = tags[-1] if tags else ""
    if "cadena" in t:
        return "Regla: cadena con código interno en la etiqueta (Walmart / Bodega Aurrera / Bara)"
    if "OCR" in t:
        return "Regla: el modelo aprobó, pero ni zxing ni el OCR confirmaron la etiqueta"
    if "confianza" in t:
        return "Regla: el modelo aprobó con confianza baja"
    if "validación" in t:
        return "Regla: el modelo aprobó, pero marcó alguna validación en falla"
    if t:
        return f"Regla: {t}"
    return f"El modelo mandó a revisión ({r['reason_code']})"


def card(c, r, badge="", extra=(), radios=False):
    e = lambda x: html.escape(str(x if x is not None else "—"))
    imgs = "".join(
        f'<figure><a href="/img/{Path(c[k + "_file"]).name}" target="_blank"><img loading="lazy" src="/img/{Path(c[k + "_file"]).name}"></a>'
        f"<figcaption>{label}</figcaption></figure>"
        for k, label in (("facade", "Fachada"), ("product", "Producto"), ("shelf", "Etiqueta"))
    )
    rows = [
        *extra,
        ("Tienda", c["capture_store_name"]), ("Producto esperado", c["product_name"]), ("Marca capturada", c["capture_brand"]),
        ("Contenido", f'{c["unit_quantity_product"]} {c["unit_product"]}'),
        ("Precio capturado", f'${c["capture_price"]}  (rango ${c["min_product_price"]}–${c["max_product_price"]})'),
        ("Precio que leyó el modelo", r["precio_detectado"]),
        ("Validaciones del modelo", " · ".join(f"{k}: {x}" for k, x in r["validaciones"].items())),
    ]
    tags = "".join(f'<label><input type="checkbox" value="{e(t)}"> {e(t)}</label>' for t in TAGS)
    dec = ('<div class="dec"><b>¿Qué debió hacer el motor?</b> ' + "".join(
        f'<label><input type="radio" name="d-{e(c["capture_id"])}" value="{v}"> {t}</label>' for v, t in DECISIONES) + "</div>") if radios else ""
    return f"""
<article class="card" id="{e(c['capture_id'])}">
  <header><b>{e(c['capture_id'])}</b>{badge}
    <span>Analista: <b>{e(c['decision_esperada'])}</b>{(' · ' + e(c['motivo_rechazo'])) if c['motivo_rechazo'] else ''}</span>
    <span>Motor: <b>{e(r['decision'])}</b> (confianza {r['confidence_score']:.2f}, {e(r['reason_code'])})</span></header>
  <div class="imgs">{imgs}</div>
  <table>{''.join(f'<tr><th>{e(k)}</th><td>{e(x)}</td></tr>' for k, x in rows)}</table>
  <p class="expl"><b>Explicación del modelo:</b> {e(r['explicacion'])}</p>
  {dec}
  <div class="tags">{tags}</div>
  <textarea placeholder="¿Por qué quedó así? ¿Qué se ve en las fotos?"></textarea>
</article>"""


def page_errores(caps, res):
    sample = {c["capture_id"] for c in load(DATA / "muestra20.json", [])}
    exp = lambda r: caps[r["capture_id"]]["decision_esperada"]
    groups = [
        ("Analista: revisión manual · Modelo: aprobada", "¿Por qué el analista no la aprobó? Esta es la pregunta clave.",
         [r for r in res if r["decision"] == "aprobada" and exp(r) == "revision_manual"]),
        ("Analista: rechazada · Modelo: aprobada", "El motivo del analista está arriba de cada una: ¿se nota en las fotos?",
         [r for r in res if r["decision"] == "aprobada" and exp(r) == "rechazada"]),
        ("Para comparar · Analista y modelo: aprobada", "Capturas válidas: ¿qué tienen estas que las de arriba no?",
         [r for r in res if r["decision"] == "aprobada" and exp(r) == "aprobada" and r["capture_id"] in sample]),
    ]
    badge = lambda i: ' <span class="badge">muestra20</span>' if i in sample else ""
    return "", "".join(
        f'<h2>{html.escape(t)} <small>({len(rs)})</small></h2><p class="hint">{html.escape(h)}</p>'
        + "".join(card(caps[r["capture_id"]], r, badge(r["capture_id"])) for r in rs)
        for t, h, rs in groups
    )


def page_manual(caps, res):
    from ocr_local import reads_code, reads_price
    texts = {r["capture_id"]: r["text"] for r in map(json.loads, (OUT / "ocr_4bit.jsonl").open())
             if r["prompt"] == "Free OCR." and r["kind"] == "shelf"} if (OUT / "ocr_4bit.jsonl").exists() else {}
    manual = [r for r in res if r["decision"] == "revision_manual"]
    groups = defaultdict(list)
    for r in manual:
        groups[why_manual(r)].append(r)
    count = Counter(caps[r["capture_id"]]["decision_esperada"] for r in manual)
    intro = (f'<p class="sum"><b>{len(manual)} capturas en revisión manual</b> (cuestan {len(manual)} puntos). Según el analista: '
             f'<b>{count["aprobada"]}</b> eran válidas (aprobarlas ahorraría {count["aprobada"]} pts), '
             f'<b>{count["rechazada"]}</b> eran rechazos (rechazarlas ahorraría {count["rechazada"]} pts) y '
             f'<b>{count["revision_manual"]}</b> el analista también las mandó a revisión.</p>'
             '<p class="hint">Recuerda la tabla: aprobar mal cuesta 10, rechazar una válida cuesta 3, revisión cuesta 1. '
             'Marca qué debió hacer el motor y, si puedes, qué señal en las fotos lo habría delatado.</p>')

    def extra(r):
        c, t = caps[r["capture_id"]], texts.get(r["capture_id"])
        z = r.get("codigo_barras_detectado")
        exp = str(c["product_barcode"]).lstrip("0")
        return [("Por qué quedó en revisión", why_manual(r)),
                ("OCR local de la etiqueta", "sin datos" if t is None else
                 f"precio {'✓ leído' if reads_price(c, t) else '✗ no leído'} · dígitos del código {'✓ leídos' if reads_code(c, t) else '✗ no leídos'}"),
                ("Código en la etiqueta (zxing)", "no se leyó" if not z else f"{z} {'✓ = producto' if str(z).lstrip('0') == exp else '✗ distinto al producto'}")]

    body = ""
    for g, rs in sorted(groups.items(), key=lambda x: -len(x[1])):
        rs.sort(key=lambda r: (ORDEN[caps[r["capture_id"]]["decision_esperada"]], r["capture_id"]))
        n = Counter(caps[r["capture_id"]]["decision_esperada"] for r in rs)
        body += (f'<h2>{html.escape(g)} <small>({len(rs)})</small></h2><p class="hint">Analista: '
                 f'{n["aprobada"]} aprobadas · {n["rechazada"]} rechazadas · {n["revision_manual"]} revisión manual</p>'
                 + "".join(card(caps[r["capture_id"]], r, extra=extra(r), radios=True) for r in rs))
    return intro, body


def page_final(caps, res):
    from ocr_local import confirms, reads_code, reads_price
    from validat3b import REASON_CODES, cost
    rows = lambda p: [json.loads(l) for l in (OUT / p).open()] if (OUT / p).exists() else []
    first = {r["capture_id"]: r["text"] for r in rows("ocr_4bit.jsonl") if r["prompt"] == "Free OCR." and r["kind"] == "shelf"}
    crop = {r["capture_id"]: r["text"] for r in rows("ocr_4bit_crop.jsonl")}
    SAME = {"aprobada": "aprobada", "rechazada": "rechazada", "revision_manual": "revision_manual"}
    t = Counter((r["decision"], caps[r["capture_id"]]["decision_esperada"]) for r in res)
    total = sum(cost(caps[r["capture_id"]]["decision_esperada"], r["decision"]) for r in res)
    th = "".join(f"<th>{h}</th>" for h in ("Motor", "Total", "Analista: aprobada", "rechazada", "revisión"))
    tr = "".join(f"<tr><td><b>{d}</b></td><td>{sum(t[(d, a)] for a in SAME)}</td>" + "".join(f"<td>{t[(d, a)]}</td>" for a in SAME) + "</tr>"
                 for d in SAME)
    intro = (f'<div class="sum"><b>Motor final · costo {total}</b> (todo a revisión = {len(res)}). '
             f'Simulado con las respuestas reales del prompt original + reglas + OCR local (sin tokens).'
             f'<table class="mx"><tr>{th}</tr>{tr}</table></div>'
             '<p class="hint">En cada grupo van primero las que no coinciden con el analista. Marca qué debió hacer el motor.</p>')

    def why(r):
        tags = re.findall(r"\[regla: (.*?)\]", r["explicacion"])
        if r["decision"] == "revision_manual":
            return why_manual(r)
        if r["decision"] == "aprobada":
            return tags[-1] if tags else "El modelo aprobó y la etiqueta quedó corroborada (zxing u OCR local)"
        return f"{r['reason_code']}: {REASON_CODES.get(r['reason_code'], '')}"

    def extra(r):
        c, i = caps[r["capture_id"]], r["capture_id"]
        tx = first.get(i)
        if tx is not None and not confirms(c, tx) and i in crop and confirms(c, crop[i]):
            tx, src = crop[i], " (2a lectura, recorte)"
        else:
            src = ""
        z, exp = r.get("codigo_barras_detectado"), str(c["product_barcode"]).lstrip("0")
        return [("Por qué esta decisión", why(r)),
                ("OCR local de la etiqueta" + src, "sin datos" if tx is None else
                 f"precio {'✓' if reads_price(c, tx) else '✗'} · dígitos del código {'✓' if reads_code(c, tx) else '✗'}"),
                ("Código en la etiqueta (zxing)", "no se leyó" if not z else f"{z} {'✓ = producto' if str(z).lstrip('0') == exp else '✗ distinto'}")]

    body = ""
    for d, title in (("aprobada", "Aprobadas"), ("rechazada", "Rechazadas"), ("revision_manual", "Revisión manual")):
        rs = sorted((r for r in res if r["decision"] == d),
                    key=lambda r: (caps[r["capture_id"]]["decision_esperada"] == d, ORDEN[caps[r["capture_id"]]["decision_esperada"]], r["capture_id"]))
        n = Counter(caps[r["capture_id"]]["decision_esperada"] for r in rs)
        body += (f'<h2>{title} <small>({len(rs)})</small></h2><p class="hint">Analista: {n["aprobada"]} aprobadas · '
                 f'{n["rechazada"]} rechazadas · {n["revision_manual"]} revisión manual</p>'
                 + "".join(card(caps[r["capture_id"]], r, extra=extra(r), radios=True) for r in rs))
    return intro, body


def page(cadena=None):
    caps = {c["capture_id"]: c for c in load(DATA / "capturas.json")}
    res = sorted(load(RESULTS), key=lambda r: r["capture_id"])
    if cadena:  # /?cadena=Neto → solo esa cadena
        res = [r for r in res if caps[r["capture_id"]]["capture_store_name"].lower() == cadena.lower()]
    intro, body = {"manual": page_manual, "final": page_final}.get(MODE, page_errores)(caps, res)
    return (PAGE.replace("{{BODY}}", body).replace("{{INTRO}}", intro)
            .replace("{{RESULTS}}", html.escape(RESULTS.name)).replace("{{NOTES}}", html.escape(NOTES.name)))


PAGE = """<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Revisión Validat3B</title><style>
body{font:15px/1.45 system-ui,sans-serif;margin:0 auto;max-width:1200px;padding:16px;background:#f6f6f4;color:#1d1d1b}
.top{position:sticky;top:0;background:#f6f6f4;padding:8px 0;border-bottom:1px solid #ddd;z-index:1;display:flex;gap:16px;align-items:center}
h2{margin:32px 0 4px}.hint{margin:0 0 12px;color:#555}.sum{background:#fff8e1;border:1px solid #f0d58a;border-radius:8px;padding:10px}
.mx{border-collapse:collapse;margin-top:8px;width:auto}.mx td,.mx th{padding:2px 10px;border-bottom:1px solid #e5d9a8;text-align:right}.mx td:first-child{text-align:left}
.card{background:#fff;border:1px solid #ddd;border-radius:10px;padding:14px;margin:0 0 18px}
.card header{display:flex;flex-wrap:wrap;gap:6px 18px;margin-bottom:10px}
.badge{background:#1d4ed8;color:#fff;border-radius:6px;padding:0 6px;font-size:12px}
.imgs{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
figure{margin:0}img{width:100%;height:340px;object-fit:contain;background:#222;border-radius:6px}
figcaption{text-align:center;font-size:13px;color:#555}
table{border-collapse:collapse;margin:10px 0;width:100%}th{text-align:left;width:240px;color:#555;font-weight:500}
th,td{padding:3px 6px;border-bottom:1px solid #eee;vertical-align:top}
.expl{background:#f3f3f0;padding:8px;border-radius:6px}
.dec{display:flex;flex-wrap:wrap;gap:6px 16px;margin:8px 0;padding:8px;background:#eef4ff;border-radius:6px}
.tags{display:flex;flex-wrap:wrap;gap:4px 14px;margin:8px 0}
textarea{width:100%;box-sizing:border-box;min-height:70px;font:inherit;padding:8px}
.card.done{border-color:#16a34a}
@media(max-width:700px){.imgs{grid-template-columns:1fr}img{height:260px}}
</style></head><body>
<div class="top"><b>Revisión Validat3B</b><span>Resultados: {{RESULTS}}</span><span id="prog"></span><span id="st"></span></div>
<p>Marca lo que veas en cada captura. Se guarda solo en <code>out/{{NOTES}}</code>. Clic en una foto para verla completa.</p>
{{INTRO}}
{{BODY}}
<script>
const cards = [...document.querySelectorAll('.card')];
const st = document.getElementById('st'), prog = document.getElementById('prog');
function collect(){const o={};cards.forEach(c=>{const tags=[...c.querySelectorAll('input[type=checkbox]:checked')].map(x=>x.value),
  nota=c.querySelector('textarea').value.trim(),d=c.querySelector('input[type=radio]:checked'),decision=d?d.value:'';
  const has=!!(tags.length||nota||decision);c.classList.toggle('done',has);if(has)o[c.id]={tags,nota,decision};});
  prog.textContent=`${Object.keys(o).length} de ${cards.length} revisadas`;return o;}
async function save(){try{const r=await fetch('/notas',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(collect())});
  st.textContent=r.ok?'Guardado '+new Date().toLocaleTimeString():'Error al guardar';}catch(e){st.textContent='Error: ¿se cerró el servidor?';}}
let t;['input','change'].forEach(ev=>document.addEventListener(ev,()=>{clearTimeout(t);t=setTimeout(save,400);}));
fetch('/notas').then(r=>r.json()).then(n=>{cards.forEach(c=>{const x=n[c.id];if(!x)return;
  c.querySelectorAll('input[type=checkbox]').forEach(i=>i.checked=(x.tags||[]).includes(i.value));
  c.querySelectorAll('input[type=radio]').forEach(i=>i.checked=i.value===x.decision);
  c.querySelector('textarea').value=x.nota||'';});collect();});
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def reply(self, code, body, ctype="text/plain; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def local_only(self):  # bloquea DNS rebinding y POSTs desde otras páginas del navegador
        origin = self.headers.get("Origin")
        ok = self.headers.get("Host") in HOSTS and (origin is None or origin.split("://")[-1] in HOSTS)
        if not ok:
            self.reply(403, b"solo local")
        return ok

    def do_GET(self):
        if not self.local_only():
            return
        path, _, query = self.path.partition("?")
        if path == "/":
            cadena = (parse_qs(query).get("cadena") or [None])[0]
            return self.reply(200, page(cadena).encode(), "text/html; charset=utf-8")
        if self.path == "/notas":
            return self.reply(200, json.dumps(load(NOTES, {}), ensure_ascii=False).encode(), "application/json")
        name = self.path.removeprefix("/img/")
        if self.path.startswith("/img/") and IMG_RE.fullmatch(name) and (DATA / "imagenes" / name).exists():
            return self.reply(200, (DATA / "imagenes" / name).read_bytes(), "image/jpeg")
        self.reply(404, b"no existe")

    def do_POST(self):
        if not self.local_only():
            return
        n = int(self.headers.get("Content-Length") or 0)
        if self.path != "/notas" or n > 1_000_000:
            return self.reply(400, b"no")
        try:
            notas = json.loads(self.rfile.read(n))
            assert isinstance(notas, dict)
        except Exception:
            return self.reply(400, b"json invalido")
        NOTES.parent.mkdir(exist_ok=True)
        NOTES.write_text(json.dumps(notas, ensure_ascii=False, indent=1))
        self.reply(200, b"ok")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    page()  # falla aquí, no en el navegador, si faltan datos o resultados
    url = f"http://127.0.0.1:{PORT}/"
    print(f"Revisión ({MODE}) en {url}  (Ctrl+C para cerrar) · notas → {NOTES.relative_to(ROOT)}")
    webbrowser.open(url)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
