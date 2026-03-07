# Documento Técnico de AETHERLAB

## Resumen
Plataforma para simulación y análisis de un campo 2D con backend FastAPI, ejecución asíncrona conmutables (BackgroundTasks/RQ+Redis), almacenamiento de artefactos (PNG, NPY, NPZ, JSON) y UI en PyQt6 para exploración.

## Arquitectura
- Capa de simulación (`aetherlab/packages/aether_sim`):
  - `simulator2d.py`: malla 2D, integración temporal con `dt`, `steps`, `lam`, `diff`, `noise` y `boundary` (periodic/fixed/absorbing). Permite `set_source` y `callback` por paso para muestrear series.
  - `sources.py`: fuentes `gaussian_pulse`, `periodic_gaussian`, `stochastic`, `top_hat`, `lorentzian`.
  - `metrics.py`: `compute_metrics` (energía, media, varianza, correlación inmediata), `autocorr2d`, `power_spectrum_radial`.
- Capa API (`aetherlab/apps/api`):
  - Gestión de proyectos, experimentos y runs.
  - Simulación síncrona (`POST /simulate/simple`) y asíncrona (`POST /simulate/async`).
  - Endpoints de resultados: snapshot, métricas, campo (.npy), serie (.npz), métricas de serie, espectro radial, autocorrelación 2D.
  - Estado de runs con polling de Redis si `REDIS_URL` y `job_id` presente. Abort/Retry/Cleanup para RQ.
- Capa UI (`aetherlab/apps/desktop`):
  - Control de parámetros (fuente, boundary, steps, dt, amplitud, etc.).
  - Pestañas de visualización: energía vs tiempo, espectro radial (lineal/log), autocorrelación 2D con recorte.
  - Gestión de runs: estado, abortar, reintentar, descarga de artefactos y export de métricas CSV.
- Capa Core (`aetherlab/packages/aether_core`):
  - ORM SQLAlchemy. Modelos `Project`, `Experiment`, `SimulationRun` (incluye `job_id`).
  - DB configurable por `AETHERLAB_DB_URL` (SQLite por defecto). Ajuste de esquema en arranque.
- Worker (`scripts/rq_worker.py`):
  - Consume cola RQ “aetherlab”, ejecuta simulaciones, guarda artefactos y actualiza `SimulationRun`.

## Flujo de Datos
1) UI o cliente REST solicita crear proyecto/experimento.
2) Se lanza `POST /simulate/simple` (bloqueante) o `POST /simulate/async` (en cola o background).
3) El simulador produce `sim.u`. Se guardan PNG/JSON y opcionalmente NPY/NPZ.
4) La API registra un `SimulationRun` con `status` y `snapshot_path`. En modo RQ, guarda `job_id`.
5) La UI consulta `/runs/{id}` para estado, y `/figures/...` para artefactos y métricas.

## Esquema ORM
- `Project(id, name, description, created_at)`
- `Experiment(id, project_id, name, created_at)`
- `SimulationRun(id, experiment_id, status, created_at, snapshot_path, job_id)`

## Endpoints Principales
- Proyectos/Experimentos: `POST/GET /projects`, `POST/GET /experiments`
- Runs: `GET /runs`, `GET /runs/{id}`, `POST /runs/{id}/refresh`, `POST /runs/{id}/abort`, `POST /runs/{id}/retry`, `POST /runs/{id}/cleanup`
- Simulación: `POST /simulate/simple`, `POST /simulate/async`
- Resultados: `GET /figures/{run}/snapshot|metrics|field|series|series-metrics|spectrum|autocorr`

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

## Asíncrono y Estados
- BackgroundTasks: ejecución inline del proceso de app.
- RQ/Redis: job en cola “aetherlab”, estado vía `job_id`. `get_run` mappea a `queued/running/failed/finished`.

## Seguridad y Configuración
- Variables de entorno: `AETHERLAB_DB_URL`, `REDIS_URL`.
- Sin secretos en repositorio. Archivos generados se guardan fuera de código.

## Extensibilidad
- Nuevas fuentes y operadores: añadir a `sources.py` y/o `simulator2d.py`.
- Nuevas métricas: implementar en `metrics.py` y añadir endpoints UI.
- Integración con AI: pipeline de entrenamiento sobre series .npz, inferencia de parámetros, o detectores de eventos con PyTorch/TF.

