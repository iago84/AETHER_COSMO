# Checklist del Proyecto (AETHER_COSMO / AETHERLAB)

## Estado actual (resumen)

**Hecho (base funcional / MVP)**
- Simulador 2D y métricas básicas: `aetherlab/packages/aether_sim/*`, `aetherlab/packages/aether_physics/numerics.py`
- API FastAPI con proyectos/experimentos/runs, figuras, datos/ETL e IA baseline: `aetherlab/apps/api/main.py`
- UI PyQt6 mínima con ejecución, plots (energía/espectro/autocorr), ROI y export: `aetherlab/apps/desktop/main.py`
- ORM/DB con entidades base y extensiones (Artifact/Figure/Tag/Annotation/Version): `aetherlab/packages/aether_core/models_db.py`
- CI de lint/tests y suite de tests: `.github/workflows/*`, `tests/*`
- Documentación inicial: `docs/*`, `README.md`, `ROADMAP.md`

**Parcial**
- Reportes: hay endpoints en API y script HTML, pero el paquete `aether_report` está en stub (`aetherlab/packages/aether_report/builder.py`)
- Trazabilidad completa: existe `Artifact`/`Figure`, pero falta completar el flujo “registrar todo lo generado” de forma sistemática (ETL/IA/Reportes)
- UI: ROI y export existen, pero faltan vistas de datos/IA/comparación/reportes con flujo “proyecto→experimento→runs→datasets”

**Pendiente (para v1)**
- Motor comparativo (sim↔sim, sim↔dataset, dataset↔baseline) con reportes automáticos
- ETL más realista (features y normalizaciones) y control de calidad de datos
- IA avanzada sobre series/ventanas y guardado de artefactos/modelos
- Endurecimiento de API (validación, seguridad si se expone fuera de localhost)
- DevOps de despliegue (si el objetivo es producción): configuración y guía operativa

## Checklist (MVP → v1)

### UI Desktop (PyQt6)
- [ ] Selector de proyecto/experimento (crear/listar/seleccionar)
- [ ] Panel lateral de parámetros con presets y validación explícita
- [ ] Pestañas adicionales: Datos, IA, Comparación, Reportes, Configuración
- [ ] Estados y progreso de jobs (queued/running/failed) con mensajes consistentes
- [ ] Export unificado (CSV/PNG/NPZ/MP4/HTML) con diálogo y rutas claras

### API
- [ ] Endpoints de comparación run↔run y run↔dataset (métricas + figuras)
- [ ] Consolidar endpoints de reportes (run y experimento) con enlaces a artefactos
- [ ] Validación y errores homogéneos (pydantic + HTTP errors consistentes)
- [ ] Política de timeouts/limitación de payloads (especialmente descargas)
- [ ] Seguridad mínima si aplica (rate limit/auth para despliegue fuera de localhost)

### Simulación / Cálculos / Métricas
- [ ] Validaciones de estabilidad (dt/lam/diff/noise) y límites en UI/API
- [ ] Métricas comparativas (distancias, correlación, similitud estructural)
- [ ] Barridos de parámetros reproducibles y registro de configuraciones
- [ ] Serie temporal: métricas por frame y export consistente (API/UI)

### Datos / ETL
- [ ] ETL con normalizaciones (z-score/min-max) y features mejoradas (ventanas/espectral)
- [ ] Control de calidad de datos (nans, rangos, warnings, summary)
- [ ] Registro de datasets con trazabilidad (hash/mtime/origen) y versionado simple
- [ ] Vinculación experimento↔dataset con flujos completos desde UI y API

### IA
- [ ] Formalizar “ModelRun” end-to-end (params, métricas, estado, outputs)
- [ ] IA sobre series/ventanas (no solo snapshots) con pipelines reproducibles
- [ ] Guardado de artefactos (CSV/figuras/modelos) y descarga segura
- [ ] Visualizaciones rápidas (PCA/plots) integradas con el flujo de runs/datasets

### Reportes / Visualización
- [ ] Implementar `aether_report` (builder real) reutilizando la lógica del script HTML
- [ ] Reporte de experimento (parámetros + datasets + runs + métricas + figuras + notas)
- [ ] Export académico adicional si se necesita (SVG/PDF) y estilos consistentes

### Core / DB
- [ ] Añadir migraciones (Alembic u otro) para evolucionar el esquema sin hacks
- [ ] Registrar sistemáticamente artefactos (ETL/IA/reportes) en la tabla `artifacts`
- [ ] Guardar configuración completa de runs y seeds para reproducibilidad

### DevOps / CI
- [ ] Docker Compose verificado (API+Redis+Postgres) y variables de entorno validadas
- [ ] Healthchecks y logs adecuados para operación
- [ ] CI con caching (pip) y tiempos estables

### QA
- [ ] Lint (ruff) sin errores
- [ ] Tests (pytest) pasando en limpio
- [ ] Smoke manual: API + UI + export (snapshot/series/reportes)

### Docs / Experimentos
- [ ] Manual de usuario actualizado con capturas y flujos (UI/API)
- [ ] Documento técnico alineado con el estado real del código y limitaciones
- [ ] Protocolo de experimentos reproducibles (plantilla + buenas prácticas)

