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
req = urllib.request.Request(base+"/projects", data=json.dumps({"name":"Demo","description":"Proyecto"}).encode(), headers={"Content-Type":"application/json"})
print(urllib.request.urlopen(req).read().decode())
req = urllib.request.Request(base+"/experiments", data=json.dumps({"project_id":1,"name":"Exp1"}).encode(), headers={"Content-Type":"application/json"})
print(urllib.request.urlopen(req).read().decode())
```

2) Lanzar simulación síncrona:

```python
payload={
  "experiment_id":1, "steps":80, "boundary":"absorbing",
  "source_kind":"lorentzian", "gamma":9.0, "sigma":10, "amplitude":1.0,
  "save_series": True, "series_stride": 10
}
req = urllib.request.Request(base+"/simulate/simple", data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"})
print(urllib.request.urlopen(req).read().decode())
```

3) Consultar resultados:

- `GET /runs` y `GET /runs/{id}`
- `GET /figures/{id}/snapshot|metrics|field|series|series-metrics|spectrum|autocorr?crop=96`

4) Asíncrono:

- `POST /simulate/async` → devuelve `run_id` (y `job_id` si RQ).
- `GET /runs/{id}` para el estado; `abort`/`retry` disponibles en RQ.

## UI de Escritorio (PyQt6)

```bash
python aetherlab\apps\desktop\main.py
```

### Controles
- Parámetros de simulación: fuente, boundary, steps, dt, amplitud, sigma, radius, gamma, frequency.
- Guardar serie y stride.
- run_id y estado con botones: Actualizar, Abortar, Reintentar (si RQ).
- Descargas: snapshot (PNG), serie (NPZ), campo (NPY), export de métricas CSV.
 - Reproducción de series: botones “Reproducir/Parar” y control de frame actual.

### Visualización
- Energía vs tiempo (desde serie NPZ).
- Espectro radial (lineal o log).
- Autocorrelación 2D (recorte configurable).

### Flujo recomendado en UI
1) Ajusta parámetros y pulsa “Simular (API)”.  
2) Pulsa “Actualizar estado” si usas asíncrono hasta ver “finished”.  
3) Usa “Cargar serie (NPZ)” para ver energía vs tiempo.  
4) Pulsa “Espectro (API)” y marca “Espectro en log” si quieres escala log.  
5) Pulsa “Autocorr (API)” y ajusta “crop” para inspección local.  
6) Descarga artefactos o exporta CSV para análisis externo.

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

## Consejos
- Si el espectro muestra alta energía en alta k, reduce `dt` o aumenta `diff`.
- Con `boundary=absorbing` minimizarás reflexiones; útil para fuentes pulsadas.
- `save_series` genera NPZ; evita strides muy pequeños en simulaciones largas.
