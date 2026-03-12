# Documento Técnico de AETHERLAB

## Resumen
Plataforma para simulación y análisis de un campo 2D con backend FastAPI, ejecución asíncrona conmutables (BackgroundTasks/RQ+Redis), almacenamiento de artefactos (PNG, NPY, NPZ, JSON) y UI en PyQt6 para exploración.

## Hipótesis de trabajo y alcance
- Hipótesis de trabajo: “La memoria del Aether” como campo fenomenológico capaz de registrar huellas energéticas/estructurales.
- Separación rigurosa:
  - Física establecida: numerics, métricas y análisis estándar (espectro, autocorrelación).
  - Modelo fenomenológico: narrativa de “memoria” útil para exploración computacional, no validada.
  - Especulación: ideas a contrastar mediante experimentos reproducibles.
- Alcance del MVP: proveer plataforma seria, modular y extensible para simular, ingerir datos y aplicar IA, sin afirmar la hipótesis como confirmada.

## Arquitectura
- Capa de simulación (`aetherlab/packages/aether_sim`):
  - `simulator2d.py`: malla 2D, integración temporal con `dt`, `steps`, `lam`, `diff`, `noise` y `boundary` (periodic/fixed/absorbing). Permite `set_source` y `callback` por paso para muestrear series.
  - `sources.py`: fuentes `gaussian_pulse`, `periodic_gaussian`, `stochastic`, `top_hat`, `lorentzian`.
  - `metrics.py`: `compute_metrics` (energía, media, varianza, correlación), `autocorr2d`, `power_spectrum_radial` y métricas comparativas (`rmse`, `nrmse`, `ssim2d`).
- Capa API (`aetherlab/apps/api`):
  - Gestión de proyectos, experimentos y runs.
  - Simulación síncrona (`POST /simulate/simple`) y asíncrona (`POST /simulate/async`).
  - Endpoints de resultados: snapshot, métricas, campo (.npy), serie (.npz), métricas de serie, espectro radial, autocorrelación 2D.
  - Barridos reproducibles (`POST /sweeps/grid`) creando múltiples `SimulationRun` con `config_json` y `seed` deterministas.
  - Comparación run↔run y run↔dataset con métricas y figura exportable (PNG/SVG/PDF).
  - Estado de runs con polling de Redis si `REDIS_URL` y `job_id` presente. Abort/Retry/Cleanup para RQ.
- Capa de datos (`aetherlab/packages/aether_data`):
  - `registry.py`: loaders para Planck/GWOSC/SDSS con resumen estadístico.
  - `etl.py`: estructura `raw/processed/features`, normalización (`zscore`, `minmax`, `robust`, `none`) y QC con trazabilidad (hash/mtime).
  - Endpoints: `GET /data/datasets`, `POST /data/load`; `POST/GET /datasets` (registro DB) y vínculo `POST /experiments/{eid}/datasets/link`.
- Capa UI (`aetherlab/apps/desktop`):
  - Control de parámetros (nx/ny, fuente, cx/cy, boundary, steps, dt, lam/diff/noise, amplitude, sigma, duration, etc.), presets y validación explícita.
  - Pestañas de visualización: energía vs tiempo, espectro radial (lineal/log), autocorrelación 2D con recorte.
  - Reproducción de series NPZ con control de frame actual.
  - Selector de proyecto/experimento, pestañas de Datos/IA/Comparación/Reportes/Configuración y export unificado.
  - Gestión de runs: estado (incluye backend y job_id), abortar, reintentar, descarga de artefactos y export (CSV/PNG/SVG/PDF/NPZ/MP4/HTML).
  - Visualización rápida: PCA de métricas de serie usando `/ai/pca-plot` (PNG embebido en base64).
- Capa Core (`aetherlab/packages/aether_core`):
  - ORM SQLAlchemy. Modelos `Project`, `Experiment`, `SimulationRun` (incluye `job_id`).
  - DB configurable por `AETHERLAB_DB_URL` (SQLite por defecto). Ajuste de esquema en arranque.
- Worker (`scripts/rq_worker.py`):

## Flujo de Datos
1) UI o cliente REST solicita crear proyecto/experimento.
2) Se lanza `POST /simulate/simple` (bloqueante) o `POST /simulate/async` (en cola o background).
3) El simulador produce `sim.u`. Se guardan PNG/JSON y opcionalmente NPY/NPZ.
4) La API registra un `SimulationRun` con `status` y `snapshot_path`. En modo RQ, guarda `job_id`.
5) La UI consulta `/runs/{id}` para estado, y `/figures/...` para artefactos y métricas.

