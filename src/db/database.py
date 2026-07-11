import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from core.config import settings
from core.constants import PROJECT_ROOT
import mysql.connector
import logging
from pathlib import Path
import ssl
import tempfile
import base64



logger = logging.getLogger(__name__)

DATABASE_URL = f"mysql+mysqlconnector://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
ASYNC_DATABASE_URL = DATABASE_URL.replace(
    "mysql+mysqlconnector://", "mysql+aiomysql://"
)
ENGINE_OPTIONS = dict(
    #echo=True if settings.ENV == Environment.DEV.value else False,
    future=True,
    pool_pre_ping=True,
    pool_recycle=1800,  # Recycle connections every 30 minutes
    pool_size=10,  # Number of connections to keep in the pool
    max_overflow=20,  # Number of connections allowed above pool_size, if both pool_size and max_overflow are reached, further connections will wait until a connection is returned to the pool
    
)

def resolve_db_ssl_ca_path() -> str | None:
    DB_SSL_CA = os.getenv("DB_SSL_CA", settings.DB_SSL_CA)
    DB_SSL_CA_PEM = os.getenv("DB_SSL_CA_PEM", settings.DB_SSL_CA_PEM)
    if DB_SSL_CA:
        ssl_ca_path = Path(DB_SSL_CA)
        if not ssl_ca_path.is_absolute():
            ssl_ca_path = Path(PROJECT_ROOT) / ssl_ca_path

        if not ssl_ca_path.exists():
            raise RuntimeError(f"DB SSL CA file not found at {ssl_ca_path}")

        return str(ssl_ca_path)

    if DB_SSL_CA_PEM:
        ssl_ca_path = Path(tempfile.gettempdir()) / "cabbo-db-ca.pem"
        ssl_ca_pem = DB_SSL_CA_PEM.strip()
        if "-----BEGIN CERTIFICATE-----" not in ssl_ca_pem:
            ssl_ca_pem = base64.b64decode(ssl_ca_pem).decode("utf-8")
        ssl_ca_pem = ssl_ca_pem.replace("\\n", "\n")
        ssl_ca_path.write_text(ssl_ca_pem + "\n", encoding="utf-8")
        return str(ssl_ca_path)

    return None



 
DB_SSL_CA_PATH = resolve_db_ssl_ca_path()

SYNC_CONNECT_ARGS = {}
ASYNC_CONNECT_ARGS = {}

if DB_SSL_CA_PATH:
    SYNC_CONNECT_ARGS = {
        "ssl_ca": DB_SSL_CA_PATH,
        "ssl_verify_cert": True,
        "ssl_verify_identity": True,
    }
    ASYNC_CONNECT_ARGS = {
        "ssl": ssl.create_default_context(cafile=DB_SSL_CA_PATH),
    }


# Pooling and connection settings (adjust as needed)
engine = create_engine(DATABASE_URL, connect_args=SYNC_CONNECT_ARGS, **ENGINE_OPTIONS)
# Create a synchronous session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine,)

async_engine = create_async_engine(
    ASYNC_DATABASE_URL, connect_args=ASYNC_CONNECT_ARGS, **ENGINE_OPTIONS
)
# Create an asynchronous session factory
AsyncSessionLocal = sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
    
)

Base = declarative_base()

def check_db_connection():
    try:
        connect_kwargs = {}
        if DB_SSL_CA_PATH:
            connect_kwargs = {
                "ssl_ca": DB_SSL_CA_PATH,
                "ssl_verify_cert": True,
                "ssl_verify_identity": True,
            }

        conn = mysql.connector.connect(
            host=settings.DB_HOST,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            port=int(settings.DB_PORT),
            database=settings.DB_NAME,
            **connect_kwargs,
            
        )
        #Test query
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        conn.close()
        logger.info("Database connection successful.")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise

def yield_mysql_session():
    db = SessionLocal()
    
    try:
        yield db
    finally:
        db.close()

def get_mysql_local_session():
    return SessionLocal()


async def a_yield_mysql_session():
    async with AsyncSessionLocal() as session:
        yield session
