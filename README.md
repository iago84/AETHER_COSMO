# AETHERLAB

Sistema modular para simular, visualizar y gestionar experimentos de un “campo Aether” 2D con backend FastAPI, ejecución síncrona/asíncrona (BackgroundTasks o RQ/Redis), y UI de escritorio en PyQt6 orientada a exploración rápida.

## Características

- Simulador 2D con condiciones de contorno: periodic, fixed, absorbing.
- Fuentes configurables: gaussian_pulse, periodic, stochastic, top_hat, lorentzian.
- Métricas por frame y finales: energía, media, varianza, correlación espacial.
- Outputs numéricos:
  - PNG del snapshot final.
  - NPY del campo final.
  - NPZ con serie temporal de frames (opcional).
  - JSON con métricas del último frame.
- API REST (FastAPI) para gestionar proyectos/experimentos/runs y consultar resultados.
- Ejecución asíncrona conmutables:
  - Sin Redis: BackgroundTasks (FastAPI).
  - Con Redis: RQ (cola “aetherlab”), persistiendo `job_id` en la base.
- UI PyQt6 con:
  - Control de parámetros (fuente, boundary, steps, dt, etc.).
  - “Guardar serie” + `stride` para muestrear frames.
  - Visualización: energía vs tiempo, espectro radial k–P(k), autocorrelación 2D.
  - Controles de runs: estado, abortar/reintentar (si RQ), descargar snapshot/serie/campo, exportar métricas CSV.

## Arquitectura

- `aetherlab/packages/aether_sim`: simulador, fuentes y métricas.
  - `simulator2d.py`: núcleo numérico y lazos de tiempo con callback opcional.
  - `sources.py`: fuentes (gaussiana, periódica, estocástica, top-hat, lorentziana).
  - `metrics.py`: métricas básicas, autocorrelación 2D, espectro radial.
- `aetherlab/apps/api`: API FastAPI.
  - Endpoints para proyectos/experimentos/runs y figuras/series/métricas.
  - Detección automática de Redis vía `REDIS_URL`.
- `aetherlab/apps/desktop`: UI PyQt6.
- `aetherlab/packages/aether_core`: ORM y DB configurable (SQLite por defecto, PostgreSQL opcional).
- `scripts/rq_worker.py`: worker RQ que ejecuta simulaciones en background.

## Requisitos

- Python 3.11+
- Dependencias principales:
  - `fastapi`, `uvicorn`, `SQLAlchemy`, `numpy`, `matplotlib`, `PyQt6`
  - Opcionales para colas: `redis`, `rq`

Instalación:

```bash
pip install -r requirements.txt
```

## Base de Datos

- Por defecto usa SQLite en `aetherlab/data/outputs/aetherlab.db`.
- Para PostgreSQL define `AETHERLAB_DB_URL`, p. ej.:

```powershell
$env:AETHERLAB_DB_URL="postgresql+psycopg2://user:pass@host:5432/dbname"
```

El esquema se crea/ajusta en el arranque de la API (añade `job_id` si falta).

## Ejecutar la API (Windows)

```bash
uvicorn aetherlab.apps.api.main:app --host 127.0.0.1 --port 8000
```

Rutas básicas:

- Salud: `GET /health`
- Proyectos: `POST /projects`, `GET /projects`
- Experimentos: `POST /experiments`, `GET /experiments?project_id=...`
- Runs: `GET /runs`, `GET /runs/{id}`, `POST /runs/{id}/refresh`
- Simulación síncrona: `POST /simulate/simple`
- Simulación asíncrona: `POST /simulate/async`
- Resultados:
  - `GET /figures/{run_id}/snapshot` → PNG
  - `GET /figures/{run_id}/metrics` → JSON
  - `GET /figures/{run_id}/field` → NPY
  - `GET /figures/{run_id}/series` → NPZ (frames)
  - `GET /figures/{run_id}/series-metrics` → métricas por frame
  - `GET /figures/{run_id}/spectrum` → k, P(k)
  - `GET /figures/{run_id}/autocorr?crop=N` → autocorrelación 2D recortada
