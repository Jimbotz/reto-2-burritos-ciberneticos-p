# Precios de supermercados en páginas oficiales

Prueba local con una ficha de leche Lala fresca entera de 1 L por cadena, más los carteles de Tiendas Bara y los folletos de Tiendas 3B. El script usa los datos de producto publicados en el HTML. Guarda el precio en pesos, SKU, códigos publicados, vendedor y, cuando la ficha los expone, código postal y sucursal de recolección.

Ejecuta estos comandos desde la raíz con Python 3.12.

```sh
.venv/bin/python scrapping/probar.py
.venv/bin/python scrapping/probar.py --tienda walmart --tienda chedraui
.venv/bin/python scrapping/probar.py --tienda soriana --url 'https://www.soriana.com/leche-lala-fresca-entera-1-lt/365947.html'
.venv/bin/python scrapping/test_probar.py
```

## Prueba del 21 de noviembre de 2026

| Tienda | Resultado |
| --- | --- |
| Walmart México | $34.00 MXN. La ficha devolvió CP 06700 y sucursal de recolección 3846. |
| Bodega Aurrerá | $33.00 MXN con CP 06700 y sucursal de recolección 3759 en una corrida. Otra consulta obtuvo $35.00 con CP 11560. La última corrida recibió una pantalla de verificación de identidad y quedó marcada como `bloqueado`. |
| Chedraui | $34.00 MXN. |
| Soriana | $34.90 MXN. |
| Tiendas Bara | 10 carteles con vigencia publicada del 4 de noviembre al 1 de diciembre. Confirmé en los carteles leche Bonamark 1 L a $20.00 y huevo blanco Bonamark de 30 piezas a $64.00. |
| Tiendas 3B | La página oficial enlazó 3 folletos embebidos. El script registra los enlaces. |
| H-E-B | La ficha respondió HTTP 403 a la solicitud local. |
| La Comer | La página de entrada cargó sin un precio de producto en el HTML consultado. |

Los valores son de páginas o carteles concretos y corresponden al momento de la consulta. La prueba usa la ubicación que devuelve cada página. Los campos de códigos se guardan tal como los publica cada tienda. La muestra de la última corrida está en [muestra.json](muestra.json).

## Carteles y bloqueos

- El OCR de Bara usa Vision en macOS con las herramientas de Swift instaladas. El script devuelve los enlaces a las imágenes en los demás entornos. El campo `precio_mxn_candidato` requiere cotejo con la imagen. Por ejemplo, Vision leyó `$350` y `$1300` en dos carteles que muestran **$3.50** y **$13.00**, respectivamente. Esas cifras ambiguas se conservan como texto de OCR. [Cartel de agua](https://bara.com.mx/wp-content/uploads/2026/09/1-POST-PRECIOS_OCTUBRE-07.png), [cartel de arroz](https://bara.com.mx/wp-content/uploads/2026/09/2-POST-PRECIOS_OCTUBRE-03.png)
- El script deja registrado el código HTTP o la redirección a verificación. Los términos de Grupo Walmart incluyen la obtención automatizada de información entre los usos indebidos de sus sitios. [Términos de Grupo Walmart, sección 07](https://www.walmartmexico.com/content/dam/walmart-mexico/documents/terminos_y_condiciones/Terminos_y_Condiciones_de_Walmart.pdf)