## Esquema ORM
- `Project(id, name, description, created_at)`
- `Experiment(id, project_id, name, created_at)`
- `SimulationRun(id, experiment_id, status, created_at, snapshot_path, job_id, seed, config_json)`
- `Dataset(id, name, path, description, created_at)`
- `ModelRun(id, experiment_id, model_name, params_json, status, metrics_json, created_at)`
- `ExperimentDataset(id, experiment_id, dataset_id, created_at)`
- `Artifact(id, experiment_id, dataset_id, model_run_id, kind, path, meta_json, created_at)`

## Endpoints Principales
- Proyectos/Experimentos: `POST/GET /projects`, `POST/GET /experiments`
- Runs: `GET /runs`, `GET /runs/{id}`, `POST /runs/{id}/refresh`, `POST /runs/{id}/abort`, `POST /runs/{id}/retry`, `POST /runs/{id}/cleanup`
- Simulación: `POST /simulate/simple`, `POST /simulate/async`
- Barridos: `POST /sweeps/grid`
- Resultados: `GET /figures/{run}/snapshot(.png)|snapshot.svg|snapshot.pdf|metrics|field|series|series-metrics|spectrum|autocorr`
- Datos: `GET /data/datasets`, `POST /data/load`, `POST/GET /datasets`, `GET /datasets/{id}/meta`, `POST /etl/dataset`, `POST /experiments/{eid}/datasets/link`
- IA: `POST /ai/outlier-score`, `POST /ai/dbscan`, `POST /ai/run-on-run`, `POST /ai/run-on-dataset`, `GET /ai/download`, `GET /models`
- Comparación: `GET /compare/run-run`, `GET /compare/run-dataset` (+ `.../figure.png|.svg|.pdf`)
- Reportes: `GET /reports/run/{id}/html`, `GET /reports/experiment/{id}/html`

## Diseño Numérico
- Laplaciano con condiciones de contorno:
  - `periodic`: `np.roll`
  - `fixed`: celdas internas; bordes Dirichlet 0
  - `absorbing`: atenuación en bordes + Dirichlet
- Estabilidad controlada por `dt`, `lam`, `diff`. El usuario ajusta desde UI.

## Persistencia de Artefactos
- Directorio: `aetherlab/data/outputs/`
- Archivos por run:
  - `snapshot_*.png`, `snapshot_*.json`, `snapshot_*.npy`, `snapshot_*.npz` (si serie activa)
  - Derivados: features (`*.npz`) y QC (`*.qc.json`) bajo `aetherlab/data/features/` (ETL)
  - Comparación: figura retornada por endpoint (PNG/SVG/PDF) (no persistida por defecto)

## Migraciones
- Migración ligera en arranque (sin Alembic): tabla `schema_migrations` y `ALTER TABLE` idempotentes para columnas nuevas.

## Asíncrono y Estados
- BackgroundTasks: ejecución inline del proceso de app.
- RQ/Redis: job en cola “aetherlab”, estado vía `job_id`. `get_run` mappea a `queued/running/failed/finished`.

## Seguridad y Configuración
- Variables de entorno: `AETHERLAB_DB_URL`, `REDIS_URL`.
- Sin secretos en repositorio. Archivos generados se guardan fuera de código.

## Operación / CI
- `docker-compose.yml` levanta API + Postgres + Redis y define healthchecks.
- CI usa caching de pip para estabilizar tiempos de instalación.

## Limitaciones conocidas
- Algunos entornos de desarrollo pueden no tener Docker disponible; en ese caso, la verificación de Compose debe hacerse en una máquina con Docker Desktop/Engine.
- Warnings actuales en runtime:
  - FastAPI: deprecación de `on_event` (migrable a lifespan).
  - Pydantic: warning por `model_name` en el namespace protegido.

## Extensibilidad
- Nuevas fuentes y operadores: añadir a `sources.py` y/o `simulator2d.py`.
- Nuevas métricas: implementar en `metrics.py` y añadir endpoints UI.
- Integración con AI: pipeline de entrenamiento sobre series .npz, inferencia de parámetros, o detectores de eventos con PyTorch/TF.

## Consideraciones epistemológicas
- El sistema facilita exploración computacional rigurosa.
- Todo resultado debe presentarse como:
  - “hipótesis de trabajo” o “modelo fenomenológico”, no prueba de existencia del Aether.
  - Métricas físicas estándar como evidencia de comportamiento numérico, no de ontología del campo.
