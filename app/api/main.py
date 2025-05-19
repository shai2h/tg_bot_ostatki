from fastapi import FastAPI
from app.api.ostatki import router

app = FastAPI(
    title="Остатки на складах API",
    description="Приём остатков с 1С. Версия API v1.0.0",
    version="1.0.0"
)

app.include_router(router)
