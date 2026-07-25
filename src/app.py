from core.cabbo_logging import *  # Cabbo Logging is configured in this module at the top/root, importing it ensures it's set up before any logs are emitted and that any logs are emitted during import of other modules are captured within the cabbo logger. This is important for a consistent logging setup across the entire application.
logger = logging.getLogger(APP_NAME)
from core.constants import APP_NAME, APP_DESCRIPTION, APP_VERSION, Environment
from core.config import settings
import warnings

warnings.filterwarnings("ignore", category=UserWarning, module="razorpay.client")
from sqlalchemy.exc import SQLAlchemyError
from core.exceptions import get_mysql_exception
from db.database import check_db_connection, get_mysql_local_session
from scheduler.app_scheduler import start_scheduler, stop_scheduler

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
from utils.redaction import redact_query_params
from core.sentry import configure_sentry
from services.environment_service import get_env
log = logging.getLogger(__name__)
ENV = get_env()

configure_sentry()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    log.info("Starting application...")

    log.info("Checking database connection...")
    check_db_connection()

    log.info("Starting scheduler...")
    start_scheduler()

    # Initialize ConfigStore at startup to ensure it's ready when needed
    with get_mysql_local_session() as db:
        settings.init_config_store(db=db)

    yield

    # Shutdown
    log.info("Shutting down scheduler...")
    stop_scheduler()

    log.info("Shutting down application...")


app = FastAPI(
    title=f"{APP_NAME.capitalize()} API",
    description=APP_DESCRIPTION,
    version=APP_VERSION,
    docs_url="/42",
    redoc_url=None,
    openapi_url="/42/openapi.json",
    lifespan=lifespan,
)


 
# CORS middleware for API best practices
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.APP_URL, "http://localhost:6173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}

if ENV == Environment.DEV.value:
    @app.get("/sentry-debug", tags=["Debug"])
    async def trigger_error():
        division_by_zero = 1 / 0


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

    
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi




def get_diagnostics(request: Request):
    """Return diagnostics dict if in dev environment, else empty dict."""
    if ENV == Environment.DEV.value:
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
            f"Query: {redact_query_params(dict(request.query_params))} "
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
    kwargs = exc.extra if hasattr(exc, "extra") else {}
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.message,
            "error": str(exc),
            **diagnostics,
            "error_code": exc.error_code or "UNKNOWN_ERROR",
            **kwargs,
        },
    )


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
    cabbo_exc = get_mysql_exception(exc)
    return await cabbo_exception_handler(request, cabbo_exc)


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
    logger.error(
        f"Validation error on {request.method} {request.url.path}: "
        f"{len(exc.errors())} error(s)"
    )
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