- Artefactos y modelos:
  - `GET /artifacts?run_id=...&dataset_id=...&experiment_id=...&model_run_id=...`
  - `GET /artifacts/{artifact_id}/download` → descarga segura (bajo `aetherlab/data/`)
  - `GET /models?experiment_id=...`, `GET /models/{model_run_id}`

### Asíncrono con RQ/Redis (opcional)

1) Define `REDIS_URL`, por ejemplo:

```powershell
$env:REDIS_URL="redis://localhost:6379/0"
```

2) Arranca el worker:

```bash
python scripts\rq_worker.py
```

3) Lanza simulaciones con `POST /simulate/async`. El `job_id` se persiste en el run.

Operaciones sobre runs con RQ:

- `POST /runs/{id}/abort` → cancelar job.
- `POST /runs/{id}/retry` → reencolar si falló.

## Docker Compose (API + Postgres + Redis + Worker)

El `docker-compose.yml` levanta:

- `api`: FastAPI + Uvicorn (puerto 8000).
- `db`: Postgres 15 (puerto 5432).
- `redis`: Redis 7 (puerto 6379).
- `worker`: RQ worker para ejecutar simulaciones asíncronas.

Variables de entorno útiles:

- `AETHERLAB_DB_URL`: URL SQLAlchemy (por defecto en Compose apunta a Postgres).
- `REDIS_URL`: URL de Redis (por defecto en Compose apunta al servicio `redis`).
- `AETHERLAB_API_KEY`: si se define, exige header `X-API-Key` en POST/PUT/DELETE.
- `AETHERLAB_CLEANUP_DAYS`: umbral (días) para limpieza automática de outputs.

Ejecutar:

```bash
docker compose up
```

## UI de Escritorio (PyQt6)

```bash
python aetherlab\apps\desktop\main.py
```

Capacidades:

- Ajuste de parámetros de simulación y ejecución vía API.
- Guardar serie (NPZ) y representar energía vs tiempo.
- Consultar espectro radial (escala lineal o log) y autocorrelación 2D (recorte).
- Gestión de runs: estado actual (incluye RQ), abortar/reintentar y descarga de artefactos (PNG, NPZ, NPY, CSV de métricas).

## Ejemplos de uso rápido (Python)

Crear proyecto y experimento:

```python
import json, urllib.request
base="http://127.0.0.1:8000"
req = urllib.request.Request(base+"/projects", data=json.dumps({"name":"Demo","description":"Proyecto"}).encode(), headers={"Content-Type":"application/json"})
print(urllib.request.urlopen(req).read().decode())
req = urllib.request.Request(base+"/experiments", data=json.dumps({"project_id":1,"name":"Exp1"}).encode(), headers={"Content-Type":"application/json"})
print(urllib.request.urlopen(req).read().decode())
```

Simulación síncrona con serie:

```python
payload={
  "experiment_id":1, "steps":80, "boundary":"absorbing",
  "source_kind":"lorentzian", "gamma":9.0, "sigma":10, "amplitude":1.0,
  "save_series": True, "series_stride": 10
}
req = urllib.request.Request(base+"/simulate/simple", data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"})
print(urllib.request.urlopen(req).read().decode())
```

Consultar espectro y autocorrelación:

```python
print(urllib.request.urlopen(base+"/figures/1/spectrum").read().decode())
print(urllib.request.urlopen(base+"/figures/1/autocorr?crop=96").read().decode())
```

## Convenciones y seguridad

- No exponer credenciales en el código. Configurar DB y Redis vía variables de entorno.
- No bloquear la UI durante operaciones de red prolongadas; llamadas con timeout y manejo de errores.
- Outputs bajo `aetherlab/data/outputs/` para facilitar limpieza y versionado de artefactos.

## Roadmap sugerido

- UI: panel de inspección de series (scrubber, repro, export de subsecuencias).
- Métricas: espectro radial en k físico (con escala espacial y normalización), autocorrelación radial, detectores de eventos.
- Persistencia: guardar config de simulación por run y exportar reports HTML.
- Colas: supervisión de jobs, reintentos con backoff, colas separadas por prioridad.

---

Para dudas o mejoras, abre un issue o comenta en el proyecto.
