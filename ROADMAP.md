# Hoja de Ruta y Checklist

## Estado por Fase
- Hecho
  - Arquitectura modular y ORM base.
  - API FastAPI con simulación síncrona/asíncrona y endpoints de resultados.
  - UI PyQt6 mínima con pestañas Energía/Espectro/Autocorr y export.
  - Baseline IA: IsolationForest, outlier-score rápido, DBSCAN + endpoints.
  - Ingesta de datos: registry y loaders Planck/GWOSC/SDSS, endpoints /data.
  - DB ampliada: datasets, model_runs y vínculos básicos.
  - CI con lint y tests básicos en Actions.
- Parcial
  - Esquema DB extendido con figuras/artefactos/versions/tags/annotations.
  - Scripts/reportes HTML y flujos de export avanzados.
  - UI: controles de serie con reproducción y frame actual.
- Pendiente
  - ETL reproducible raw/processed/features con caché y trazabilidad.
  - Endpoints de ejecución IA sobre snapshots/datasets con guardado y descarga.
  - Vinculación completa experimento↔dataset y comparativas.
  - UI: selección de ROI y exportación avanzada.
  - Documentación técnica extendida y publicación.
  - Docker Compose y CI/CD de despliegue.

## Siguientes Pasos
- Implementar ETL reproducible en aether-data con estructura raw/processed/features y caché local.
- Añadir endpoints para vincular datasets a experimentos y ejecutar modelos IA sobre snapshots/datasets con guardado (CSV/JSON) y descarga.
- Extender UI PyQt6 para animaciones, selección de ROI y export avanzada.
- Mantener este checklist y enlazar módulos/endpoints clave.

## Enlaces Clave
- API: aetherlab/apps/api/main.py
- Simulador: aetherlab/packages/aether_sim/simulator2d.py
- IA baseline: aetherlab/packages/aether_ai/baseline.py
- Datos: aetherlab/packages/aether_data/registry.py, aetherlab/packages/aether_data/etl.py
- UI: aetherlab/apps/desktop/main.py
