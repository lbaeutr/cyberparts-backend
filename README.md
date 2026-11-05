# CyberParts API

Backend de CyberParts: FastAPI + SQLAlchemy + Alembic + PostgreSQL.

Este repositorio es un mirror del monorepo `pps-ciberseguridad-trabajos-pps-26-27-lbaeutr`
(carpeta `1_desarrollo_web/backend`). No lo edites directamente: los cambios se hacen en el
monorepo y se publican con `scripts/push-deploy.sh`.

## Despliegue en Render

El servicio se define en `render.yaml` (Blueprint). Variables manuales:

- `DATABASE_URL`: cadena de conexión directa de Neon (acepta `postgres://` o
  `postgresql://`; la aplicación la normaliza a `postgresql+psycopg://`).
- `ADMIN_EMAIL` y `ADMIN_PASSWORD`: administrador inicial. En producción la aplicación
  rechaza la contraseña por defecto `Admin123!`.
- `GITHUB_CLIENT_ID` y `GITHUB_CLIENT_SECRET`: OAuth App de producción.

El resto de variables (`ENVIRONMENT`, `SECRET_KEY`, cookies, CORS, `FRONTEND_URL`,
`SEED_DEMO_USERS`, `GITHUB_REDIRECT_URI`) se define en `render.yaml`.

En producción no se crean los usuarios demo de Matrix (`SEED_DEMO_USERS=false`). El seed sí
crea roles, el administrador y el catálogo de productos.

El arranque aplica migraciones, ejecuta el seed idempotente y levanta Uvicorn con
`--proxy-headers --forwarded-allow-ips="*"` para que el rate limiting use la IP real del
cliente detrás del proxy de Render.

## Local

Desde el monorepo:

```bash
./scripts/setup.sh
./scripts/backend.sh
```

Documentación completa en el monorepo (`README.md`, `docs/`).
