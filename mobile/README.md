# Validat3B Campo

PWA móvil para confirmar la sucursal mediante ubicación o búsqueda, registrar el código de barras y enviar fotos del producto y de la etiqueta. FastAPI conserva las capturas y una cola de validación en SQLite. El navegador guarda los envíos pendientes en IndexedDB.

## Abrir desde el teléfono

1. Conecta el servidor y el teléfono a la misma red privada.
2. Abre el archivo `out/mobile/tls/ca.crt` en el teléfono si levantaste el servidor con la CA local. Instala el certificado y habilita su confianza para HTTPS. En iOS, activa la confianza en **Configuración → General → Información → Configuración de confianza de certificados**. También se puede usar un certificado que el teléfono ya reconozca con `--cert` y `--key`.
3. Abre la URL HTTPS que muestra el servidor. Usa la clave de `out/mobile/operador.clave` o la configurada mediante `MOBILE_OPERATOR_KEY`. La bandeja en `/revisar` usa su propia clave. Los archivos `*.key` permanecen en el servidor.

El navegador solicita ubicación al iniciar la visita. Si se deniega el permiso o hay varias tiendas cerca, la persona operadora puede elegir una sucursal. Una visita con ubicación pendiente puede registrar capturas y queda sujeta a revisión.

## Levantar el piloto

Ejecuta estos comandos desde la raíz del repositorio.

```sh
uv pip install --python .venv/bin/python -r mobile/requirements.txt
npm ci --prefix mobile/web
npm run --prefix mobile/web build
.venv/bin/python -m mobile.serve
```

El servidor escucha por HTTPS en el puerto 8443. Usa `--ip` si el teléfono debe entrar por otra interfaz privada. El primer arranque crea las claves del piloto y carga el catálogo del reto si existe `data/catalogo_productos.csv`. Usa `--local` para probar nitidez y códigos sin enviar imágenes a Foundry. La API principal toma `Endpoint`, `MODEL` y `API_KEY` del mismo entorno que el CLI.

## Cargar fuentes

El importador acepta el CSV de establecimientos o el ZIP publicado por INEGI. En la edición probada, los archivos usan `latin-1`. El importador limita los resultados a las cadenas soportadas y a las actividades SCIAN de abarrotes, supermercados y minisúpers. Guarda ID DENUE, CLEE y edición.

```sh
.venv/bin/python -m mobile.catalogos --denue data/denue_09_0525_csv.zip --edicion 2025-05 --encoding latin-1
.venv/bin/python -m mobile.catalogos --qqp data/01-2026_Q1.csv --edicion 2026-01-Q1
.venv/bin/python -m mobile.catalogos --productos data/catalogo_productos.csv
.venv/bin/python -m mobile.catalogos --equivalencias mobile/qqp/equivalencias.csv
.venv/bin/python -m mobile.catalogos --enlaces mobile/qqp/sucursales.csv
```

La muestra inicial combina [DENUE](https://www.inegi.org.mx/app/descarga/) y [observaciones de Profeco QQP](https://datos.profeco.gob.mx/index.php). Profeco carece de código de barras en el CSV. Las equivalencias se cargan después de cotejar marca, presentación y variante. La muestra usa el código de barras de Carnation Clavel de 360 g para resolver el SKU en el catálogo local y muestra observaciones de tres sucursales Soriana cuyo número de sucursal coincide en ambas fuentes. La referencia de QQP incluye la fecha de levantamiento. [Presentación de Nestlé](https://www.nestleprofessional.com.mx/carnation-clavel/leche-evaporada-360g)

Archivos verificados de DENUE de mayo de 2025. [Ciudad de México](https://www.inegi.org.mx/contenidos/masiva/denue/2025_05/denue_09_0525_csv.zip), [Jalisco](https://www.inegi.org.mx/contenidos/masiva/denue/2025_05/denue_14_0525_csv.zip), [Nuevo León](https://www.inegi.org.mx/contenidos/masiva/denue/2025_05/denue_19_0525_csv.zip)

## Evaluación oficial y operación móvil

El CLI recibe fachada, producto y etiqueta, y conserva el JSON oficial con `tienda_fachada`. La app guarda `sucursal` en el resultado móvil y aplica las reglas de producto, código, precio y confianza del mismo motor. La revisión humana pertenece a la operación móvil. Las fotos se guardan en el servidor y solo el worker las envía al endpoint de IA asignado cuando habilitas Foundry. [Bases y conexión oficiales](https://hackaton3b.com/validat3b.html#foundry)

El almacenamiento del piloto vive en `out/mobile/`. Su base y sus fotos deben seguir en el mismo volumen. La PWA usa un UUID para que reintentar una subida devuelva la misma captura.
