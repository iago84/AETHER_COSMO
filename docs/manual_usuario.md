# Manual de Usuario

## Instalación
1) Instalar dependencias:

```bash
pip install -r requirements.txt
```

2) Inicializar base de datos (si corresponde):

```bash
python scripts\init_db.py
```

## Ejecución de la API

```bash
uvicorn aetherlab.apps.api.main:app --host 127.0.0.1 --port 8000
```

Opcional (asíncrono con RQ/Redis):

```powershell
$env:REDIS_URL="redis://localhost:6379/0"
python scripts\rq_worker.py
```

## Flujo básico (API)

1) Crear proyecto y experimento (ejemplo con Python/urllib):

```python
import json, urllib.request

base="http://127.0.0.1:8000"
req = urllib.request.Request(
  base+"/projects",
  data=json.dumps({"name":"Demo","description":"Proyecto"}).encode(),
  headers={"Content-Type":"application/json"},
)
project = json.loads(urllib.request.urlopen(req).read().decode())
req = urllib.request.Request(
  base+"/experiments",
  data=json.dumps({"project_id": project["id"], "name":"Exp1"}).encode(),
  headers={"Content-Type":"application/json"},
)
experiment = json.loads(urllib.request.urlopen(req).read().decode())
print(project, experiment)
```

2) Lanzar simulación síncrona:

```python
payload={
  "experiment_id": experiment["id"],
  "nx": 128, "ny": 128,
  "steps": 120, "dt": 0.05,
  "lam": 0.5, "diff": 0.2, "noise": 0.0,
  "seed": 123,
  "boundary": "absorbing",
  "source_kind": "lorentzian",
  "cx": 64, "cy": 64,
  "gamma": 9.0, "sigma": 10, "duration": 20, "amplitude": 1.0,
  "save_series": True, "series_stride": 10,
}
req = urllib.request.Request(base+"/simulate/simple", data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"})
print(urllib.request.urlopen(req).read().decode())
```

3) Consultar resultados:

- `GET /runs` y `GET /runs/{id}`
- `GET /figures/{id}/snapshot|metrics|field|series|series-metrics|spectrum|autocorr?crop=96`
- Export académico:
  - `GET /figures/{id}/snapshot.svg` y `GET /figures/{id}/snapshot.pdf`

4) Asíncrono:

- `POST /simulate/async` → devuelve `run_id` (y `job_id` si RQ).
- `GET /runs/{id}` para el estado; `abort`/`retry` disponibles en RQ.

5) Barridos reproducibles:

- `POST /sweeps/grid` con `base` + `grid` → devuelve `run_ids`.
- Consultar por experimento:
  - `GET /runs?experiment_id={id}`

## UI de Escritorio (PyQt6)

```bash
python aetherlab\apps\desktop\main.py
```

### Controles
- API base (por defecto `http://127.0.0.1:8000`).
- Selector de proyecto y experimento (crear/refrescar/seleccionar).
- Parámetros de simulación:
  - Tamaño: `nx`, `ny`
  - Dinámica: `steps`, `dt`, `lam`, `diff`, `noise`
  - Fuente: `source_kind` + parámetros (`sigma`, `radius`, `gamma`, `frequency`, `duration`, `amplitude`)
  - Posición fuente: `cx`, `cy`
  - Seed: “Seed auto” (sin seed explícita) o seed fijo
  - Presets: atajos para configurar parámetros típicos
- Ejecución:
  - “Asíncrono” para usar `/simulate/async`
  - “Auto refrescar” para polling de estado
- Guardar serie: “Guardar serie” y `stride`.
- run_id y estado con botones: Actualizar, Abortar, Reintentar (si RQ).
- Export unificado: Reporte HTML, métricas CSV, snapshot PNG/SVG/PDF, serie NPZ, campo NPY, ROI CSV, MP4.
- Reproducción de series: “Reproducir/Parar” y control de frame actual.

### Visualización
- Energía vs tiempo (desde serie NPZ).
- Espectro radial (lineal o log).
- Autocorrelación 2D (recorte configurable).

### Pestañas adicionales
- Datos: listar datasets, ver meta, ejecutar ETL y ver artefactos asociados.
- IA: ejecutar IA sobre run o dataset y listar ModelRuns del experimento.
- Comparación: run↔run y run↔dataset con métricas y figura.
- Reportes: cargar HTML de run/experimento y guardar localmente.
- Configuración: `GET /health` para comprobar estado del API.

### Flujo recomendado en UI
1) Ajusta parámetros y pulsa “Simular (API)”.  
2) Pulsa “Actualizar estado” si usas asíncrono hasta ver “finished”.  
3) Usa “Cargar serie (NPZ)” para ver energía vs tiempo.  
4) Pulsa “Espectro (API)” y marca “Espectro en log” si quieres escala log.  
5) Pulsa “Autocorr (API)” y ajusta “crop” para inspección local.  
6) Descarga artefactos o exporta CSV para análisis externo.

### Capturas (pendiente de incorporar al manual)
- Pantalla principal con selector de proyecto/experimento y presets.
- Ejecución asíncrona mostrando estado `queued/running/finished` y backend.
- Export unificado con snapshot SVG/PDF.
- Pestaña Comparación con métricas (mse/ssim/nrmse) y figura.
- Pestaña IA con “PCA serie”.

## Datos y IA

### Registrar datasets en DB
- Crear un dataset:
  - `POST /datasets` con `{"name": "...", "path": "ruta_local", "description": "opcional"}`
- Listar datasets:
  - `GET /datasets`

### Vincular dataset a experimento
- `POST /experiments/{experiment_id}/datasets/link?dataset_id={id}`
- Listar vínculos del experimento:
  - `GET /experiments/{experiment_id}/datasets`

### Ejecutar IA
- Sobre un run:
  - `POST /ai/run-on-run` con `{"run_id": X, "method": "isoforest|mean_dist"}`
  - Descarga de resultados CSV:
    - `GET /ai/download?path=...` (ruta devuelta por el endpoint)
- Sobre un dataset:
  - `POST /ai/run-on-dataset` con `{"dataset_id": X, "method": "isoforest|mean_dist"}`
  - Descarga de resultados CSV:
    - `GET /ai/download?path=...`
 - Visualización PCA:
   - `POST /ai/pca-plot` con `{"X": [[...], ...]}` → devuelve PNG embebido (base64).

## Consejos
- Si el espectro muestra alta energía en alta k, reduce `dt` o aumenta `diff`.
- Con `boundary=absorbing` minimizarás reflexiones; útil para fuentes pulsadas.
- `save_series` genera NPZ; evita strides muy pequeños en simulaciones largas.

## Reproducibilidad y reportes
- Fijar seed y anotar commit/versión del código.
- Registrar parámetros exactos y entorno (CPU/GPU, librerías).
- Usar reportes HTML:
  - `GET /reports/run/{id}/html` y `GET /reports/experiment/{id}/html`.
- Comparación:
  - `GET /compare/run-run` y `GET /compare/run-dataset` (+ `.../figure.png|.svg|.pdf`).
- Limpieza de datos:
  - `POST /data/cleanup?days=30` para eliminar outputs/features antiguos.
