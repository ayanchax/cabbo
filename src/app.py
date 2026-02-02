from core.cabbo_logging import *
from core.constants import APP_NAME, APP_DESCRIPTION, APP_VERSION, PROJECT_ROOT
from core.config import settings
import warnings

from db.database import check_db_connection
from scheduler.app_scheduler import start_scheduler, stop_scheduler
from services.file_service import copy_file, create_directories

warnings.filterwarnings("ignore", category=UserWarning, module="razorpay.client")
logger = logging.getLogger(APP_NAME)
from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from core.exceptions import CabboException
from fastapi.exceptions import RequestValidationError
from fastapi import HTTPException as FastAPIHTTPException
import os
from datetime import datetime, timezone
from fastapi.staticfiles import StaticFiles
from api.v1.routes import router as v1_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Starting application...")

    print("Checking database connection...")
    check_db_connection()

    print("Starting scheduler...")
    start_scheduler()
    yield
    
    # Shutdown
    print("Shutting down scheduler...")
    stop_scheduler()

    print("Shutting down application...")


app = FastAPI(
    title=f"{APP_NAME.capitalize()} API",
    description=APP_DESCRIPTION,
    version=APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS middleware for API best practices
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": f"Welcome to {APP_NAME.capitalize()} API!"}


# Include routers
app.include_router(v1_router, prefix="/api/v1")

# Ensure share/images and share/documents directory exists relative to this file (project root)
SHARE_IMAGES_DIR = os.path.join(PROJECT_ROOT, settings.SHARE_PATH, "images")
SHARE_DOCUMENTS_DIR = os.path.join(PROJECT_ROOT, settings.SHARE_PATH, "documents")
# Create directories if they don't exist
create_directories([SHARE_IMAGES_DIR, SHARE_DOCUMENTS_DIR])
# Copy default logo to share/images if not already present, this logo can be used in emails or other places
copy_file(
    os.path.join(PROJECT_ROOT,"resources", "logo-without-tagline.svg"),
    os.path.join(SHARE_IMAGES_DIR, "logo.svg"),
    overwrite=False,
)

# ...existing code...

# Mount the static images directory
app.mount("/images", StaticFiles(directory=SHARE_IMAGES_DIR), name="images")
# Mount the static documents directory
app.mount("/documents", StaticFiles(directory=SHARE_DOCUMENTS_DIR), name="documents")


# Custom OpenAPI schema (optional, for branding or extensions)
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

ENV = settings.ENV


def get_diagnostics(request: Request):
    """Return diagnostics dict if in dev environment, else empty dict."""
    if ENV == "dev":
        return {
            "path": str(request.url),
            "method": request.method,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
    return {}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    diagnostics = get_diagnostics(request)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An unexpected error occurred. Please try again later.",
            "error": str(exc),
            **diagnostics,
        },
    )


@app.exception_handler(CabboException)
async def cabbo_exception_handler(request: Request, exc: CabboException):
    logger.error(f"CabboException: {exc}", exc_info=True)
    diagnostics = get_diagnostics(request)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "error": str(exc), **diagnostics},
    )


@app.exception_handler(FastAPIHTTPException)
async def http_exception_handler(request: Request, exc: FastAPIHTTPException):
    logger.error(f"HTTPException: {exc.detail}", exc_info=True)
    diagnostics = get_diagnostics(request)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "error": str(exc), **diagnostics},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"Validation error: {exc}", exc_info=True)
    diagnostics = get_diagnostics(request)
    # If the error is due to missing Authorization header, return 401
    for err in exc.errors():
        if (
            err.get("loc", [])[0] == "header"
            and "authorization" in str(err.get("loc", [])).lower()
        ):
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Authorization header missing or invalid.",
                    "error": str(exc),
                    **diagnostics,
                },
            )
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "error": str(exc), **diagnostics},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
