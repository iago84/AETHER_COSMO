# Experimentos Propuestos (Sistema y AI)

## Hipótesis de trabajo y criterios
- Hipótesis de trabajo: campo fenomenológico con “memoria” de eventos; objetivo es explorar firmas computacionales.
- Criterios:
  - Diferenciar métricas físicas (espectro/autocorr/energía) de interpretaciones fenomenológicas.
  - Mantener reproducibilidad: series NPZ, parámetros exactos, seeds y versiones.
  - Documentar limitaciones: el sistema no valida la existencia del Aether; habilita exploración rigurosa.

## Comparativa de fuentes
- Objetivo: Evaluar propagación y energía para `gaussian_pulse`, `periodic`, `stochastic`, `top_hat`, `lorentzian`.
- Diseño: Misma malla y parámetros (nx, ny, dt, steps), varia `source_kind` y parámetros clave (sigma/radius/gamma).
- Métricas: energía final/temporal, espectro radial, autocorrelación 2D.
- Resultado esperado: perfiles espectrales característicos por fuente; correlaciones más amplias para top-hat/lorentziana.

## Estudio de condiciones de contorno
- Objetivo: Medir efectos de reflection/absorción en `periodic`, `fixed`, `absorbing`.
- Diseño: Fuente pulsada centrada; comparar energía en bordes y espectro.
- Métricas: energía vs tiempo, energía en anillos periféricos, espectro.

## Barrido de parámetros (diff, dt, lam, noise)
- Objetivo: Analizar estabilidad y suavizado.
- Diseño: grid de {diff, dt, lam, noise}; guardar series con stride fijo.
- Métricas: energía media, varianza, decaimiento de correlación, cambio del pico espectral.
- Resultado: mapas calor de energía/correlación vs parámetros.

## Efecto del ruido
- Objetivo: Impacto del `noise` en estructuras espaciales.
- Diseño: runs con noise ∈ {0, 0.01, 0.05, 0.1}; fuente periodic.
- Métricas: crecimiento de potencia en alta k; reducción de autocorrelación.

## Dinámica transitoria vs régimen estacionario
- Objetivo: Caracterizar convergencia temporal.
- Diseño: series largas con periodic, medir energía y espectro en ventanas.
- Métricas: tiempo hasta estacionariedad; deriva del pico espectral.

## Experimentos con AI (extensiones)
- Predicción temporal:
  - Entrenar modelos (LSTM/Temporal CNN/Transformer) sobre series NPZ para predecir frames futuros.
  - Métrica: MSE/PSNR sobre frames; fidelidad espectral.
- Inferencia de parámetros:
  - Regresor que, dado un segmento de la serie, infiere (dt, diff, lam, sigma/gamma/radius).
  - Métrica: error MAE/MAPE por parámetro, robustez a ruido.
- Detección de eventos:
  - Clasificador que detecte aparición de patrones (picos de energía, anillos en espectro).
  - Métrica: precisión/recuperación, F1, tasa de falsos positivos.

## Experimentos con datos reales (ETL + IA)
- Planck (mapas 2D):
  - Pipeline: loader → ETL (`POST /etl/dataset`, features NPZ + QC) → IA baseline (IsolationForest/mean_dist) → CSV de scores → análisis.
  - Indicadores: distribución de scores y correlación con métricas de textura (energía/localidad).
- GWOSC (strain 1D):
  - Pipeline: loader → ETL (`POST /etl/dataset`) → IA baseline → CSV → análisis temporal.
- SDSS (tablas):
  - Pipeline: selección de columnas relevantes → features (p.ej. normalización, PCA previa) → IA/clustering.

## Protocolos de ejecución
1) Crear experimento y configurar parámetros (UI o API).
2) Activar `save_series=true` con `series_stride` adecuado en runs.
3) Registrar datasets y vincular a experimentos.
4) Ejecutar ETL y IA sobre datasets/runs (endpoints dedicados).
5) Exportar CSV/HTML, comparar (run↔run / run↔dataset) y revisar figuras y métricas.
6) Documentar hipótesis asociada y observaciones.

## Protocolo reproducible (paso a paso)
1) Preparación
   - Registrar versión del código (commit/tag) y el entorno (Python, SO, dependencias).
   - Verificar API: `GET /health`.
