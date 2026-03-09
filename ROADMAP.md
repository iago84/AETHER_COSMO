# Hoja de Ruta y Checklist

## Estado por Fase
- Hecho
  - Arquitectura modular y ORM base.
  - API FastAPI con simulación síncrona/asíncrona y endpoints de resultados.
  - UI PyQt6 mínima con pestañas Energía/Espectro/Autocorr y export.
  - Baseline IA: IsolationForest, outlier-score rápido, DBSCAN + endpoints.
  - Ingesta de datos: registry y loaders Planck/GWOSC/SDSS, endpoints /data.
  - DB ampliada: datasets, model_runs y vínculos básicos.
  - ETL reproducible raw/processed/features con caché y trazabilidad.
  - Endpoints de ejecución IA sobre snapshots/datasets con guardado y descarga.
  - Vinculación experimento↔dataset y listados.
  - CI con lint y tests básicos en Actions.
- Parcial
  - Esquema DB extendido con figuras/artefactos/versions/tags/annotations.
  - Scripts/reportes HTML y flujos de export avanzados.
  - UI: selección de ROI y exportación avanzada.
  - Documentación técnica extendida (manual, técnico, requisitos, experimentos) y publicación.
- Pendiente
  - Comparativas completas experimento↔dataset y reportes automatizados.
  - Docker Compose y CI/CD de despliegue.

## Siguientes Pasos
- Completar UI: ROI interactivo y export de métricas/MP4.
- Trazabilidad: registrar artifacts/outputs de ETL/IA en DB (ModelRun + Artifact).
- Reportes: plantilla HTML/Markdown automatizada con enlaces a artefactos.
- Publicación: documentación hospedada (MkDocs/Sphinx) y guía de experimentos.
- Despliegue: Docker Compose y CI/CD.

## Enlaces Clave
- API: aetherlab/apps/api/main.py
- Simulador: aetherlab/packages/aether_sim/simulator2d.py
- IA baseline: aetherlab/packages/aether_ai/baseline.py
- Datos: aetherlab/packages/aether_data/registry.py, aetherlab/packages/aether_data/etl.py
- UI: aetherlab/apps/desktop/main.py
