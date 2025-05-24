from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from core.config import settings
import os
import importlib
import mysql.connector
import contextlib
import logging

logger = logging.getLogger(__name__)

DATABASE_URL = f"mysql+mysqlconnector://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
ASYNC_DATABASE_URL = DATABASE_URL.replace(
    "mysql+mysqlconnector://", "mysql+aiomysql://"
)
ENGINE_OPTIONS = dict(
    echo=True if settings.ENV == "dev" else False,
    future=True,
    pool_pre_ping=True,
    pool_recycle=1800,  # Recycle connections every 30 minutes
    pool_size=10,  # Number of connections to keep in the pool
    max_overflow=20,  # Number of connections allowed above pool_size
)


# Pooling and connection settings (adjust as needed)
engine = create_engine(DATABASE_URL, **ENGINE_OPTIONS)
# Create a synchronous session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

async_engine = create_async_engine(ASYNC_DATABASE_URL, **ENGINE_OPTIONS)
# Create an asynchronous session factory
AsyncSessionLocal = sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

Base = declarative_base()


def _import_all_models():
    models_dir = os.path.join(os.path.dirname(__file__), "..", "models")
    for root, _, files in os.walk(models_dir):
        for filename in files:
            if filename.endswith("_orm.py") and filename != "__init__.py":
                # Build the module path relative to the models directory
                rel_path = os.path.relpath(os.path.join(root, filename), models_dir)
                module_name = "models." + rel_path.replace(os.sep, ".")[:-3]
                importlib.import_module(module_name)


def _ensure_database_exists():
    db_name = settings.DB_NAME
    try:
        conn = mysql.connector.connect(
            host=settings.DB_HOST,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            port=int(settings.DB_PORT),
        )
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}`")
        cursor.close()
        conn.close()
        logger.info(f"Ensured database '{db_name}' exists.")
    except Exception as e:
        logger.error(f"Error ensuring database exists: {e}")
        raise


def init_db():
    logger.info("Initializing database and creating tables if not present...")
    _ensure_database_exists()
    _import_all_models()
    Base.metadata.create_all(bind=engine)

    logger.info("Database initialization complete.")


def get_mysql_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_mysql_async_session():
    async def _get_session():
        async with AsyncSessionLocal() as session:
            yield session

    return contextlib.asynccontextmanager(_get_session)()
