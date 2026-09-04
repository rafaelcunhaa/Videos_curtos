from fastapi import FastAPI

from api.routes import router

app = FastAPI(
    title="BoomVibes API",
    version="1.0.0",
    description="Sistema de automação para criação e publicação de Shorts.",
)

app.include_router(router)
