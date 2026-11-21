# Validat3B · Burritos Cibernéticos

Motor que decide `aprobada` / `rechazada` / `revision_manual` para cada captura de precio (Reto 2, Hackatón Tiendas 3B).

Flujo por captura: filtro local de nitidez (OpenCV) y lectura local del código de barras de la etiqueta (zxing-cpp), sin tokens → Claude en Azure AI Foundry con las 3 fotos + metadatos → reglas duras (confianza, precio de etiqueta = capturado, rango de precio, no aprobar en cadenas cuya etiqueta trae código interno; aprobar si la etiqueta trae el código del producto y todo cuadra). Ante duda o error, `revision_manual`.

## Instalación paso a paso

Todos los comandos se corren **desde la carpeta raíz del repositorio**. Donde los comandos cambian, hay una versión para cada sistema:

- **Windows**: PowerShell. El Python del proyecto es `.venv\Scripts\python`.
- **Mac**: Terminal. El Python del proyecto es `.venv/bin/python`.

### Paso 1. Instalar las herramientas

Necesitas `git`, [`uv`](https://docs.astral.sh/uv/), que instala Python 3.12 por ti, y Node.js 20 o más reciente, solo para la app móvil.

```powershell
# Windows
winget install Git.Git
winget install astral-sh.uv
winget install OpenJS.NodeJS.LTS
```

```sh
# Mac (con Homebrew)
brew install git uv node
```

Cierra y vuelve a abrir la terminal para que reconozca los programas nuevos.

### Paso 2. Clonar e instalar dependencias

```powershell
# Windows
git clone <url-del-repo> reto-2; cd reto-2
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python -r requirements.txt -r mobile/requirements.txt
```

```sh
# Mac
git clone <url-del-repo> reto-2 && cd reto-2
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt -r mobile/requirements.txt
```

### Paso 3. Configurar la conexión a Foundry

Copia la plantilla y llénala con los datos de la sección «Conéctate a Azure AI Foundry» de la [página del reto](https://hackaton3b.com/validat3b.html#foundry): `Endpoint`, `MODEL` y `API_KEY`.

```sh
cp .env.example .env      # funciona igual en PowerShell y en Mac
```

La llave es personal del equipo. `.env` está en `.gitignore`: nunca la pongas en el código ni en un commit. Si dejas `API_KEY` vacía, el motor corre solo los filtros locales y no gasta tokens.

### Paso 4. Descargar los datos del reto (obligatorio)

Descárgalos de la [página del reto](https://hackaton3b.com/validat3b.html). No se suben al repo: `data/` está en `.gitignore`.

| Archivo | Qué trae | Dónde va |
|---|---|---|
| `Validat3B_desarrollo_metadatos.zip` | `capturas.json`, `capturas.csv`, `catalogo_productos.csv`, `LEEME.md` | descomprimir en `data/` |
| `Validat3B_desarrollo_imagenes.zip` | carpeta `imagenes/` con 300 fotos | descomprimir en `data/` |
| `Validat3B_evaluacion_metadatos.zip` | set ciego: capturas, catálogo y LEEME | descomprimir en `data/evaluacion/` |
| `Validat3B_evaluacion_imagenes.zip` | fotos del set ciego | descomprimir en `data/evaluacion/` |

Deja los zips en la raíz del repo, que también los ignora git, y descomprímelos:

```powershell
# Windows
Expand-Archive Validat3B_desarrollo_metadatos.zip  -DestinationPath data -Force
Expand-Archive Validat3B_desarrollo_imagenes.zip   -DestinationPath data -Force
Expand-Archive Validat3B_evaluacion_metadatos.zip  -DestinationPath data/evaluacion -Force
Expand-Archive Validat3B_evaluacion_imagenes.zip   -DestinationPath data/evaluacion -Force
```

```sh
# Mac
unzip -o Validat3B_desarrollo_metadatos.zip -d data
unzip -o Validat3B_desarrollo_imagenes.zip  -d data
unzip -o Validat3B_evaluacion_metadatos.zip -d data/evaluacion
unzip -o Validat3B_evaluacion_imagenes.zip  -d data/evaluacion
```

Debe quedar así. El motor busca las fotos en una carpeta `imagenes/` junto al `capturas.json` que le pases:

```
data/
├── capturas.json            ← desarrollo (100 capturas con decision_esperada)
├── catalogo_productos.csv
├── imagenes/CAP-…_facade.jpg, CAP-…_product.jpg, CAP-…_shelf.jpg
└── evaluacion/
    ├── capturas.json        ← set ciego (50 capturas)
    └── imagenes/…
```

Si al descomprimir quedó una carpeta de más, por ejemplo `data/evaluacion/Validat3B_evaluacion/capturas.json`, mueve su contenido un nivel arriba.

### Paso 5. DENUE de INEGI: ya viene en el repo

`datasets/denue_autoservicio_462111_462112.csv` (47,210 tiendas de todo el país) ya está en el repo. Lo usan `geolocalizar.py`, que compara el GPS de la fachada contra la sucursal declarada, y la app móvil. **No necesitas descargar nada para correr el proyecto.**

Fuente del archivo:

- *DENUE (INEGI), descarga masiva:* https://www.inegi.org.mx/app/descarga/?ti=6
- *Archivo usado:* Comercio al por menor (2 de 4), SCIAN 46112–46311, CSV, edición 05/2026
  https://www.inegi.org.mx/contenidos/masiva/denue/denue_00_46112-46311_csv.zip
- *Filtro:* `codigo_act` = 462111 (supermercados) y 462112 (minisupers)

Solo para actualizarlo a una edición nueva: descarga ese zip en `data/denue/` y regenera el CSV con este comando. Con la edición 05/2026 sale idéntico, byte por byte, al del repo:

```powershell
# Windows (en Mac cambia .venv\Scripts\python por .venv/bin/python)
.venv\Scripts\python -c "import csv,io,zipfile,sys;z=zipfile.ZipFile(sys.argv[1]);r=csv.reader(io.TextIOWrapper(z.open('conjunto_de_datos/denue_inegi_46112-46311_.csv'),'latin-1'));h=next(r);i=h.index('codigo_act');w=csv.writer(open(sys.argv[2],'w',newline='',encoding='utf-8-sig'));w.writerow(h);w.writerows(x for x in r if x[i] in ('462111','462112'))" data/denue/denue_00_46112-46311_csv.zip datasets/denue_autoservicio_462111_462112.csv
```

Los demás zips de DENUE (`denue_00_43`, `46111`, `46321-46531`, `46591-46911`) no se usan.

### Paso 6. Precios Profeco QQP (solo para la pestaña Comparar)

El motor no usa estos precios para decidir. Solo alimentan la comparación de la app móvil.

1. Descarga [`QQP_2026.rar`](https://datos.profeco.gob.mx/docs/qqp/QQP_2026.rar) de [datos.profeco.gob.mx](https://datos.profeco.gob.mx/index.php) y ponlo en `data/qqp/`.
2. Extrae la quincena que se probó, la segunda de marzo de 2026:

   ```powershell
   # Windows: el tar del sistema lee RAR
   cd data/qqp; C:\Windows\System32\tar.exe -xf QQP_2026.rar 2026/03-2026_Q2.csv; cd ../..
   ```

   ```sh
   # Mac: el tar del sistema (bsdtar) también lee RAR
   (cd data/qqp && tar -xf QQP_2026.rar 2026/03-2026_Q2.csv)
   ```

3. El RAR viene truncado y el CSV termina en basura. Este comando lo recorta a la última línea completa (en Mac usa `.venv/bin/python`):

   ```sh
   .venv\Scripts\python -c "import re;p='data/qqp/2026/03-2026_Q2.csv';b=open(p,'rb').read();m=re.search(rb'\x00|  {50,}',b);open('data/qqp/03-2026_Q2_completo.csv','wb').write(b[:b.rfind(b'\n',0,m.start() if m else len(b))+1])"
   ```

Resultado: `data/qqp/03-2026_Q2_completo.csv`.

### Paso 7. Cargar los catálogos en la app móvil

La base vive en `out/mobile/campo.sqlite`. En Mac cambia `.venv\Scripts\python` por `.venv/bin/python`:

```powershell
.venv\Scripts\python -m mobile.catalogos --productos data/catalogo_productos.csv
.venv\Scripts\python -m mobile.catalogos --denue datasets/denue_autoservicio_462111_462112.csv --edicion "DENUE 2026-05" --encoding utf-8-sig
.venv\Scripts\python -m mobile.catalogos --qqp data/qqp/03-2026_Q2_completo.csv --edicion "QQP 2026-03 Q2" --estado "Ciudad de México"
.venv\Scripts\python -m mobile.catalogos --equivalencias mobile/qqp/equivalencias.csv
.venv\Scripts\python -m mobile.catalogos --familias mobile/qqp/familias.csv
.venv\Scripts\python -m mobile.catalogos --enlaces mobile/qqp/sucursales.csv
```

Sin el paso 6, omite las líneas `--qqp` y `--enlaces`. La app funciona igual, pero Comparar sale vacía.

### Paso 8. OCR local (solo Mac con Apple Silicon)

El OCR local, Unlimited-OCR 4bit sobre MLX, corrobora que la etiqueta trae el precio y el código del producto. Es la segunda prueba que exige el motor para aprobar cuando zxing no leyó el código.

```sh
# Mac M1/M2/M3/M4
uv pip install --python .venv/bin/python mlx-vlm==0.6.3
```

El modelo (`sahilchachra/unlimited-ocr-4bit-mlx`) se descarga solo de Hugging Face la primera vez. En Windows o en una Mac Intel no hay OCR: el motor funciona, pero solo aprueba cuando zxing lee el código en la etiqueta, así que aprueba menos y manda más a revisión. **Corre el set ciego en una Mac con Apple Silicon** y confirma que la salida diga `OCR local: N etiquetas`, no `(no disponible: sin mlx-vlm)`.

### Paso 9. Verificar que todo quedó bien

```powershell
.venv\Scripts\python test_validat3b.py                    # imprime "ok"
.venv\Scripts\python -m mobile.test_comparar              # imprime "ok"
.venv\Scripts\python validat3b.py ping                    # responde "pong": la llave y el endpoint sirven
.venv\Scripts\python validat3b.py data/capturas.json out/local.json --local   # cero tokens: prueba datos y fotos
```

### Paso 10. Correr

```powershell
# Set ciego: es el archivo que se envía por correo
.venv\Scripts\python validat3b.py data/evaluacion/capturas.json out/evaluacion.json

# App móvil: compilar la interfaz y levantar el servidor
npm ci --prefix mobile/web
npm run --prefix mobile/web build
.venv\Scripts\python -m mobile.serve --http --port 8080
```

## Uso

En Windows cambia `.venv/bin/python` por `.venv\Scripts\python`. Para elegir versión en PowerShell usa `$env:VERSION="v2"; .venv\Scripts\python …` en lugar de `VERSION=v2 …`.

```bash
.venv/bin/python validat3b.py ping                                       # prueba el endpoint
.venv/bin/python validat3b.py data/capturas.json out/local.json --local  # solo filtros locales, cero tokens
.venv/bin/python validat3b.py data/capturas.json out/resultados.json 10  # primeras 10 capturas (gasta tokens)
.venv/bin/python validat3b.py data/capturas.json out/resultados.json     # todas
.venv/bin/python test_validat3b.py                                       # pruebas de reglas
VERSION=v2 .venv/bin/python validat3b.py data/capturas.json out/v2.json   # v2: + equivalencias de medidas y etiqueta correcta
VERSION=v2.1 .venv/bin/python validat3b.py data/capturas.json out/v2_1.json  # v2.1: + medidas + foto lejana
.venv/bin/python comparativo.py --tokens v2=N v2.1=M                       # analista vs v1 vs v2 vs v2.1
```

Con datos etiquetados imprime costo operativo, precisión de aprobación y la matriz esperada → predicha.

Versión por defecto: `v2.1` (`VERSION=v1|v2|v2.1|v2.2`). Política: si el modelo duda por la calidad de la foto (lejana, borrosa, ilegible), la captura se **rechaza para volver a capturarla** en lugar de mandarla a revisión.

`geolocalizar.py` contrasta el GPS EXIF de cada fachada (y su precisión) con las tiendas DENUE de `datasets/`; si el GPS queda ambiguo, desempata con el OCR de la fachada. La app móvil usa la misma regla. Las fotos de desarrollo no traen EXIF (ahí devuelve `sin_gps`); `test/` trae fotos de campo con GPS.

La [app móvil de campo](mobile/README.md) permite iniciar una visita por sucursal y registrar producto y etiqueta desde un teléfono conectado a la misma red.

## Resultados

`resultados/resumen.json`: totales por versión (costo operativo, precisión, distribución, matriz esperada → predicha). La pestaña **Parte técnica** de la app calcula ahí exactitud, precisión y sensibilidad por versión. El detalle por captura (`out/comparativo.json`) se queda local porque trae datos de 3B.
