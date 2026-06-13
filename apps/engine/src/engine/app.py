from fastapi import FastAPI

from .api import router

app = FastAPI(
    title="Annotation Engine API",
    description="REST & WebSocket API for the TLGP Annotation Engine.",
    version="0.1.0",
)

app.include_router(router)
