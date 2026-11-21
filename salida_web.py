"""Salida para la página web: cada captura con los campos de capturas.json + el resultado del motor + hallazgos descriptivos.

La salida del hackathon sigue siendo el JSON oficial (validat3b.py la escribe igual que siempre). Esta otra es para personas:
qué se revisó, quién lo detectó (modelo, OCR local, lector de códigos, nitidez o una regla), qué falló y qué hacer para que pase.

    .venv/bin/python salida_web.py out/v2_1.json        → out/v2_1.web.json (recalcula señales locales, cero tokens)
validat3b.py también la escribe sola al terminar cada corrida (<salida>.web.json). Trae datos de 3B: se queda local.
"""
import json, sys
from pathlib import Path

import ocr_local
from validat3b import BLUR_REJECT, NO_APPROVE_CHAINS, barcodes, blur_score, num

# ponytail: textos propuestos; ajústalos al lenguaje de los operadores de campo
ACCIONES = {
    "CAPTURA_BORROSA": "Vuelve a tomar la foto con el teléfono quieto y toca la pantalla para enfocar.",
    "CAPTURA_LEJANA": "Acércate hasta que la etiqueta o el producto llenen al menos media foto.",
    "FOTO_DE_PANTALLA": "Fotografía el producto y la etiqueta reales, no la pantalla de otro dispositivo.",
    "FACHADA_INCORRECTA": "Toma la fachada donde se lea el nombre de la cadena.",
    "DESCRIPCION_INCOMPLETA": "Fotografía el producto completo y de frente, con su nombre y contenido visibles.",
    "PRODUCTO_NO_COINCIDE": "Verifica que sea el producto esperado: marca, presentación y contenido.",
    "CONTRATIPO_INVALIDO": "Captura solo contratipos permitidos para este producto.",
    "PRODUCTO_NO_VISIBLE": "Asegúrate de que el producto se vea completo y en primer plano.",
    "SIN_ETIQUETA_PRECIO": "Fotografía la etiqueta de precio que está justo junto al producto.",
    "SIN_PRECIO_UNITARIO": "Fotografía la etiqueta completa, incluido el precio unitario.",
    "PRECIO_NO_COINCIDE": "Verifica el precio capturado contra la etiqueta del producto correcto.",
    "DUDOSO": "Un analista revisará la captura. Si puedes, vuelve a fotografiar la etiqueta de cerca y de frente.",
}
SIN_MODELO = ("Foto shelf borrosa", "Foto product borrosa", "Sin modelo", "Error interno")
FOTO = {"shelf": "de la etiqueta", "product": "del producto"}


def h(frente, fuente, nivel, mensaje, accion=None):
    return {"frente": frente, "fuente": fuente, "nivel": nivel, "mensaje": mensaje, "accion": accion}


