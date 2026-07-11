
import logging

from alembic import context
from sqlalchemy import engine_from_config, pool

# Dynamic model imports
import os
import sys
from pathlib import Path
import tempfile
import base64

sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))

from dotenv import load_dotenv
from core.constants import PROJECT_ROOT, Environment
log= logging.getLogger(__name__)
# Load .env file
ENV = os.getenv("ENV", Environment.LOCAL.value)
# Load ONLY for local
if ENV == Environment.LOCAL.value:
    env_path = os.path.join(PROJECT_ROOT, f".env.{Environment.LOCAL.value}")
    load_dotenv(dotenv_path=env_path)
    log.info(f"Loaded local env: {env_path}")
else:
    log.info("Running in non-local mode, relying on system env vars")

# Build DB URL from env vars
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT") or 3306
DB_NAME = os.getenv("DB_NAME")
DB_SSL_CA = os.getenv("DB_SSL_CA", "")
DB_SSL_CA_PEM = os.getenv("DB_SSL_CA_PEM", "")
SQLALCHEMY_DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)


def resolve_db_ssl_ca_path() -> str | None:
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


import models  # Ensure all models are imported so that they are registered with SQLAlchemy
from db.database import Base

 
config = context.config
config.set_main_option("sqlalchemy.url", SQLALCHEMY_DATABASE_URL)
 
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata


# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connect_args = {}
    if DB_SSL_CA_PATH:
        connect_args = {
            "ssl": {
                "ca": DB_SSL_CA_PATH,
                "check_hostname": True,
            }
        }

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
