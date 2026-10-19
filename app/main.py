from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routers import auth, orders, products, users
from app.core.config import settings
from app.services.errors import ServiceError

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.1.0",
    description="API REST de la tienda cyberpunk de piezas roboticas.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ServiceError)
async def service_error_handler(_request: Request, exc: ServiceError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


app.include_router(auth.router, prefix=settings.API_PREFIX)
app.include_router(products.router, prefix=settings.API_PREFIX)
app.include_router(users.router, prefix=settings.API_PREFIX)
app.include_router(orders.router, prefix=settings.API_PREFIX)


@app.get("/api/health", tags=["Sistema"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.PROJECT_NAME}
