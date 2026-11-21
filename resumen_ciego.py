"""Resume una salida oficial sin consultar datos de referencia."""

import argparse
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean


DECISIONES = ("aprobada", "rechazada", "revision_manual")
LLAVES = {
    "capture_id", "decision", "confidence_score", "reason_code", "validaciones",
    "precio_detectado", "codigo_barras_detectado", "explicacion",
}


def resumen(capturas, tokens_por_captura=None):
    if not isinstance(capturas, list) or any(not isinstance(c, dict) for c in capturas):
        raise ValueError("La entrada debe ser una lista de objetos")
    if tokens_por_captura is not None and (
        not math.isfinite(tokens_por_captura) or tokens_por_captura < 0
    ):
        raise ValueError("Los tokens por captura deben ser finitos y no negativos")
    distribucion = dict.fromkeys(DECISIONES, 0)
    motivos = {d: Counter() for d in DECISIONES}
    confianza = {d: [] for d in DECISIONES}
    fallas = Counter()
    for captura in capturas:
        validaciones = captura.get("validaciones", {})
        if not isinstance(validaciones, dict) or any(
            valor not in ("ok", "falla") for valor in validaciones.values()
        ):
            raise ValueError("Las validaciones deben ser un objeto con valores ok o falla")
        fallas.update(campo for campo, valor in validaciones.items() if valor == "falla")
        decision = captura.get("decision")
        if decision not in DECISIONES:
            continue
        distribucion[decision] += 1
        if "reason_code" in captura:
            if not isinstance(captura["reason_code"], str):
                raise ValueError("reason_code debe ser texto")
            motivos[decision][captura["reason_code"]] += 1
        if "confidence_score" in captura:
            valor = captura["confidence_score"]
            if type(valor) not in (int, float) or not math.isfinite(valor):
                raise ValueError("confidence_score debe ser un número finito")
            confianza[decision].append(valor)
    return {
        "version": "v2.1",
        "generado": datetime.now(timezone.utc).isoformat(),
        "capturas": len(capturas),
        "distribucion": distribucion,
        "reason_code": motivos,
        "fallas": dict(fallas),
        "confianza_promedio": {d: mean(valores) if valores else None
                               for d, valores in confianza.items()},
        "json_valido": all(LLAVES <= c.keys() and c.get("decision") in DECISIONES
                           for c in capturas),
        "tokens_por_captura": tokens_por_captura,
    }


def prueba():
    capturas = [
        {"capture_id": i, "decision": decision, "confidence_score": confianza,
         "reason_code": motivo, "validaciones": {"precio": estado, "codigo": "ok"},
         "precio_detectado": 12.5, "codigo_barras_detectado": "123",
         "explicacion": "Captura sintética"}
        for i, (decision, confianza, motivo, estado) in enumerate([
            ("aprobada", 0.9, "OK", "ok"),
            ("rechazada", 0.8, "PRECIO", "falla"),
            ("revision_manual", 0.5, "DUDOSO", "falla"),
        ])
    ]
    resultado = resumen(capturas, 120)
    assert resultado["version"] == "v2.1"
    assert datetime.fromisoformat(resultado["generado"]).utcoffset().total_seconds() == 0
    assert resultado["capturas"] == 3
    assert resultado["distribucion"] == dict.fromkeys(DECISIONES, 1)
    assert resultado["reason_code"] == {
        "aprobada": {"OK": 1}, "rechazada": {"PRECIO": 1},
        "revision_manual": {"DUDOSO": 1},
    }
    assert resultado["fallas"] == {"precio": 2}
    assert resultado["confianza_promedio"] == dict(zip(DECISIONES, (0.9, 0.8, 0.5)))
    assert resultado["json_valido"] is True
    assert resultado["tokens_por_captura"] == 120
    assert json.loads(json.dumps(resultado, allow_nan=False)) == resultado
    capturas[1]["decision"] = "aprobada"
    assert math.isclose(resumen(capturas)["confianza_promedio"]["aprobada"], 0.85)
    capturas[1]["decision"] = "invalida"
    assert resumen(capturas)["json_valido"] is False
    capturas[1]["decision"] = "rechazada"
    del capturas[0]["explicacion"]
    assert resumen(capturas)["json_valido"] is False
    assert resumen([])["confianza_promedio"] == dict.fromkeys(DECISIONES)
    assert resumen([])["tokens_por_captura"] is None
    print("Pruebas correctas")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("salida_oficial", nargs="?")
    parser.add_argument("tokens_por_captura", nargs="?", type=float)
    parser.add_argument("--test", action="store_true", help="Prueba sintética sin escribir archivos")
    args = parser.parse_args()
    if args.test:
        prueba()
        return
    if not args.salida_oficial:
        parser.error("Falta salida_oficial.json")
    try:
        capturas = json.loads(Path(args.salida_oficial).read_text(encoding="utf-8"))
        resultado = resumen(capturas, args.tokens_por_captura)
        contenido = json.dumps(resultado, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        destino = Path(__file__).resolve().parent / "resultados" / "resumen_ciego.json"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(contenido, encoding="utf-8")
    except (OSError, ValueError) as error:
        parser.exit(1, f"Error: {error}\n")
    print(f"{'Decisión':<18} {'Capturas':>8} {'Confianza':>10}")
    for decision in DECISIONES:
        confianza = resultado["confianza_promedio"][decision]
        texto = "—" if confianza is None else f"{confianza:.3f}"
        print(f"{decision:<18} {resultado['distribucion'][decision]:>8} {texto:>10}")
    print(f"Total: {resultado['capturas']} · JSON válido: {resultado['json_valido']}")


if __name__ == "__main__":
    main()
