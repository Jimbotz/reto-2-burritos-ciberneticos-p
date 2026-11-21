"""Arma el JSON comparativo por captura: analista vs v1 vs v2 (y tus marcas de revisión, si existen).

    .venv/bin/python comparativo.py [--tokens-v2 N]
→ out/comparativo.json   detalle por captura (datos de 3B: se queda local, out/ está en .gitignore)
→ resultados/resumen.json solo totales por versión, sin productos, precios ni IDs (es lo que se publica)
v1 = prompt original + reglas (out/sim_final.json, simulado con las respuestas reales del modelo).
v2 = v1 + equivalencias de medidas + etiqueta del producto correcto (out/v2.json, corrida real).
Contiene datos de 3B (productos, precios, etiquetas del analista): por las reglas del reto no se publica fuera del equipo.
"""
import argparse, json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from validat3b import cost

VERSIONES = {
    "v1": ("out/sim_final.json", "Prompt original + reglas (cadena, nitidez, precio, corroboración zxing/OCR, dudas corroboradas)"),
    "v2": ("out/v2.json", "v1 + equivalencias de medidas (kg/g, L/ml, drenado/neto, promos) + usar la etiqueta del producto correcto"),
}
KEYS = ("decision", "confidence_score", "reason_code", "validaciones", "precio_detectado", "explicacion")
MARCA = {"aprobar": "aprobada", "rechazar": "rechazada", "revision": "revision_manual"}


def resumen(caps, res, tokens=None):
    pairs = [(caps[i]["decision_esperada"], r["decision"]) for i, r in res.items()]
    aprob = [e for e, p in pairs if p == "aprobada"]
    return {
        "capturas": len(pairs),
        "costo_operativo": sum(cost(e, p) for e, p in pairs),
        "precision_aprobacion": round(sum(e == "aprobada" for e in aprob) / len(aprob), 4) if aprob else None,
        "distribucion": dict(Counter(p for _, p in pairs)),
        "esperada_vs_predicha": {f"{e}->{p}": n for (e, p), n in sorted(Counter(pairs).items())},
        "tokens_por_captura": round(tokens / len(pairs)) if tokens else None,
    }


def main(out, publico, tokens_v2):
    caps = {c["capture_id"]: c for c in json.loads(Path("data/capturas.json").read_text())}
    res = {v: {r["capture_id"]: r for r in json.loads(Path(p).read_text())} for v, (p, _) in VERSIONES.items() if Path(p).exists()}
    notas = json.loads(Path("out/notas_final.json").read_text()) if Path("out/notas_final.json").exists() else {}
    doc = {
        "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "versiones": {v: {"descripcion": VERSIONES[v][1], **resumen(caps, r, tokens_v2 if v == "v2" else None)} for v, r in res.items()},
        "capturas": [
            {
                "capture_id": i,
                "tienda": c["capture_store_name"],
                "producto": c["product_name"],
                "precio_capturado": c["capture_price"],
                "analista": {"decision": c["decision_esperada"], "motivo": c["motivo_rechazo"] or None},
                **{v: {k: r[i].get(k) for k in KEYS} for v, r in res.items() if i in r},
                "revisor": MARCA.get((notas.get(i) or {}).get("decision")),
            }
            for i, c in sorted(caps.items())
        ],
    }
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(doc, ensure_ascii=False, indent=1))
    analista = dict(Counter(c["decision_esperada"] for c in caps.values()))
    pub = {"generado": doc["generado"], "capturas": len(caps), "analista": analista, "versiones": doc["versiones"]}
    Path(publico).parent.mkdir(parents=True, exist_ok=True)
    Path(publico).write_text(json.dumps(pub, ensure_ascii=False, indent=1))
    for v, s in doc["versiones"].items():
        print(f"{v}: costo {s['costo_operativo']} · precisión {s['precision_aprobacion']} · {s['distribucion']}")
    print(f"→ {out} (local) · {publico} (público)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokens-v2", type=int)
    ap.add_argument("--out", default="out/comparativo.json")
    ap.add_argument("--publico", default="resultados/resumen.json")
    a = ap.parse_args()
    main(a.out, a.publico, a.tokens_v2)
