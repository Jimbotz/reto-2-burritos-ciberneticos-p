# Validat3B · Burritos Cibernéticos

Motor que decide `aprobada` / `rechazada` / `revision_manual` para cada captura de precio (Reto 2, Hackatón Tiendas 3B).

Flujo por captura: filtro local de nitidez (OpenCV) y lectura local del código de barras de la etiqueta (zxing-cpp), sin tokens → Claude en Azure AI Foundry con las 3 fotos + metadatos → reglas duras (confianza, precio de etiqueta = capturado, rango de precio, no aprobar en cadenas cuya etiqueta trae código interno; aprobar si la etiqueta trae el código del producto y todo cuadra). Ante duda o error, `revision_manual`.

## Setup

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env    # llenar Endpoint, API_KEY, MODEL (la key es personal)
```

Datos (no se suben al repo): descomprimir ambos zips del reto en `data/` para que quede `data/capturas.json` junto a `data/imagenes/`.
`geolocalizar.py` contrasta el GPS EXIF de cada fachada (y su precisión) con las tiendas DENUE de `datasets/`; si el GPS queda ambiguo, desempata con el OCR de la fachada. La app móvil usa la misma regla. Las fotos de desarrollo no traen EXIF (ahí devuelve `sin_gps`); `test/` trae fotos de campo con GPS.

## Uso

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

Versión por defecto: `v2.1` (`VERSION=v1|v2|v2.1`). Política: si el modelo duda por la calidad de la foto (lejana, borrosa, ilegible), la captura se **rechaza para volver a capturarla** en lugar de mandarla a revisión.

La [app móvil de campo](mobile/README.md) permite iniciar una visita por sucursal y registrar producto y etiqueta desde un teléfono conectado a la misma red.

## Resultados

`resultados/resumen.json`: totales por versión (costo operativo, precisión, distribución, matriz esperada → predicha). El detalle por captura (`out/comparativo.json`) se queda local porque trae datos de 3B.
