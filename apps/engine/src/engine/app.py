from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from tlgp_logger import get_logger

from .api import router
from .exceptions import (
    BoundaryViolationError,
    ComponentNotFoundError,
    InvalidArchiveError,
    InvalidImageError,
    InvalidStateError,
    ParentNotFoundError,
    UndoRedoError,
)

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Application startup: initialize resources if needed
    logger.info("Starting up Annotation Engine API...")
    yield
    # Application shutdown: clean up resources if needed
    logger.info("Shutting down Annotation Engine API...")


app = FastAPI(
    title="Annotation Engine API",
    description="REST & WebSocket API for the TLGP Annotation Engine.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production to specific frontend URLs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


@app.exception_handler(BoundaryViolationError)
async def boundary_violation_handler(request: Request, exc: BoundaryViolationError):
    logger.warning(
        "Boundary violation",
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


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(
        "Request validation failed",
        path=request.url.path,
        errors=exc.errors(),
        body=getattr(exc, "body", None),
    )
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": getattr(exc, "body", None)},
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    logger.warning(
        "HTTP exception occurred",
        path=request.url.path,
        status_code=exc.status_code,
        detail=exc.detail,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
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