2) Crear estructura en DB
   - `POST /projects` → `project_id`
   - `POST /experiments` → `experiment_id`
3) Ejecución de runs (síncrono y asíncrono)
   - Síncrono (1 run): `POST /simulate/simple` con `seed` explícita y `config` completa.
   - Asíncrono (colas): `POST /simulate/async` con `seed` explícita o determinista y `save_series` si se necesita serie.
   - Guardar siempre el `run_id` retornado.
4) Barridos reproducibles (campañas)
   - `POST /sweeps/grid` con:
     - `base`: configuración base completa (incluye `nx/ny/dt/lam/diff/noise/source_kind/...`).
     - `grid`: parámetros a variar (p.ej. `{"lam":[0.1,0.2], "diff":[0.2,0.4]}`).
     - `seed_base`: para generar seeds deterministas por combinación.
   - Guardar `run_ids` como “manifiesto” del barrido (orden y parámetros).
5) Auditoría de configuración y estado
   - `GET /runs?experiment_id={id}` para listar runs del experimento.
   - `GET /runs/{run_id}` para:
     - `status` y backend (`background`/`rq`)
     - `seed` y `config` (configuración reproducible)
6) Export de artefactos y evidencias
   - Campo/figuras:
     - `GET /figures/{run}/snapshot` (PNG)
     - `GET /figures/{run}/snapshot.svg` (SVG)
     - `GET /figures/{run}/snapshot.pdf` (PDF)
     - `GET /figures/{run}/field` (NPY)
   - Series:
     - `GET /figures/{run}/series` (NPZ)
     - `GET /figures/{run}/series-metrics.csv` (CSV)
   - Reporte:
     - `GET /reports/run/{run}/html` (HTML)
7) Comparación y validación cruzada
   - run↔run:
     - `GET /compare/run-run?run_a=...&run_b=...`
     - Figura: `GET /compare/run-run/figure.png|.svg|.pdf?...`
   - run↔dataset:
     - `GET /compare/run-dataset?...`
   - Métricas clave: `mse`, `rmse`, `nrmse`, `corr`, `ssim`, `spectrum_l2`.
8) Datos reales (ETL + IA)
   - Registrar dataset: `POST /datasets`
   - Vincular a experimento: `POST /experiments/{eid}/datasets/link?dataset_id=...`
   - ETL: `POST /etl/dataset` (incluye `normalize` + `qc`)
   - Artefactos: `GET /artifacts?dataset_id=...` y/o `GET /artifacts?experiment_id=...`
9) Cierre del experimento
   - Guardar una ficha con:
     - objetivo + hipótesis
     - lista de `run_id` (y `run_ids` del barrido)
     - parámetros/semillas (desde `config` de cada run)
     - artefactos exportados (archivos locales) y métricas resumidas

## Plantilla de Ficha de Experimento
- Identificación:
  - Proyecto / Experimento / Fecha / Autor
- Hipótesis de trabajo:
  - Describir la hipótesis asociada (lenguaje prudente, no concluyente)
- Objetivo:
  - Qué patrón/efecto se busca observar/cuantar
- Parámetros de simulación (si aplica):
  - nx, ny, dt, steps, boundary, source_kind, {sigma|gamma|radius|amplitude}, lam, diff, noise
- Datasets vinculados (si aplica):
  - Lista de `dataset_id`, nombre, path de origen y preprocesado (ETL)
- Protocolo:
  - Pasos ejecutados (endpoints, opciones de UI, orden)
- Métricas y figuras:
  - Energía vs tiempo, espectro radial (lineal/log), autocorrelación 2D (crop)
  - Enlaces a artefactos: PNG/NPY/NPZ/CSV (ruta relativa bajo `aetherlab/data`)
- Resultados IA:
  - Método (isoforest|mean_dist|dbscan), parámetros, ruta CSV y resumen de scores
- Observaciones:
  - Hallazgos cualitativos y cuantitativos; discrepancias; próximos pasos
- Limitaciones:
  - Suposiciones del modelo numérico y del ETL; fuentes de error
- Reproducibilidad:
  - Seed, versión de código, versión de datasets, hardware, tiempos

## Ejemplo de reporte (estructura)
- Resumen:
  - Breve descripción del objetivo y del setup
