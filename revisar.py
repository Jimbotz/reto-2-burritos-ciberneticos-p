"""Página local para revisar a mano las capturas donde el modelo se equivocó.

Uso:  python revisar.py [out/local.json]   → abre http://127.0.0.1:8765
Las notas se guardan solas en out/notas.json. Todo corre en tu máquina: las imágenes de 3B no salen de aquí.
"""
import html, json, re, sys, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA, NOTES = ROOT / "data", ROOT / "out" / "notas.json"
PORT = 8765
HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
IMG_RE = re.compile(r"CAP-\d+_(facade|product|shelf)\.jpg")
TAGS = ["Foto lejana", "Foto borrosa", "Etiqueta ilegible o cortada", "Precio no coincide", "Producto distinto o contratipo",
        "Descripción incompleta", "Fachada no corresponde", "Foto de otra pantalla", "Parece válida", "Otro"]
RESULTS = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "out" / "local.json")


def load(p, default=None):
    return json.loads(Path(p).read_text()) if Path(p).exists() else default


def card(c, r, in_sample):
    e = lambda x: html.escape(str(x if x is not None else "—"))
    imgs = "".join(
        f'<figure><a href="/img/{Path(c[k + "_file"]).name}" target="_blank"><img loading="lazy" src="/img/{Path(c[k + "_file"]).name}"></a>'
        f"<figcaption>{label}</figcaption></figure>"
        for k, label in (("facade", "Fachada"), ("product", "Producto"), ("shelf", "Etiqueta"))
    )
    v = r["validaciones"]
    rows = [
        ("Tienda", c["capture_store_name"]), ("Producto esperado", c["product_name"]), ("Marca capturada", c["capture_brand"]),
        ("Contenido", f'{c["unit_quantity_product"]} {c["unit_product"]}'),
        ("Precio capturado", f'${c["capture_price"]}  (rango ${c["min_product_price"]}–${c["max_product_price"]})'),
        ("Precio que leyó el modelo", r["precio_detectado"]),
        ("Validaciones del modelo", " · ".join(f"{k}: {x}" for k, x in v.items())),
    ]
    tags = "".join(f'<label><input type="checkbox" value="{e(t)}"> {e(t)}</label>' for t in TAGS)
    return f"""
<article class="card" id="{e(c['capture_id'])}">
  <header><b>{e(c['capture_id'])}</b>{' <span class="badge">muestra20</span>' if in_sample else ''}
    <span>Analista: <b>{e(c['decision_esperada'])}</b>{(' · ' + e(c['motivo_rechazo'])) if c['motivo_rechazo'] else ''}</span>
    <span>Modelo: <b>{e(r['decision'])}</b> (confianza {r['confidence_score']:.2f}, {e(r['reason_code'])})</span></header>
  <div class="imgs">{imgs}</div>
  <table>{''.join(f'<tr><th>{e(k)}</th><td>{e(x)}</td></tr>' for k, x in rows)}</table>
  <p class="expl"><b>Explicación del modelo:</b> {e(r['explicacion'])}</p>
  <div class="tags">{tags}</div>
  <textarea placeholder="¿Por qué el analista decidió esto? ¿Qué se ve en las fotos que el modelo no vio?"></textarea>
</article>"""


def page():
    caps = {c["capture_id"]: c for c in load(DATA / "capturas.json")}
    res = sorted(load(RESULTS), key=lambda r: r["capture_id"])
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
    body = "".join(
        f'<h2>{html.escape(t)} <small>({len(rs)})</small></h2><p class="hint">{html.escape(h)}</p>'
        + "".join(card(caps[r["capture_id"]], r, r["capture_id"] in sample) for r in rs)
        for t, h, rs in groups
    )
    return PAGE.replace("{{BODY}}", body).replace("{{RESULTS}}", html.escape(RESULTS.name))


PAGE = """<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Revisión Validat3B</title><style>
body{font:15px/1.45 system-ui,sans-serif;margin:0 auto;max-width:1200px;padding:16px;background:#f6f6f4;color:#1d1d1b}
.top{position:sticky;top:0;background:#f6f6f4;padding:8px 0;border-bottom:1px solid #ddd;z-index:1;display:flex;gap:16px;align-items:center}
h2{margin:32px 0 4px}.hint{margin:0 0 12px;color:#555}
.card{background:#fff;border:1px solid #ddd;border-radius:10px;padding:14px;margin:0 0 18px}
.card header{display:flex;flex-wrap:wrap;gap:6px 18px;margin-bottom:10px}
.badge{background:#1d4ed8;color:#fff;border-radius:6px;padding:0 6px;font-size:12px}
.imgs{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
figure{margin:0}img{width:100%;height:340px;object-fit:contain;background:#222;border-radius:6px}
figcaption{text-align:center;font-size:13px;color:#555}
table{border-collapse:collapse;margin:10px 0;width:100%}th{text-align:left;width:220px;color:#555;font-weight:500}
th,td{padding:3px 6px;border-bottom:1px solid #eee;vertical-align:top}
.expl{background:#f3f3f0;padding:8px;border-radius:6px}
.tags{display:flex;flex-wrap:wrap;gap:4px 14px;margin:8px 0}
textarea{width:100%;box-sizing:border-box;min-height:70px;font:inherit;padding:8px}
.card.done{border-color:#16a34a}
@media(max-width:700px){.imgs{grid-template-columns:1fr}img{height:260px}}
</style></head><body>
<div class="top"><b>Revisión Validat3B</b><span>Resultados: {{RESULTS}}</span><span id="prog"></span><span id="st"></span></div>
<p>Para cada captura marca lo que veas y escribe por qué crees que el analista decidió así. Se guarda solo en <code>out/notas.json</code>. Clic en una foto para verla completa.</p>
{{BODY}}
<script>
const cards = [...document.querySelectorAll('.card')];
const st = document.getElementById('st'), prog = document.getElementById('prog');
function collect(){const o={};cards.forEach(c=>{const tags=[...c.querySelectorAll('input:checked')].map(x=>x.value),nota=c.querySelector('textarea').value.trim();
  c.classList.toggle('done',!!(tags.length||nota));if(tags.length||nota)o[c.id]={tags,nota};});prog.textContent=`${Object.keys(o).length} de ${cards.length} revisadas`;return o;}
async function save(){try{const r=await fetch('/notas',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(collect())});
  st.textContent=r.ok?'Guardado '+new Date().toLocaleTimeString():'Error al guardar';}catch(e){st.textContent='Error: ¿se cerró el servidor?';}}
let t;['input','change'].forEach(ev=>document.addEventListener(ev,()=>{clearTimeout(t);t=setTimeout(save,400);}));
fetch('/notas').then(r=>r.json()).then(n=>{cards.forEach(c=>{const x=n[c.id];if(!x)return;
  c.querySelectorAll('input').forEach(i=>i.checked=x.tags.includes(i.value));c.querySelector('textarea').value=x.nota||'';});collect();});
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
        if self.path == "/":
            return self.reply(200, page().encode(), "text/html; charset=utf-8")
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
    print(f"Revisión en {url}  (Ctrl+C para cerrar) · notas → {NOTES.relative_to(ROOT)}")
    webbrowser.open(url)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
