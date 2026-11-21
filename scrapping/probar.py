"""Sondea páginas públicas de supermercados y emite una muestra JSON."""

import argparse
from datetime import datetime
from decimal import Decimal
import gzip
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


URLS = {
    "walmart": "https://www.walmart.com.mx/ip/leche-fresca-lala-entera-1-l/00750102052606",
    "bodega_aurrera": "https://www.bodegaaurrera.com.mx/ip/leche-fresca-lala-fresca-entera-1-l/00750102052606",
    "chedraui": "https://www.chedraui.com.mx/leche-entera-lala-fresca-carton-1l-3012008/p",
    "soriana": "https://www.soriana.com/leche-lala-fresca-entera-1-lt/365947.html",
    "bara": "https://bara.com.mx/",
    "tiendas_3b": "https://tiendas3b.com/promociones-tiendas-3-b-folleto-mensual/",
    "heb": "https://www.heb.com.mx/lala-leche-fresca-entera-carton-con-tapa-1-l-2767/p",
    "la_comer": "https://www.lacomer.com.mx/lacomer/",
}


class Pagina(HTMLParser):
    def __init__(self):
        super().__init__()
        self.json_ld = []
        self.next_data = {}
        self.carteles = []
        self.folletos = []
        self.vigencia = None
        self.despues_de_vigencia = False
        self.script = None
        self.fragmentos = []

    def handle_starttag(self, tag, attrs):
        datos = dict(attrs)
        src = datos.get("src")
        if tag == "script":
            if datos.get("type") == "application/ld+json":
                self.script = "json_ld"
            elif datos.get("id") == "__NEXT_DATA__":
                self.script = "next_data"
            self.fragmentos = []
        elif tag == "img" and src and "POST PRECIOS" in (datos.get("title") or "").upper():
            self.carteles.append(src)
        elif tag == "iframe" and src and "fp-iframe" in (datos.get("class") or "").split():
            self.folletos.append(src)

    def handle_data(self, data):
        if self.script:
            self.fragmentos.append(data)
        elif data.strip() == "Vigencia:":
            self.despues_de_vigencia = True
        elif self.despues_de_vigencia and data.strip():
            self.vigencia = data.strip()
            self.despues_de_vigencia = False

    def handle_endtag(self, tag):
        if tag != "script" or not self.script:
            return
        try:
            datos = json.loads("".join(self.fragmentos))
        except ValueError:
            datos = None
        if self.script == "json_ld":
            self.json_ld.append(datos)
        elif isinstance(datos, dict):
            self.next_data = datos
        self.script = None


def objetos(valor):
    if isinstance(valor, dict):
        yield valor
    elif isinstance(valor, list):
        for elemento in valor:
            yield from objetos(elemento)


def productos(valor):
    for objeto in objetos(valor):
        tipo = objeto.get("@type")
        if tipo == "Product" or (isinstance(tipo, list) and "Product" in tipo):
            yield objeto
        yield from productos(objeto.get("@graph"))


def ofertas(valor):
    for oferta in objetos(valor):
        if oferta.get("@type") == "AggregateOffer":
            yield from ofertas(oferta.get("offers"))
        else:
            yield oferta


def precios_pagina(pagina):
    publicados = pagina.next_data
    for clave in ("props", "pageProps", "initialData", "data", "product"):
        publicados = publicados.get(clave) or {}
        if not isinstance(publicados, dict):
            publicados = {}
            break
    ubicacion = publicados.get("location") or {}
    ubicacion = {
        "cp_publicado": ubicacion.get("postalCode"),
        "sucursal_pickup_id_publicada": (ubicacion.get("pickupLocation") or {}).get("storeId"),
    }
    for producto in productos(pagina.json_ld):
        codigos = {
            clave: producto[clave]
            for clave in ("gtin", "gtin12", "gtin13", "gtin14")
            if producto.get(clave)
        }
        for oferta in ofertas(producto.get("offers")):
            precio = str(oferta.get("price"))
            if oferta.get("priceCurrency") != "MXN" or not re.fullmatch(r"\d+(?:\.\d{1,2})?", precio):
                continue
            vendedor = oferta.get("seller")
            if isinstance(vendedor, dict):
                vendedor = vendedor.get("name")
            yield {
                "producto": producto.get("name"),
                "sku": producto.get("sku"),
                "codigos_publicados": codigos,
                "precio_mxn": f"{Decimal(precio):.2f}",
                "vendedor": vendedor or publicados.get("sellerDisplayName"),
                **ubicacion,
            }


