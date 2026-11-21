# Validat3B Campo

PWA móvil para confirmar la sucursal mediante ubicación o búsqueda, registrar el código de barras y enviar fotos del producto y de la etiqueta. FastAPI conserva las capturas y una cola de validación en SQLite. El navegador guarda los envíos pendientes en IndexedDB.

## Abrir desde el teléfono

1. Conecta el servidor y el teléfono a la misma red privada.
2. Abre la URL HTTP que imprime el servidor y entra con la clave de `out/mobile/operador.clave` o `MOBILE_OPERATOR_KEY`. La bandeja en `/revisar` usa su propia clave.
3. Busca la sucursal por nombre o dirección. Confírmala y empieza a registrar tus capturas. La ubicación queda pendiente de verificación.

La app tiene tres pestañas:

- **Capturar** (revisor: **Revisión**): fotos del producto y de la etiqueta, código y precio.
- **Comparar nuestros productos**: elige una zona (alcaldía) y un producto del catálogo para ver los precios Profeco de esa zona en tres niveles (ver abajo).
- **Errores corregidos**: los 3 errores más relevantes del modelo anterior que Validat3B ya corrige. Las capturas de pantalla y los textos se editan en `web/src/errores.ts`.

## Levantar el piloto

Ejecuta estos comandos desde la raíz del repositorio.

```sh
uv pip install --python .venv/bin/python -r mobile/requirements.txt
npm ci --prefix mobile/web
npm run --prefix mobile/web build
.venv/bin/python -m mobile.serve --http --port 8080
```

Usa HTTP en una red privada de confianza. El primer arranque crea las claves del piloto y carga el catálogo del reto si existe `data/catalogo_productos.csv`. Usa `--ip` si el teléfono debe entrar por otra interfaz privada y `--local` para probar nitidez y códigos sin enviar imágenes a Foundry. La API principal toma `Endpoint`, `MODEL` y `API_KEY` del mismo entorno que el CLI.

La ubicación automática y la recarga de la app sin conexión requieren HTTPS. Para habilitarlas, ejecuta `.venv/bin/python -m mobile.serve` y autoriza en el teléfono el certificado de `out/mobile/tls/ca.crt`, o usa un certificado reconocido por el dispositivo con `--cert` y `--key`.

## Cargar fuentes

El importador acepta el CSV de establecimientos o el ZIP publicado por INEGI. En la edición probada, los archivos usan `latin-1`. El importador limita los resultados a las cadenas soportadas y a las actividades SCIAN de abarrotes, supermercados y minisúpers. Guarda ID DENUE, CLEE y edición.

```sh
.venv/bin/python -m mobile.catalogos --denue data/denue_09_0525_csv.zip --edicion 2025-05 --encoding latin-1
.venv/bin/python -m mobile.catalogos --qqp data/01-2026_Q1.csv --edicion 2026-01-Q1
.venv/bin/python -m mobile.catalogos --productos data/catalogo_productos.csv
.venv/bin/python -m mobile.catalogos --equivalencias mobile/qqp/equivalencias.csv
.venv/bin/python -m mobile.catalogos --enlaces mobile/qqp/sucursales.csv
```

### Comparación de precios Profeco (CDMX)

En la pestaña Comparar se elige una zona (alcaldía o municipio, `GET /api/zonas`) y un producto del catálogo. La app compara con el precio Profeco más reciente de cada tienda de esa zona (`GET /api/precios/comparar`), en tres niveles:

1. **Mismo producto**, por cadena (mediana entre tiendas), según `equivalencias.csv`: marca, variante y presentación exactas.
2. **Misma marca, otra presentación**, por precio por kg, L o pieza.
3. **Otras marcas del mismo tipo**, por precio unitario; muestra la opción más barata.

Arriba de los niveles, una línea resume lo más barato de la zona y, si se escribe el precio de la etiqueta, cuánto se aleja de ese mínimo. Al elegir solo la zona aparece **¿Qué cadena es más barata?** (`GET /api/precios/cadenas`): en cada producto exacto que venden al menos dos cadenas de la zona se calcula el % de cada cadena sobre la más barata, y se promedia por cadena.

