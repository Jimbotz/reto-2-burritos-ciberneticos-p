# Validat3B · Burritos Cibernéticos

Motor que decide `aprobada` / `rechazada` / `revision_manual` para cada captura de precio (Reto 2, Hackatón Tiendas 3B).

Flujo por captura: filtro local de nitidez (OpenCV) y lectura local del código de barras de la etiqueta (zxing-cpp), sin tokens → Claude en Azure AI Foundry con las 3 fotos + metadatos → reglas duras (confianza, precio de etiqueta = capturado, rango de precio, no aprobar en cadenas cuya etiqueta trae código interno; aprobar si la etiqueta trae el código del producto y todo cuadra). Ante duda o error, `revision_manual`.

## Setup

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env    # llenar Endpoint, API_KEY, MODEL (la key es personal)
```

Datos (no se suben al repo): descomprimir ambos zips del reto en `data/` para que quede `data/capturas.json` junto a `data/imagenes/`.

## Uso

```bash
.venv/bin/python validat3b.py ping                                       # prueba el endpoint
.venv/bin/python validat3b.py data/capturas.json out/local.json --local  # solo filtros locales, cero tokens
.venv/bin/python validat3b.py data/capturas.json out/resultados.json 10  # primeras 10 capturas (gasta tokens)
.venv/bin/python validat3b.py data/capturas.json out/resultados.json     # todas
.venv/bin/python test_validat3b.py                                       # pruebas de reglas
```

Con datos etiquetados imprime costo operativo, precisión de aprobación y la matriz esperada → predicha.
