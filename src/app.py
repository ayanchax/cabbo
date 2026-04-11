from core.cabbo_logging import * #Cabbo Logging is configured in this module at the top/root, importing it ensures it's set up before any logs are emitted and that any logs are emitted during import of other modules are captured within the cabbo logger. This is important for a consistent logging setup across the entire application.
from core.constants import APP_NAME, APP_DESCRIPTION, APP_VERSION, Environment
from core.config import settings
import warnings

from db.database import check_db_connection, get_mysql_local_session
from scheduler.app_scheduler import start_scheduler, stop_scheduler

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
from datetime import datetime, timezone
from api.v1.routes import router as v1_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Starting application...")

    print("Checking database connection...")
    check_db_connection()

    print("Starting scheduler...")
    start_scheduler()

    # Initialize ConfigStore at startup to ensure it's ready when needed
    with get_mysql_local_session() as db:
        settings.init_config_store(db=db)
    
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


@app.get("/", tags=["Health"])
def health():
    return {"message": f"Welcome to {APP_NAME.capitalize()} API!"}


# Include routers
app.include_router(v1_router, prefix="/api/v1")


# Custom OpenAPI schema (optional, for branding or extensions)
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    # Generate the default OpenAPI schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    # Count the number of endpoints
    endpoint_count = sum(1 for route in app.routes if hasattr(route, "endpoint"))

    # Add the endpoint count to the description
    openapi_schema["info"]["description"] += f"\n\nThis API has **{endpoint_count} endpoints**."

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


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = datetime.now(timezone.utc)

    try:
        response = await call_next(request)
    except Exception as e:
        logger.exception(
            f"Unhandled error during request: {request.method} {request.url.path}"
        )
        raise

    duration = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
    response_size = response.headers.get("content-length", "unknown")
    if ENV == Environment.DEV.value:
        logger.info(
        f"{request.method} {request.url.path} "
        f"Query: {dict(request.query_params)} "
        f"Status: {response.status_code} "
        f"Time: {round(duration, 2)}ms "
        f"Size: {response_size} bytes "
        f"Client: {request.client.host if request.client else 'unknown'}"
    )
    else:
        logger.info(
            f"{request.method} {request.url.path} "
            f"Status: {response.status_code} "
            f"Time: {round(duration, 2)}ms "
            f"Client: {request.client.host if request.client else 'unknown'}"
        )

    return response

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
        content={"detail": exc.message, "error": str(exc), **diagnostics, "error_code": exc.error_code or "UNKNOWN_ERROR"},
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