Los niveles 2 y 3 salen de `familias.csv`: por SKU, el tipo de producto de QQP, su marca y un filtro de variante (palabras obligatorias, `-palabra` excluida, `_` une frases: `super_extra -integral`). El contenido se lee del texto de la presentación ("Botella 1.5 Lt.", "Paquete C/12") y solo cuentan presentaciones entre 0.4 y 2.5 veces el contenido del producto. Si el nombre del catálogo trae el peso total ("90g (total: 130g)"), se usa ese, porque QQP publica el peso total de latas y frascos.

Es información para el equipo: el motor no la usa para decidir. Con la quincena de marzo de 2026 hay datos en 11 de las 16 alcaldías de CDMX. Bara no está en QQP y Neto casi no aparece.

Carga probada con la segunda quincena de marzo de 2026:

```sh
mkdir -p data/qqp && curl -L -o data/qqp/QQP_2026.rar https://datos.profeco.gob.mx/docs/qqp/QQP_2026.rar
cd data/qqp && C:/Windows/System32/tar.exe -xf QQP_2026.rar 2026/03-2026_Q2.csv; cd ../..   # tar de Windows (bsdtar) lee RAR
# El RAR viene truncado: el CSV termina en basura. Se recorta a la última línea completa.
.venv/Scripts/python -c "import re;p='data/qqp/2026/03-2026_Q2.csv';b=open(p,'rb').read();m=re.search(rb'\x00|  {50,}',b);open('data/qqp/03-2026_Q2_completo.csv','wb').write(b[:b.rfind(b'\n',0,m.start() if m else len(b))+1])"
.venv/Scripts/python -m mobile.catalogos --qqp data/qqp/03-2026_Q2_completo.csv --edicion "QQP 2026-03 Q2" --estado "Ciudad de México"
.venv/Scripts/python -m mobile.catalogos --equivalencias mobile/qqp/equivalencias.csv
.venv/Scripts/python -m mobile.catalogos --familias mobile/qqp/familias.csv
```

`equivalencias.csv` (18 SKU) y `familias.csv` (104 SKU) se revisaron a mano contra los datos de CDMX de marzo de 2026, copiando el texto exacto de QQP. Con esa quincena, alguno de los tres niveles responde en el 75% de los pares SKU × sucursal de CDMX (muestra de 60 sucursales); el nivel exacto, en el 12%. En la consola de Windows los acentos se ven como `�`, pero el CSV y la base están bien en UTF-8.

La muestra inicial combina [DENUE](https://www.inegi.org.mx/app/descarga/) y [observaciones de Profeco QQP](https://datos.profeco.gob.mx/index.php). Profeco carece de código de barras en el CSV. Las equivalencias se cargan después de cotejar marca, presentación y variante. La muestra usa el código de barras de Carnation Clavel de 360 g para resolver el SKU en el catálogo local y muestra observaciones de tres sucursales Soriana cuyo número de sucursal coincide en ambas fuentes. La referencia de QQP incluye la fecha de levantamiento. [Presentación de Nestlé](https://www.nestleprofessional.com.mx/carnation-clavel/leche-evaporada-360g)

Archivos verificados de DENUE de mayo de 2025. [Ciudad de México](https://www.inegi.org.mx/contenidos/masiva/denue/2025_05/denue_09_0525_csv.zip), [Jalisco](https://www.inegi.org.mx/contenidos/masiva/denue/2025_05/denue_14_0525_csv.zip), [Nuevo León](https://www.inegi.org.mx/contenidos/masiva/denue/2025_05/denue_19_0525_csv.zip)

## Evaluación oficial y operación móvil

El CLI recibe fachada, producto y etiqueta, y conserva el JSON oficial con `tienda_fachada`. La app guarda `sucursal` en el resultado móvil y aplica las reglas de producto, código, precio y confianza del mismo motor. La revisión humana pertenece a la operación móvil. Las fotos se guardan en el servidor y solo el worker las envía al endpoint de IA asignado cuando habilitas Foundry. [Bases y conexión oficiales](https://hackaton3b.com/validat3b.html#foundry)

El almacenamiento del piloto vive en `out/mobile/`. Su base y sus fotos deben seguir en el mismo volumen. La PWA usa un UUID para que reintentar una subida devuelva la misma captura.
