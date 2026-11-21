# Herramientas locales y servicios de precios

## ¿Qué proyectos se pueden ejecutar en local?

### Takeaway

Existe código público dirigido a México. RadardeOfertas tiene adaptadores reales para Walmart, Bodega Aurrera y Soriana, con un flujo documentado en Python y Docker Compose. El código de Walmart/Bodega sirve como referencia técnica para ofertas en línea y requiere validar vigencia y ubicación antes de depender de sus resultados.

### Cited Findings

- RadardeOfertas captura ofertas en línea y documenta ejecución local con Docker Compose, PostgreSQL, Redis y workers Celery, además de CLI en Python. Su flujo completo incluye publicador de Telegram. El README declara MIT, aunque GitHub no identifica un archivo de licencia. La API de GitHub devuelve último push el 26 de marzo de 2026 UTC y repositorio sin archivar. [Repositorio y README](https://github.com/nieto567-sudo/RadardeOfertas) [Metadatos públicos de GitHub](https://api.github.com/repos/nieto567-sudo/RadardeOfertas)
- Los adaptadores de Walmart México y Bodega Aurrera usan búsquedas públicas en sus dominios mexicanos con `requests` y `BeautifulSoup`, leen precio de las tarjetas HTML y pasan solo la palabra buscada. Los dos escriben `available=True` al construir cada resultado. Las búsquedas predeterminadas se enfocan en electrónica y electrodomésticos. El campo `store` contiene el nombre de la cadena, sin sucursal ni CP. [Walmart](https://github.com/nieto567-sudo/RadardeOfertas/blob/main/scrapers/walmart.py) [Bodega Aurrera](https://github.com/nieto567-sudo/RadardeOfertas/blob/main/scrapers/bodega_aurrera.py) [Modelo base](https://github.com/nieto567-sudo/RadardeOfertas/blob/main/scrapers/base.py)
- El repositorio también incluye un adaptador para la búsqueda pública de Soriana (`www.soriana.com`), con parseo genérico de tarjetas de producto. [Adaptadores de comercios mexicanos](https://github.com/nieto567-sudo/RadardeOfertas/blob/main/scrapers/retailers_mx.py)
- El proyecto público `bolsa-de-frutas-y-verduras` ofrece scripts Node sin dependencias npm para su flujo de ingesta y una interfaz local que se levanta con su instalación de desarrollo. Combina la Central de Abasto de Iztapalapa de SNIIM con observaciones al menudeo de Profeco para CDMX. Incluye Walmart, Walmart Express, Bodega Aurrera, Soriana, Chedraui y La Comer. La mediana que presenta es por cadena y quincena, no un precio vigente de una sucursal específica. [Proyecto y metodología](https://github.com/Nathsvelro/bolsa-de-frutas-y-verduras)
- Existe `walmart-mx`, CLI Python para búsqueda en walmart.com.mx y gestión de pedidos y carrito. Utiliza una sesión autenticada del navegador y una interfaz interna que el propio autor describe como no publicada y cambiante. [Repositorio y limitaciones](https://github.com/johnparkerg/walmart-mx)

### Inferences

- El código de RadardeOfertas demuestra que hay una opción adaptable de ejecución local, pero el nombre de la cadena y un `available=True` fijo impiden usarlo tal cual para afirmar stock o precio de una sucursal. Las consultas iniciales tampoco cubren por defecto una canasta básica. Su dependencia de selectores de HTML puede hacer que un cambio en la tienda devuelva filas vacías.
- Para demostración con el reto 3B, el modelo más útil es producto y presentación exactos, cadena, sucursal confirmada o CP, modalidad (observación física o carrito en línea), vendedor, precio en MXN, URL y fecha de observación. Si la fuente entrega la sucursal seleccionada, conservarla para poder detectar respuestas del valor predeterminado.

### Gaps

- Se revisó el código, sin instalar ni ejecutar el bot contra las tiendas. No hay evidencia propia de que los selectores actuales devuelvan filas o de que exista un scraper público local mantenido que cubra a la vez Walmart, Aurrera, Soriana, Chedraui y La Comer con precio por sucursal.

## ¿Qué API alojada documenta precios por sucursal o precios del catálogo mexicano?

### Takeaway

Hay opciones administradas diferentes para Walmart México y Aurrera con parámetros documentados de sucursal o CP. La procedencia y la sucursal devuelta merecen verificación antes de emplearlas como referencia.

### Cited Findings

- Walmart México en SerpApi admite `walmart_domain=walmart.com.mx`, `store_id`, precio de oferta y campos de ubicación en `search_information.location`. La incidencia pública reportó tiendas MX que devolvían la tienda predeterminada 2344 y el equipo anunció la corrección el 27 de octubre de 2026. [Documentación oficial del proveedor](https://serpapi.com/walmart-search-api) [Incidencia y corrección](https://github.com/serpapi/public-roadmap/issues/4465)
- La oferta Walmart Product & Local Store Scraper en Apify documenta `market=MX`, `mexicoPostalCode` y `mexicoStoreId`, resultados en MXN, ubicación y precio, con exportación JSON/CSV. Los parámetros equivalentes `zipCode`/`storeId` de ese actor son para EE. UU. [Apify HypeBridge](https://apify.com/hypebridge/walmart-product-scraper)
- La oferta de JMLP para Bodega Aurrera en Apify documenta `postalCodes` y `storeIds`, una fila por producto y sucursal, registros de sucursales con dirección e ID, y tienda predeterminada 3874 en Coyoacán cuando no se manda ubicación. El precio anunciado es US$25 por 1,000 filas más uso de la plataforma. [Apify JMLP](https://apify.com/jmlp/bodega-aurrera-scraper) [Esquema de entrada](https://apify.com/jmlp/bodega-aurrera-scraper/api/openapi)
- Scavio ofrece búsqueda y categorías de Walmart México con precio en MXN, vendedor, disponibilidad y ubicación devuelta. Para México la ubicación es la tienda predeterminada de Walmart y el proveedor documenta que no se puede configurar CP ni sucursal. [Documentación de Scavio](https://scavio.dev/es/walmart-api)
- Un actor de Chedraui en Apify documenta búsquedas por texto o EAN, precio normal y de oferta, y stock del catálogo. Aclara que se trata de la ubicación en línea predeterminada. [Apify Chedraui](https://apify.com/youthful_colleague/chedraui-scraper)

### Inferences

- Para comprobar precisión por sucursal se puede comparar manualmente el mismo producto y presentación en dos sucursales, con idéntica modalidad y poca diferencia de tiempo, y corroborar que el proveedor devuelve el ID solicitado. El antecedente de SerpApi muestra por qué mandar un ID no basta.

### Gaps

- La cobertura y exactitud de las APIs alojadas se basan en documentación de los proveedores. No se ejecutaron llamadas de pago, ni se comprobó equivalencia entre precio en línea y precio en caja.

## ¿Qué comparadores mexicanos existen para uso directo?

### Takeaway

Hay comparadores ya hechos para Walmart, Bodega Aurrera y otras cadenas. CompraÓptima también incluye Tiendas 3B y explica que sus referencias son de tickets, etiquetas y comunidad.

### Cited Findings

- Chécalo publica cobertura de Walmart, Bodega Aurrera, Chedraui, Soriana, HEB, La Comer, City Market, Fresko, Sumesa y La Gran Bodega. Compara por código de barras, muestra fecha de captura, y según su sitio muestra el precio de la sucursal cercana cuando la cadena publica precios diferenciados. Son referencias de tienda en línea capturadas periódicamente. [Chécalo](https://checalo.mx/)
- SuCom dice revisar diariamente lo publicado por las tiendas en línea, entre ellas Walmart México, Bodega Aurrera, Chedraui, Soriana, La Comer y H-E-B. Tiene historial por tienda y búsqueda por nombre, marca, presentación o código de barras. Su propio aviso indica que el precio de sucursal puede variar. [Comparador y método de SuCom](https://www.sucom.com.mx/precios) [Historial de SuCom](https://www.sucom.com.mx/historial-de-precios)
- CompraÓptima incluye Tiendas 3B, Bodega Aurrera, Walmart, Walmart Express, Chedraui, La Comer, Soriana y otras cadenas. Declara captura manual a partir de tickets y etiquetas, más aportes de la comunidad. Indica cobertura principalmente en CDMX, fecha de observación y precios de lista sin promociones. [Cobertura y metodología de CompraÓptima](https://www.compraoptima.com/)

### Inferences

- CompraÓptima es precedente especialmente pertinente si la pregunta se vincula al reto 3B. Chécalo y SuCom sirven para contrastar manualmente la viabilidad de precios públicos de catálogo por producto. El enfoque de tickets y etiquetas puede cubrir comercios que carezcan de un catálogo en línea usable.

### Gaps

- En las fuentes revisadas no se encontró una API pública de integración o una descarga de esos comparadores. Sus declaraciones de frecuencia, cobertura y precios no fueron contrastadas con tickets ni con compras.
- La búsqueda del término exacto «banera» en este contexto no identificó con suficiente certeza un supermercado o proveedor de datos mexicano. No sustituir el término por otro nombre como si estuviera confirmado.