- Figuras:
  - Snapshot (PNG) del campo
  - Energía vs tiempo (PNG/CSV)
  - Espectro radial (PNG) e interpretación
  - Autocorrelación 2D (PNG) con distinto `crop`
- Datos:
  - Enlaces a NPZ/NPY de serie/campo y CSV de IA
- Conclusiones:
  - Qué se observó, qué falta por validar, próximos experimentos

## Ficha de Experimento (Ejemplo) – Run simulado
- Identificación:
  - Proyecto: “Exploración fuentes periódicas” / Experimento: “Periodic-01” / Fecha: 2026-03-09 / Autor: Equipo AETHERLAB
- Hipótesis de trabajo:
  - La fuente periódica genera patrones estables detectables en espectro radial y autocorrelación; la “memoria” sería observada como persistencia espacial-temporal.
- Objetivo:
  - Cuantificar estabilidad temporal y localizar pico espectral.
- Parámetros de simulación:
  - nx=128, ny=128, dt=0.02, steps=600, boundary=absorbing, source_kind=periodic_gaussian, amplitude=1.0, sigma=10, frequency=0.4, lam=0.0, diff=0.02, noise=0.0
- Protocolo:
  - POST /simulate/simple con `save_series=true` y `series_stride=10`.
  - GET /figures/{run}/series para NPZ; GET /figures/{run}/spectrum y /autocorr con `crop` ajustado.
- Métricas y figuras:
  - Energía vs tiempo (PNG); Espectro radial (PNG, lineal/log); Autocorr 2D (PNG).
- Resultados IA:
  - POST /ai/run-on-run con `{"run_id": X, "method": "isoforest"}`; descargar CSV con GET /ai/download?path=...
- Observaciones:
  - Pico espectral estable; autocorrelación centrada con decaimiento radial; puntuaciones IA bajas (sin anomalías).
- Limitaciones:
  - Modelo numérico simplificado; sin validación externa.
- Reproducibilidad:
  - Seed 0 (fuente periódica determinista), versión commit, hardware local (CPU 8 hilos).

## Ficha de Experimento (Ejemplo) – Dataset Planck
- Identificación:
  - Proyecto: “Comparativa mapas CMB” / Experimento: “Planck-Maps-ETL-01” / Fecha: 2026-03-09 / Autor: Equipo AETHERLAB
- Hipótesis de trabajo:
  - Los mapas CMB presentan texturas estadísticas que pueden compararse con simulaciones; la “memoria” se explora como persistencia de firmas en features.
- Objetivo:
  - Generar features reproduci­bles y evaluar detección de anomalías básica.
- Datasets vinculados:
  - `dataset_id=42`, name: “planck-local”, path: `C:\data\planck\map.npy` (archivo local predescargado).
- Protocolo:
  - POST /datasets con name/path; POST /experiments/{eid}/datasets/link?dataset_id=42.
  - POST /ai/run-on-dataset `{"dataset_id": 42, "method": "mean_dist"}`; GET /ai/download?path=...
  - Opcional: ejecutar ETL previo con módulo `aetherlab/packages/aether_data/etl.py` para features NPZ.
- Métricas y figuras:
  - Estadísticos de textura (energía/media/varianza) y distribución de scores.
- Resultados IA:
  - CSV de scores por bloque/patch; análisis simple de percentiles.
- Observaciones:
  - Puntuaciones distribuidas según esperados de textura estadística; sin afirmaciones ontológicas.
- Limitaciones:
  - Preprocesado local; falta de calibración cruzada con catálogos completos.
- Reproducibilidad:
  - Guardar hash/mtime del archivo en ETL; registrar commit y entorno.

## Protocolo de ejecución
1) Crear experimento y configurar parámetros (UI o API).
2) Activar `save_series=true` con `series_stride` adecuado.
3) Ejecutar runs en cola (RQ) para barridos extensos.
4) Recopilar NPZ/JSON; exportar CSV de métricas desde la UI.
5) Analizar espectros y autocorrelaciones; si aplica, entrenar modelos AI con las series.

## Reporte de resultados
- Incluir resumen de parámetros, artefactos (PNG, CSV), y gráficos:
  - Energía vs tiempo (varias condiciones).
  - Espectro radial comparado (por fuente o parámetro).
  - Autocorrelación 2D recortada.
