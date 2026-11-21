# Datos de precios por sucursal de Profeco

## Descargas y actualización

### Takeaway

La base pública Quién es Quién en los Precios permite consultar precios observados por sucursal con herramientas locales. El catálogo de Profeco ofrece archivos anuales, el metadato del conjunto reciente declara actualización mensual y las filas de los CSV están agrupadas por quincena.

### Cited Findings

- La ruta explícita `/index.php` del catálogo devolvió HTTP 200 con el listado de archivos y enlaces a los RAR anuales de 2015 a 2026. La ruta antigua `/datos_abiertos/index.php` devolvió 404 al consultarla, aunque algunos buscadores conservan su contenido. [Catálogo de datos abiertos de Profeco](https://datos.profeco.gob.mx/index.php)
- El CSV oficial declara cobertura del 1 de enero de 2024 al 31 de agosto de 2026 y periodicidad mensual. El directorio del archivo 2026 muestra piezas llamadas `01-2026_Q1.csv`, `01-2026_Q2.csv` y equivalentes de febrero y marzo. [Metadatos oficiales](https://datos.profeco.gob.mx/docs/qqp/QQP_metadatos_dataset.csv), [archivo de 2026](https://datos.profeco.gob.mx/docs/qqp/QQP_2026.rar)
- Prueba local del 21 de noviembre de 2026. El RAR respondió a la petición del rango completo con HTTP 206, `Content-Range: bytes 0-20772375/20772376` y `Content-Length: 20772376`. El archivo guardado midió 20.772.376 bytes. `bsdtar` pudo leer los registros de la primera quincena de enero y extraer una pequeña muestra de la segunda quincena de marzo, pero al listar y procesar el archivo reportó truncación tras seis nombres. La fecha del corte de agosto proviene del metadato. [Descarga oficial de 2026](https://datos.profeco.gob.mx/docs/qqp/QQP_2026.rar), [metadatos de Profeco](https://datos.profeco.gob.mx/docs/qqp/QQP_metadatos_dataset.csv)
- Existe un catálogo alternativo federal para 2025. El índice muestra CSV descargables por producto, marca, categoría y ubicación, y marca CC BY 4.0. La solicitud directa al catálogo devolvió HTTP 403 en este entorno. Profeco también publica un RAR 2025 y el enlace respondió con cabecera RAR genuina en una consulta parcial. [Conjunto federal 2025](https://www.datos.gob.mx/dataset/programa_quien_es_quien_precios_2025), [archivo de 2025](https://datos.profeco.gob.mx/docs/qqp/QQP_2025.rar)
- El buscador actual de QQP facilita consultas de productos y establecimientos, y Profeco explica que su sistema de consulta se actualiza diariamente. El histórico está disponible desde 1999 bajo solicitud. [Buscador de Profeco](https://qqp.profeco.gob.mx/), [metodología](https://www.gob.mx/profeco/documentos/que-es-el-qqp-y-como-funciona?state=published), [solicitud histórica](https://qqp.profeco.gob.mx/historico)

### Inferences

- Para una ingesta local, importa la fecha de observación de cada fila. El atributo HTTP `Last-Modified` y la fecha de actualización de la página corresponden al servidor y al catálogo.
- Una tabla local SQLite o DuckDB permite filtrar por municipio, cadena, sucursal y fecha tras convertir las quincenas disponibles en registros tabulares.

### Gaps

- Quedó sin verificar localmente la disponibilidad efectiva del corte completo de agosto de 2026. La truncación se observó en la descarga probada y no acredita que toda copia del archivo se comporte igual.
- No se verificó una API pública documentada de consulta masiva del buscador actualizado.

## Campos, cobertura y precios registrados

### Takeaway

La primera quincena de enero de 2026 contiene registros de Walmart, Bodega Aurrerá, Soriana, Chedraui, La Comer y H-E-B. Cada observación identifica producto, presentación, precio, fecha y sucursal. Los datos reflejan los productos y establecimientos monitoreados en fechas concretas.

### Cited Findings

- Encabezado observado localmente en la primera quincena de enero de 2026. `producto,presentacion,marca,categoria,catalogo,precio,fecha_registro,cadena_comercial,giro,nombre_comercial,direccion,estado,municipio,latitud,longitud`. En este CSV faltan EAN/UPC, SKU y un campo exclusivo para CP. Las direcciones observadas incluyen CP como texto. [Archivo oficial](https://datos.profeco.gob.mx/docs/qqp/QQP_2026.rar)
- La primera quincena extraída permitió leer 496.726 filas con fechas del 2 al 15 de enero y 29 etiquetas de estado. Las filas observadas incluyen `Wal-Mart` (88.346), `Bodega Aurrera` (51.882), `Hipermercado Soriana` (67.078), `Chedraui` (37.671), `La Comer` (11.468) y `H.E.B.` (8.715), más formatos adicionales de varias cadenas. [Archivo oficial](https://datos.profeco.gob.mx/docs/qqp/QQP_2026.rar)
- El reporte semanal que Profeco publicó el 16 de noviembre de 2026 incluye precios de canasta observados del 3 al 6 de noviembre e identifica sucursales concretas de Walmart, Bodega Aurrerá, H-E-B y S-Mart, con entidad, municipio y dirección. Sirve como comprobación de cobertura más reciente para canastas. [Histórico de presentaciones](https://qqph.profeco.gob.mx/), [reporte del 16 de noviembre](https://qqph.profeco.gob.mx/storage/attachment/primeran/2026/QQPPRIMERAN_111626.pdf)
- La metodología describe precios de venta al consumidor registrados en establecimientos. Explica la consulta de un catálogo de productos y el levantamiento con personal de Profeco. [Qué es el QQP y cómo funciona](https://www.gob.mx/profeco/documentos/que-es-el-qqp-y-como-funciona?state=published)
- Existe una implementación pública de ingesta por lotes. CanastaMX describe su procesamiento de CSV oficiales de 2025 y 2026, incluyendo inconsistencias de codificación en mayo de 2026. Es contexto de implementación verificable en sus propios documentos. [Repositorio CanastaMX](https://github.com/arik36/canastamx), [documentación técnica sobre los archivos](https://github.com/arik36/canastamx/blob/main/docs/datos/fuente-qqp.md)

### Inferences

- Para cotejar productos entre cadenas con este CSV, usar conjuntamente producto, marca y presentación. Conservar fecha, sucursal y dirección como parte de cada observación. Comparar tamaños y conversiones con cuidado.
- Los datos sirven como referencia histórica y geográfica. La fecha del levantamiento limita su uso para obtener un precio pagable hoy. Un precio de tienda en línea depende de su propio canal y zona de servicio.

### Gaps

- Sin municipio o CP del usuario, la comprobación de cobertura no certifica existencia de una sucursal o muestra de su colonia.
- Quedó sin verificar una coincidencia de EAN, pues falta la columna en la muestra local.
