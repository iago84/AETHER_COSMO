# Guía de Contribución

Gracias por tu interés en contribuir a AETHERLAB.

## Flujo de trabajo

- Crea una rama desde `main` o `master`.
- Abre un issue si no existe uno asociado a tu cambio.
- Envía un Pull Request usando la plantilla y completa el checklist.

## Estándares

- Python 3.11+.
- Mantén separados API, simulador, métricas y UI según la arquitectura del repositorio.
- No incluyas credenciales ni secretos en el código ni en los logs.
- Documenta endpoints y nuevos parámetros en los documentos de `docs/` cuando aplique.

## Pruebas rápidas (local)

```bash
pip install -r requirements.txt
python scripts\run_sim_example.py
```

## Calidad

- Asegúrate de que el código ejecuta el “smoke test” mínimo (ver CI).
- Si añades dependencias, explícalas en el PR y actualiza `requirements.txt`.

## Seguridad

- Maneja entradas de usuario de forma segura; valida parámetros en API.
- Evita exponer rutas sensibles y verifica permisos al gestionar artefactos.

## Commits y PRs

- Commits claros y atómicos.
- En PR, describe: alcance, módulos afectados, notas de despliegue (env vars, migraciones).

## Licencia

Al contribuir aceptas que tu aportación se licencie bajo BSD-3-Clause.
