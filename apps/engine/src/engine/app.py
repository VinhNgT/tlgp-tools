from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from tlgp_logger import get_logger

from .api import router
from .exceptions import (
    ComponentNotFoundError,
    InvalidArchiveError,
    InvalidImageError,
    InvalidStateError,
    ParentNotFoundError,
    UndoRedoError,
)

logger = get_logger(__name__)

app = FastAPI(
    title="Annotation Engine API",
    description="REST & WebSocket API for the TLGP Annotation Engine.",
    version="0.1.0",
)


@app.exception_handler(ComponentNotFoundError)
async def component_not_found_handler(request: Request, exc: ComponentNotFoundError):
    logger.warning(
        "Component not found",
        path=request.url.path,
        error=exc.message,
        details=exc.details,
    )
    return JSONResponse(
        status_code=404,
        content={"detail": exc.message, "details": exc.details},
    )


@app.exception_handler(ParentNotFoundError)
async def parent_not_found_handler(request: Request, exc: ParentNotFoundError):
    logger.warning(
        "Parent not found",
        path=request.url.path,
        error=exc.message,
        details=exc.details,
    )
    return JSONResponse(
        status_code=400,
        content={"detail": exc.message, "details": exc.details},
    )


@app.exception_handler(InvalidArchiveError)
async def invalid_archive_handler(request: Request, exc: InvalidArchiveError):
    logger.warning(
        "Invalid archive uploaded",
        path=request.url.path,
        error=exc.message,
        details=exc.details,
    )
    return JSONResponse(
        status_code=400,
        content={"detail": exc.message, "details": exc.details},
    )


@app.exception_handler(InvalidImageError)
async def invalid_image_handler(request: Request, exc: InvalidImageError):
    logger.warning(
        "Invalid image uploaded",
        path=request.url.path,
        error=exc.message,
        details=exc.details,
    )
    return JSONResponse(
        status_code=400,
        content={"detail": exc.message, "details": exc.details},
    )


@app.exception_handler(InvalidStateError)
async def invalid_state_handler(request: Request, exc: InvalidStateError):
    logger.warning(
        "Invalid state for operation",
        path=request.url.path,
        error=exc.message,
        details=exc.details,
    )
    return JSONResponse(
        status_code=400,
        content={"detail": exc.message, "details": exc.details},
    )


@app.exception_handler(UndoRedoError)
async def undo_redo_handler(request: Request, exc: UndoRedoError):
    logger.warning(
        "Undo/redo failed",
        path=request.url.path,
        error=exc.message,
        details=exc.details,
    )
    return JSONResponse(
        status_code=400,
        content={"detail": exc.message, "details": exc.details},
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
