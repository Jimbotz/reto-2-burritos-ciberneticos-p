# Walmart, Bodega Aurrera y cadenas similares

## ¿Hay precios públicos asociados a ubicación y sucursal?

### Takeaway

Las fichas de Walmart México y Bodega Aurrera muestran precio en línea, vendedor y sucursal de recolección. Algunas fichas también muestran el código postal para la entrega. Walmart advierte que el precio web puede diferir del precio de la tienda física.

### Cited Findings

- La ficha de leche fresca Lala entera de 1 L de Walmart, con ID en URL `00750102052606`, mostró $34.00 MXN, recolección en SC TOREO, envío desde tienda a Miguel Hidalgo 11220 y venta de Walmart. Es una observación de la versión indexada de la ficha. [Walmart México](https://www.walmart.com.mx/ip/leche-fresca-lala-entera-1-l/00750102052606)
- La ficha con el mismo ID de Bodega Aurrera mostró $33.00 MXN, recolección en BA CANTIL y venta de Bodega Aurrera. Una versión indexada del kiosco también indicaba envío a la ZM del Valle de México, CP 04330. Son instantáneas de fechas y contextos diferentes. [Bodega Aurrera](https://www.bodegaaurrera.com.mx/ip/leche-fresca-lala-fresca-entera-1-l/00750102052606)
- El centro de ayuda de Walmart señala que los precios del sitio y de tienda física a veces difieren y que el precio o disponibilidad en dispositivos móviles pueden quedar sujetos a confirmación al pagar. [Centro de ayuda Walmart](https://kiosco.www.walmart.com.mx/ayuda/articulo/precios-y-contenidos/5c6f06e3f31a4d8a9b60d79a230a1aa7)
- Bodega Aurrera documenta que el cliente elige la tienda en la modalidad de recolección y distingue entre el surtido local de Tu Bodega y los artículos exclusivos en línea de Bodega Extendida. En una ficha, el subdominio `despensa.bodegaaurrera.com.mx` redirigió al dominio principal, por lo que conviene enlazar ese dominio. [Guía oficial de compra](https://www.bodegaaurrera.com.mx/imagenes/Informativo/Como_hago%20mi_despensa.pdf), [Preguntas frecuentes oficiales](https://www.bodegaaurrera.com.mx/imagenes/Legales_BOD/Preguntas_frecuentes_v03.pdf), [Ficha de despensa](https://despensa.bodegaaurrera.com.mx/ip/leche-fresca-lala-fresca-entera-1-l/00750102052606)
- Los términos de compra explican que los vendedores independientes de Marketplace establecen sus propios precios y que el Pickup no aplica a compras del Marketplace. [Términos de compra Grupo Walmart, secciones 02 y 04](https://www.walmartmexico.com/content/dam/walmart-mexico/documents/terminos_y_condiciones/Terminos_y_Condiciones_de_Walmart.pdf)
- Soriana publica fichas con precios y un selector de CP para calcular la fecha de entrega. El centro de ayuda de Chedraui documenta la selección de tienda para recolección y advierte que las promociones web pueden diferir de las de tienda física. [Ficha oficial Soriana](https://www.soriana.com/leche-lala-entera-deslactosada-1-l/11661460.html), [Sucursales Chedraui](https://ayuda.chedraui.com.mx/hc/es-419/articles/360038423614--Cu%C3%A1l-es-mi-tienda-m%C3%A1s-cercana), [Promociones Chedraui](https://ayuda.chedraui.com.mx/hc/es-419/articles/360038503534--Las-promociones-en-tienda-en-l%C3%ADnea-son-diferentes-a-tienda-f%C3%ADsica)

### Inferences

- Al almacenar datos, mantener aparte vendedor, sucursal, CP, modalidad (entrega/Pickup/anaquel), precio observado y fecha. El CP describe la entrega y la sucursal el Pickup, por lo que uno no reemplaza al otro.
- Si se usa para Validat3B, el precio en línea sirve como referencia contextual de orden de magnitud, mientras un caso de verificación de etiqueta física necesita evidencia de ese canal y fecha. Comparar a nivel de GTIN o presentación exacta y tratar promociones, peso variable y vendedores externos como contextos distintos.

### Gaps

- No se midió la variación real por CP/sucursal manteniendo constantes la cadena, la fecha, la modalidad y el GTIN. El ejemplo de leche ilustra campos disponibles, no una comparación vigente o alineada geográficamente.
- No se identificó una cadena mexicana verificable llamada “Banera”. Puede ser una errata, un comercio local o un término distinto. Pedir nombre o URL si se trata de otra tienda.

## ¿Se puede automatizar desde el equipo y qué acceso ofrece Walmart?

### Takeaway

Es viable procesar archivos o consultar APIs autorizadas desde un equipo local. Los términos de compra que enlaza Walmart incluyen la obtención automatizada de datos entre los usos indebidos. El API oficial de precios en México se orienta a la gestión de productos de vendedores de Marketplace.

### Cited Findings

- La sección 07 de los términos de compra de Grupo Walmart, actualización del 28 de octubre de 2026, incluye como uso indebido usar herramientas automatizadas para obtener información de los sitios. El documento identifica a Walmart y Bodega Aurrera y es el que enlaza la página de ayuda de los términos para Walmart.com.mx. Una versión anterior de los términos también contiene esta disposición e incluye expresamente Bodega Aurrera y Despensa Bodega Aurrera. El sitio anuncia un cambio de términos el 27 de noviembre, posterior a la fecha de consulta del 21 de noviembre. [Términos de Grupo Walmart, sección 07](https://www.walmartmexico.com/content/dam/walmart-mexico/documents/terminos_y_condiciones/Terminos_y_Condiciones_de_Walmart.pdf), [Página de ayuda de los términos](https://kiosco.www.walmart.com.mx/ayuda/articulo/terminos-y-condiciones/0ce968556dd14c0e98097b3675d39b08), [Versión anterior](https://i5.walmartimages.com/dfw/3ccc2d91-5ad5/k2-_a31fe262-aeac-4785-b554-cc450e6b7bf1.v1.pdf)
- Las Global Marketplace APIs en México son para vendedores y proveedores de soluciones aprobados, con alta y OAuth. Su documentación de precios describe la gestión de precios y promociones de los productos propios, no un acceso público a precios al consumidor por sucursal. [Acceso a las API de Marketplace](https://developer.walmart.com/mx-marketplace/docs/global-marketplace-apis), [API de precios y promociones](https://developer.walmart.com/global-marketplace/docs/price-and-promotional-price-management-api-overview)
- La Comer en Tu Casa también prohíbe emplear herramientas tecnológicas para extraer o recopilar información, incluso si es pública. [Términos de La Comer](https://www.lacomer.com.mx/resourceLacomer/TerminosyCondiciones.pdf)

### Inferences

- Programar una extracción en casa no resuelve la condición de acceso de las cadenas. Para integración repetible, usar un conjunto oficial reutilizable como Profeco, o un feed autorizado con la cobertura y derechos de reutilización pactados.

### Gaps

- No se instaló ni se verificó un scraper, y no se ensayaron captchas ni interfaces internas. La lectura puntual del centro de ayuda de Bodega devolvió una pantalla de verificación de identidad en el navegador de investigación, aunque la ficha sí se abrió. Esto no permite estimar tasas de bloqueo ni cobertura.
- No se confirmó autorización de extracción de Soriana o Chedraui. Una ficha pública y la ausencia de una palabra en los términos no acreditan permiso.
