from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from core.config import settings
import mysql.connector
import logging



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


# Pooling and connection settings (adjust as needed)
engine = create_engine(DATABASE_URL, **ENGINE_OPTIONS)
# Create a synchronous session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine,)

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

def check_db_connection():
    try:
        conn = mysql.connector.connect(
            host=settings.DB_HOST,
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            port=int(settings.DB_PORT),
            database=settings.DB_NAME,
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

