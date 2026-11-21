import json
from unittest.mock import patch

from probar import Pagina, URLS, precios_pagina, probar


pagina = Pagina()
oferta = {"@type": "Offer", "price": "34.90", "priceCurrency": "MXN"}
producto = {
    "@type": "Product",
    "name": "Leche Lala Fresca Entera 1 lt",
    "sku": "365947",
    "offers": {
        "@type": "AggregateOffer",
        "offers": [oferta, dict(oferta, priceCurrency="USD"), dict(oferta, price="NaN")],
    },
}
pagina.feed(f'<script type="application/ld+json">{json.dumps({"@graph": [producto]})}</script>')
pagina.feed('<script type="application/ld+json">{json inválido}</script>')
pagina.feed('<strong>Vigencia: <span>4 de noviembre al 1 de diciembre de 2026.</span></strong>')
pagina.feed('<img title="POST PRECIOS HUEVO" src="/huevo.png">')
pagina.feed('<iframe class="fp-iframe" src="https://heyzine.com/flip-book/ejemplo.html"></iframe>')
pagina.close()

precios = list(precios_pagina(pagina))
assert len(precios) == 1
assert precios[0]["precio_mxn"] == "34.90"
assert precios[0]["sku"] == "365947"
assert precios[0]["cp_publicado"] is None
assert pagina.vigencia == "4 de noviembre al 1 de diciembre de 2026."
assert pagina.carteles == ["/huevo.png"]
assert pagina.folletos == ["https://heyzine.com/flip-book/ejemplo.html"]

url_bodega = URLS["bodega_aurrera"]
with patch("probar.descargar", return_value=(200, "https://www.bodegaaurrera.com.mx/blocked", b"")):
    bloqueado = probar("bodega_aurrera", url_bodega)
assert bloqueado["estado"] == "bloqueado"
assert bloqueado["url"] == url_bodega
print("ok")
