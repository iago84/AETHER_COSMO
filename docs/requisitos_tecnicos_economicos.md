# Requisitos Técnicos y Económicos

## Requisitos Técnicos

### Software
- Python 3.11+
- Dependencias: `fastapi`, `uvicorn`, `SQLAlchemy`, `numpy`, `matplotlib`, `PyQt6`
- Opcionales (asíncrono): `redis`, `rq`
- DB: SQLite (por defecto) o PostgreSQL (producción)

### Hardware (orientativo)
- Desarrollo/uso local:
  - CPU: 4 núcleos
  - RAM: 8–16 GB
  - Disco: 1–5 GB libres para outputs (PNG/NPY/NPZ)
- Servidor API ligero:
  - CPU: 2–4 vCPU
  - RAM: 4–8 GB
  - Almacenamiento: 10–50 GB (según retención de series)
- Opcional AI (entrenamiento):
  - GPU CUDA (8–16 GB VRAM) si se agregan modelos DL

### Despliegue
- API con Uvicorn/Gunicorn detrás de Nginx o equivalente.
- Redis gestionado (Docker o servicio administrado).
- DB PostgreSQL gestionada si se requiere multiusuario/escala.
- Logs y rotación para outputs en `aetherlab/data/outputs/`.

### Seguridad
- Variables de entorno para credenciales (nunca en el repo).
- TLS/HTTPS al exponer la API públicamente.
- Políticas de retención y limpieza de artefactos.

## Requisitos Económicos (estimaciones)

### Local / On-Prem
- Coste inicial: nulo si ya se dispone de equipo.
- Mantenimiento: tiempo de administración, energía y almacenamiento.

### Cloud (aproximado, mensual)
- VM pequeña (2 vCPU, 4–8 GB RAM): 20–60 €
- Redis gestionado básico: 10–30 €
- PostgreSQL gestionado básico: 20–50 €
- Almacenamiento (50–200 GB): 2–10 €
- Total orientativo: 50–150 € según proveedor y región.

### Escalado
- Más vCPU/RAM para simulaciones concurrentes.
- Redis con mayor throughput si aumentan jobs.
- Almacenamiento adicional y CDN/objeto (p.ej., S3) para artefactos.

## Riesgos y Mitigaciones
- Crecimiento de artefactos: implementar limpieza y expiración.
- Jobs fallidos o colgados: usar RQ con reintentos y monitoreo.
- Cuellos de botella en CPU: paralelizar runs y optimizar numerics; considerar GPU si se incorpora AI pesada.

## Recomendaciones
- Empezar con SQLite + BackgroundTasks para MVP.
- Migrar a Redis/RQ y PostgreSQL al escalar usuarios o barridos.
- Automatizar backups de DB y outputs críticos.

