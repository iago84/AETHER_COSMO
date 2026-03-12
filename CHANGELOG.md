## Changelog

### [Unreleased]
- Plantillas de issues y PR con checklists.
- Checklist global del proyecto en `CHECKLIST.md`.
- Plantilla de checklist de tareas actualizada por módulos (UI/API/sim/datos/IA/reportes/devops/docs).
- CI de smoke test (Python 3.11) y labeler automático.
- Release Drafter y CODEOWNERS.
- Reportes HTML centralizados (`aether_report`) para run y experimento.
- Endpoints de comparación run↔run y run↔dataset (métricas + figura PNG).
- ETL con normalización + QC, con registro de artefactos en DB.
- ModelRun con métricas agregadas y trazabilidad básica.
- UI PyQt6 con selector proyecto/experimento, pestañas (Datos/IA/Comparación/Reportes/Config) y export unificado.
- Migraciones simples en arranque (`schema_migrations` + `ALTER TABLE` idempotentes).
- Script warmup para demo+reporte.
- Documentación técnica, manual y experimentos.
- Licencia BSD-3-Clause.
