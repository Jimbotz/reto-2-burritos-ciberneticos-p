# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Validat3B (Reto 2, Hackatón Tiendas 3B) decide `aprobada` / `rechazada` / `revision_manual` para cada captura de precio de campo. Código, comentarios, mensajes y commits van en español. Commits: `Validat3B: <asunto corto>`.

## Comandos

Desde la raíz, Python 3.12 en `.venv`:

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env                       # Endpoint, MODEL, API_KEY (vacía = solo local); EFFORT, WORKERS opcionales

.venv/bin/python test_validat3b.py         # reglas de apply_rules(); sin datos ni credenciales, imprime "ok"
.venv/bin/python scrapping/test_probar.py  # pruebas del scraper
.venv/bin/python -m mobile.test_comparar   # comparación Profeco por zona (SQLite temporal)
.venv/bin/python validat3b.py ping                                       # conectividad Foundry
.venv/bin/python validat3b.py data/capturas.json out/local.json --local  # solo filtros locales, cero tokens
.venv/bin/python validat3b.py data/capturas.json out/resultados.json 10  # primeras 10 (gasta tokens)
.venv/bin/python revisar.py [manual]       # página local de revisión en http://127.0.0.1:8765
```

Las pruebas son scripts de `assert` planos (sin pytest): no hay forma de correr una sola; se ejecuta el archivo completo. No hay linter ni formateador configurado.

App móvil (`mobile/`):

```bash
uv pip install --python .venv/bin/python -r mobile/requirements.txt
npm ci --prefix mobile/web && npm run --prefix mobile/web build   # build = tsc --noEmit + vite build → mobile/web/dist
.venv/bin/python -m mobile.serve --http --port 8080 [--local]     # sin --http genera CA propia en out/mobile/tls
.venv/bin/python -m mobile.catalogos --productos data/catalogo_productos.csv   # también --denue, --qqp, --equivalencias, --enlaces
```

`mobile.serve` se niega a arrancar si `mobile/web/dist/index.html` no existe. No hay dev server de Vite configurado.

`data/` (zips del reto: `data/capturas.json` + `data/imagenes/`), `out/`, `.env` y `AGENTS.md` están en `.gitignore`.

## Arquitectura

**Pipeline por captura (`validat3b.py`, `decide()`)**, ordenado de barato a caro:
1. Nitidez local (varianza del Laplaciano, OpenCV) de `shelf` y `product` contra `BLUR_REJECT` → `rechazada` sin tokens.
2. Lectura local de códigos de barras de la etiqueta con zxing-cpp.
3. Sin `API_KEY` → se salta el modelo. Con clave → `ask_model()`: Claude vía `AnthropicFoundry` con las fotos redimensionadas y `META_KEYS`, salida forzada con `output_config.format` json_schema (`SCHEMA`).
4. `apply_rules()`: normaliza al formato oficial y aplica reglas duras. Es la única capa determinista y la que cubren las pruebas; las reglas nuevas van ahí.

`safe_decide()` atrapa cualquier excepción y devuelve `revision_manual`: el gate exige ≥99% de JSON válido, así que nunca se pierde una captura. `evaluate()` imprime costo y precisión si las capturas traen `decision_esperada`.

**Asimetría de costos (`cost()`)**: aprobar mal = 10, rechazar una buena = 3, revisión manual = 1; gate de precisión de aprobación ≥97%. Todo el diseño falla hacia `revision_manual`. En `apply_rules()`, una `aprobada` se degrada si: sucursal no verificada, cadena en `NO_APPROVE_CHAINS` (etiqueta con código interno), confianza < `APPROVE_MIN`, alguna validación en `falla`, precio de etiqueta ≠ capturado, precio fuera de rango o, por último, falta de corroboración OCR. La única promoción es `revision_manual` → `aprobada` cuando zxing leyó en la etiqueta el código del producto, el precio cuadra y todo está `ok`.

**OCR local (`ocr_local.py`)**: Unlimited-OCR 4bit sobre MLX, solo Apple Silicon (`mlx-vlm`, no está en `requirements.txt`). Corre en un pool de un hilo porque MLX debe usar el modelo en el mismo hilo. Se pasa a `apply_rules()` como callable perezoso (`ocr=`) y solo se invoca si todas las demás reglas pasaron; hay una prueba que lo verifica. Sin MLX, `read_text()` devuelve `""` y nada se aprueba sin zxing. `estudio_ocr.py` es el benchmark que eligió el modelo.

**Dos modos en el mismo motor**, según `store_verified`:
- CLI (`None`): 3 fotos (facade, product, shelf), validación `tienda_fachada`, OCR activo.
- Móvil (`True`/`False`): 2 fotos, `sucursal` reemplaza a `tienda_fachada`, comparación de código más estricta y sin OCR.

`MOBILE_PROMPT` se deriva de `PROMPT` con `.replace()` de frases literales. Si editas esas frases en `PROMPT`, el reemplazo falla en silencio y el prompt móvil sigue pidiendo la fachada. `MOBILE_SCHEMA` es una copia de `SCHEMA` sin `tienda_fachada`.

**App móvil (`mobile/`)**: PWA React + TanStack Router/Query (`mobile/web/src`) servida por FastAPI (`api.py`, `create_app()`). `POST /api/capturas` normaliza las fotos (`evidencia.py`: HEIC/JPEG, GPS de EXIF), decide si la sucursal quedó verificada (ubicación de la visita, ventana de 4 h, EXIF a menos de 250 m) y encola en SQLite (`out/mobile/campo.sqlite`, esquema en `db.py`). Un hilo `worker.py` reclama capturas con lease, llama a `validat3b.decide(..., store_verified=...)` y reintenta con backoff ante errores transitorios de Anthropic. El UUID de la PWA hace idempotente el reenvío (`huella`). Hay dos roles con claves distintas (`operador`, `revisor`) en `out/mobile/*.clave` o en `MOBILE_OPERATOR_KEY` / `MOBILE_REVIEW_KEY`. `catalogos.py` importa sucursales (DENUE), precios Profeco QQP y el catálogo de productos.

**Otros**: `revisar.py` es una página local de etiquetado manual (lee `out/local.json` o `out/sim_ocr.json` y guarda notas en `out/notas*.json`). `scrapping/` es un experimento aparte de precios en sitios de cadenas; no lo usa el motor.

## Convenciones

- No cambies las llaves del JSON oficial (`capture_id`, `decision`, `confidence_score`, `reason_code`, `validaciones`, `precio_detectado`, `codigo_barras_detectado`, `explicacion`) ni los valores `ok`/`falla` y de decisión; `test_validat3b.py` los fija.
- Los comentarios `ponytail:` marcan umbrales calibrados en dev (`BLUR_REJECT`, `NO_APPROVE_CHAINS`, `REASON_CODES` provisionales, costo supuesto de `revision_manual`). Si cambias una decisión, reporta costo operativo y precisión de aprobación sobre datos etiquetados y extiende `test_validat3b.py`.
- Las imágenes del reto no deben salir de la máquina salvo hacia el endpoint Foundry configurado.