def hallazgos(cap, res, senales):
    """Lista de hallazgos a partir del resultado oficial y de las señales locales que midió el motor."""
    out = []
    for kind, s in senales.get("nitidez", {}).items():
        if s < BLUR_REJECT[kind]:
            out.append(h("evidencia", "nitidez", "falla", f"La foto {FOTO[kind]} está borrosa (nitidez {s:.0f}; mínimo {BLUR_REJECT[kind]:.0f}).",
                         ACCIONES["CAPTURA_BORROSA"]))
        else:
            out.append(h("evidencia", "nitidez", "ok", f"La foto {FOTO[kind]} es nítida (nitidez {s:.0f})."))
    if not senales.get("modelo"):
        out.append(h("evidencia", "regla", "aviso", "No se consultó al modelo: la captura se decidió con los filtros locales."))
        return out

    v, store = res["validaciones"], cap.get("capture_store_name")
    if "tienda_fachada" in v:
        out.append(h("fachada", "modelo", "ok", f"La fachada corresponde a {store}.") if v["tienda_fachada"] == "ok" else
                   h("fachada", "modelo", "falla", f"La fachada no permite confirmar que la tienda sea {store}.", ACCIONES["FACHADA_INCORRECTA"]))
    out.append(h("producto", "modelo", "ok", f"El producto coincide con «{cap.get('product_name')}».") if v.get("producto") == "ok" else
               h("producto", "modelo", "falla", f"El producto de la foto no se pudo confirmar como «{cap.get('product_name')}».",
                 ACCIONES["PRODUCTO_NO_COINCIDE"]))
    out.append(h("codigo_barras", "app", "ok", "El código escaneado coincide con el producto esperado.") if v.get("codigo_barras") == "ok" else
               h("codigo_barras", "app", "falla", f"El código escaneado ({cap.get('capture_barcode')}) no es el del producto esperado "
                 f"({cap.get('product_barcode')}).", "Escanea el código del producto que estás capturando."))

    exp = str(cap.get("product_barcode")).lstrip("0")
    codes = senales.get("codigos_etiqueta") or []
    if exp in codes:
        out.append(h("precio", "lector de códigos", "ok", "La etiqueta trae el código de barras del producto: es su etiqueta."))
    elif codes and store in NO_APPROVE_CHAINS:
        out.append(h("precio", "lector de códigos", "aviso", f"La etiqueta trae un código interno de {store} ({codes[0]}); no sirve para verificar el producto."))
    elif codes:
        out.append(h("precio", "lector de códigos", "aviso", f"La etiqueta trae otro código ({codes[0]}): podría ser de otro producto.",
                     ACCIONES["SIN_ETIQUETA_PRECIO"]))

    p, cp = res.get("precio_detectado"), num(cap.get("capture_price"))
    lo, hi = num(cap.get("min_product_price")), num(cap.get("max_product_price"))
    if p is None:
        out.append(h("precio", "modelo", "falla", "No se pudo leer el precio en la etiqueta.", "Fotografía la etiqueta de cerca y de frente."))
    elif cp is not None and abs(p - cp) > 0.01:
        out.append(h("precio", "modelo", "falla", f"La etiqueta dice ${p:.2f} y se capturó ${cp:.2f}.", ACCIONES["PRECIO_NO_COINCIDE"]))
    else:
        out.append(h("precio", "modelo", "ok", f"La etiqueta dice ${p:.2f}, igual al precio capturado."))
    if cp is not None and lo is not None and hi is not None and not lo <= cp <= hi:
        out.append(h("precio", "regla", "aviso", f"El precio capturado ${cp:.2f} está fuera del rango esperado (${lo:.2f}–${hi:.2f})."))

    if (t := senales.get("ocr")) is not None:
        if ocr_local.confirms(cap, t):
            out.append(h("precio", "OCR local", "ok", "El OCR local leyó en la etiqueta el precio y el código del producto."))
        else:
            falta = [x for x, ok in (("el precio", ocr_local.reads_price(cap, t)), ("el código", ocr_local.reads_code(cap, t))) if not ok]
            out.append(h("precio", "OCR local", "aviso", f"El OCR local no leyó {' ni '.join(falta)} en la etiqueta: no se pudo corroborar."))
    if store in NO_APPROVE_CHAINS:
        out.append(h("precio", "regla", "aviso", f"En {store} la etiqueta trae código interno: el motor no aprueba solo, la revisa un analista."))
    return out


def accion_sugerida(cap, res):
    if res["decision"] == "aprobada":
        return None
    if res["decision"] == "revision_manual" and cap.get("capture_store_name") in NO_APPROVE_CHAINS:
        return "Un analista revisará la captura: en esta cadena la etiqueta no permite verificar el producto."
    return ACCIONES.get(res["reason_code"], ACCIONES["DUDOSO"])


def registro(cap, res, senales):
    """Campos de capturas.json + resultado del motor + hallazgos descriptivos."""
    return {**cap, **res, "hallazgos": hallazgos(cap, res, senales), "accion_sugerida": accion_sugerida(cap, res)}


def senales_locales(cap, res, base):
    """Recalcula lo que midió el motor (nitidez, código en etiqueta, OCR si aplicaba), sin llamar al modelo."""
    s = {"nitidez": {}}
    for kind in ("shelf", "product"):
        s["nitidez"][kind] = round(blur_score(base / cap[f"{kind}_file"]), 1)
        if s["nitidez"][kind] < BLUR_REJECT[kind]:
            return s
    s["codigos_etiqueta"] = sorted(barcodes(base / cap["shelf_file"]))
    s["modelo"] = not res["explicacion"].startswith(SIN_MODELO)
    if s["modelo"] and (res["decision"] == "aprobada" or "OCR" in res["explicacion"]):
        s["ocr"] = ocr_local.read_label(cap, base / cap["shelf_file"])
    return s


def main(results_path, caps_path="data/capturas.json"):
    caps = {c["capture_id"]: c for c in json.loads(Path(caps_path).read_text())}
    base = Path(caps_path).parent
    web = [registro(caps[r["capture_id"]], r, senales_locales(caps[r["capture_id"]], r, base))
           for r in json.loads(Path(results_path).read_text())]
    out = Path(results_path).with_suffix(".web.json")
    out.write_text(json.dumps(web, ensure_ascii=False, indent=1))
    print(f"{len(web)} capturas → {out}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
