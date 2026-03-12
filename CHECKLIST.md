# Checklist del Proyecto (AETHER_COSMO / AETHERLAB)

## Estado actual (resumen)

**Hecho (base funcional / MVP)**
- Simulador 2D y métricas básicas: `aetherlab/packages/aether_sim/*`, `aetherlab/packages/aether_physics/numerics.py`
- API FastAPI con proyectos/experimentos/runs, figuras, datos/ETL e IA baseline: `aetherlab/apps/api/main.py`
- UI PyQt6 con selector de proyecto/experimento, parámetros, pestañas y export: `aetherlab/apps/desktop/main.py`
- ORM/DB con entidades base y extensiones (Artifact/Figure/Tag/Annotation/Version): `aetherlab/packages/aether_core/models_db.py`
- CI de lint/tests y suite de tests: `.github/workflows/*`, `tests/*`
- Documentación inicial: `docs/*`, `README.md`, `ROADMAP.md`

**Parcial**
- Visualizaciones rápidas (PCA/plots) aún no integradas con el flujo de runs/datasets

**Pendiente (para v1)**
- Guardado de modelos entrenados y sus artefactos (versionado / descarga)
- Validaciones de estabilidad más estrictas (dt/lam/diff/noise) y límites explícitos en UI
- DevOps de despliegue (si el objetivo es producción): configuración y guía operativa

## Checklist (MVP → v1)

### UI Desktop (PyQt6)
- [x] Selector de proyecto/experimento (crear/listar/seleccionar)
- [ ] Panel lateral de parámetros con presets y validación explícita
- [x] Pestañas adicionales: Datos, IA, Comparación, Reportes, Configuración
- [ ] Estados y progreso de jobs (queued/running/failed) con mensajes consistentes
- [x] Export unificado (CSV/PNG/NPZ/MP4/HTML) con diálogo y rutas claras

### API
- [x] Endpoints de comparación run↔run y run↔dataset (métricas + figuras)
- [x] Consolidar endpoints de reportes (run y experimento) con enlaces a figuras embebidas
- [x] Validación y errores homogéneos (pydantic + HTTP errors consistentes)
- [x] Política de timeouts/limitación de payloads (especialmente descargas)
- [x] Seguridad mínima si aplica (rate limit/auth para despliegue fuera de localhost)

### Simulación / Cálculos / Métricas
- [x] Validaciones de estabilidad (dt/lam/diff/noise) y límites en UI/API
- [ ] Métricas comparativas (distancias, correlación, similitud estructural)
- [ ] Barridos de parámetros reproducibles y registro de configuraciones
- [x] Serie temporal: métricas por frame y export consistente (API/UI)

### Datos / ETL
- [x] ETL con normalizaciones (z-score/min-max) y features mejoradas (ventanas/espectral)
- [x] Control de calidad de datos (nans, rangos, warnings, summary)
- [x] Registro de datasets con trazabilidad (hash/mtime/origen) y versionado simple
- [x] Vinculación experimento↔dataset con flujos completos desde UI y API

### IA
- [x] Formalizar “ModelRun” end-to-end (params, métricas, estado, outputs)
- [x] IA sobre series/ventanas (no solo snapshots) con pipelines reproducibles
- [x] Guardado de artefactos (CSV/figuras/modelos) y descarga segura
- [ ] Visualizaciones rápidas (PCA/plots) integradas con el flujo de runs/datasets

### Reportes / Visualización
- [x] Implementar `aether_report` (builder real) reutilizando la lógica del script HTML
- [x] Reporte de experimento (parámetros + datasets + runs + métricas + figuras + notas)
- [ ] Export académico adicional si se necesita (SVG/PDF) y estilos consistentes

### Core / DB
- [x] Añadir migraciones (Alembic u otro) para evolucionar el esquema sin hacks
- [x] Registrar sistemáticamente artefactos (ETL/IA/reportes) en la tabla `artifacts`
- [x] Guardar configuración completa de runs y seeds para reproducibilidad

### DevOps / CI
- [ ] Docker Compose verificado (API+Redis+Postgres) y variables de entorno validadas
- [ ] Healthchecks y logs adecuados para operación
- [ ] CI con caching (pip) y tiempos estables

### QA
- [x] Lint (ruff) sin errores
- [x] Tests (pytest) pasando en limpio
- [ ] Smoke manual: API + UI + export (snapshot/series/reportes)

### Docs / Experimentos
- [ ] Manual de usuario actualizado con capturas y flujos (UI/API)
- [ ] Documento técnico alineado con el estado real del código y limitaciones
- [ ] Protocolo de experimentos reproducibles (plantilla + buenas prácticas)