def descargar(url):
    solicitud = Request(url, headers={"User-Agent": "PricePageSample/1.0"})
    with urlopen(solicitud, timeout=15) as respuesta:
        contenido = respuesta.read()
        if respuesta.headers.get("Content-Encoding", "").lower() == "gzip":
            contenido = gzip.decompress(contenido)
        return respuesta.status, respuesta.url, contenido


def precios_bara(pagina, url):
    urls = list(dict.fromkeys(urljoin(url, src) for src in pagina.carteles))
    urls = [
        imagen for imagen in urls
        if urlsplit(imagen).scheme == "https" and urlsplit(imagen).hostname == urlsplit(url).hostname
    ]
    if not urls or not shutil.which("swift") or not shutil.which("xcrun"):
        return [{"imagen_url": imagen} for imagen in urls]

    resultado = []
    with TemporaryDirectory() as temporal:
        archivos = []
        pendientes = []
        for imagen in urls:
            fila = {"imagen_url": imagen, "requiere_revision": True}
            resultado.append(fila)
            try:
                _, _, contenido = descargar(imagen)
            except (OSError, ValueError) as error:
                fila["error"] = str(error)
                continue
            archivo = Path(temporal) / f"{len(archivos)}.png"
            archivo.write_bytes(contenido)
            archivos.append(archivo)
            pendientes.append(fila)
        if archivos:
            script = Path(__file__).with_name("ocr_bara.swift")
            proceso = subprocess.run(
                ["swift", str(script), *map(str, archivos)],
                capture_output=True, text=True, timeout=120, check=True,
            )
            lecturas = json.loads(proceso.stdout)
            for fila, lectura in zip(pendientes, lecturas, strict=True):
                fila.update(lectura)
                importe = lectura.get("importe_ocr") or ""
                # shortcut: las cifras sin separador pueden incluir centavos en superíndice.
                if re.fullmatch(r"\$\d{1,2}(?:\.\d{2}|\.)?", importe):
                    fila["precio_mxn_candidato"] = f"{Decimal(importe[1:]):.2f}"
    return resultado


def probar(tienda, url):
    resultado = {
        "tienda": tienda,
        "url": url,
        "consultado_en": datetime.now(ZoneInfo("America/Mexico_City")).isoformat(timespec="seconds"),
    }
    try:
        estado, url_final, contenido = descargar(url)
        if urlsplit(url_final).path.rstrip("/") == "/blocked":
            resultado.update(estado="bloqueado", http=estado)
            return resultado
        resultado.update(http=estado, url=url_final)
        pagina = Pagina()
        pagina.feed(contenido.decode("utf-8", errors="replace"))
        pagina.close()
        if tienda == "bara":
            resultado.update(estado="carteles", vigencia_publicada=pagina.vigencia)
            resultado["carteles"] = precios_bara(pagina, url_final)
        elif tienda == "tiendas_3b":
            resultado.update(
                estado="folleto" if pagina.folletos else "sin_folleto",
                folletos=pagina.folletos,
            )
        else:
            precios = list(precios_pagina(pagina))
            resultado.update(estado="precio" if precios else "sin_precio_estructurado", precios=precios)
    except HTTPError as error:
        resultado.update(estado="error_http", http=error.code, error=error.reason)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        resultado.update(estado="error", error=str(error))
    return resultado


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--tienda", choices=URLS, action="append")
    cli.add_argument("--url", help="URL pública alternativa para una sola tienda")
    args = cli.parse_args()
    tiendas = args.tienda or URLS
    if args.url:
        if len(tiendas) != 1:
            cli.error("--url requiere seleccionar exactamente una --tienda")
        url = urlsplit(args.url)
        if url.scheme != "https" or url.hostname != urlsplit(URLS[tiendas[0]]).hostname:
            cli.error("--url debe usar HTTPS y el dominio de la tienda seleccionada")
    resultados = [probar(tienda, args.url or URLS[tienda]) for tienda in tiendas]
    print(json.dumps(resultados, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
