from core.cabbo_logging import *
from core.constants import APP_NAME, APP_DESCRIPTION, APP_VERSION
from core.config import settings
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="razorpay.client")
logger = logging.getLogger(APP_NAME)
from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from routes import auth, customer, location, trip, seed  # Import your routers here
from db.database import init_db
from contextlib import asynccontextmanager
from core.exceptions import CabboException
from fastapi.exceptions import RequestValidationError
from fastapi import HTTPException as FastAPIHTTPException
import os
from datetime import datetime, timezone
from fastapi.staticfiles import StaticFiles


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # Call synchronously, do not await
    yield


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
app.include_router(auth.router)
app.include_router(customer.router)
app.include_router(seed.router)
app.include_router(location.router)
app.include_router(trip.router)

# Ensure share/images directory exists relative to this file (project root)
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SHARE_IMAGES_DIR = os.path.join(PROJECT_ROOT, settings.SHARE_PATH, "images")
SHARE_DOCUMENTS_DIR = os.path.join(PROJECT_ROOT, settings.SHARE_PATH, "documents")
os.makedirs(SHARE_IMAGES_DIR, exist_ok=True)
os.makedirs(SHARE_DOCUMENTS_DIR, exist_ok=True)
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

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
