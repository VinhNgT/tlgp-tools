from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from tlgp_logger import get_logger

from .api import router

logger = get_logger(__name__)

app = FastAPI(
    title="Annotation Engine API",
    description="REST & WebSocket API for the TLGP Annotation Engine.",
    version="0.1.0",
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "Unhandled engine exception occurred", path=request.url.path, error=str(exc)
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error occurred."},
    )


app.include_router(router)
