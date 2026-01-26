import os
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))

from dotenv import load_dotenv

from core.constants import PROJECT_ROOT, Environment

# Load .env file
ENV = os.getenv("ENV", Environment.DEV.value)
ENV_FILE = (
    f".env.{Environment.DEV.value}"
    if ENV == Environment.DEV.value
    else f".env.{Environment.PROD.value}"
)
load_dotenv(dotenv_path=ENV_FILE)

# Build DB URL from env vars
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT") or 3306
DB_NAME = os.getenv("DB_NAME")


SQLALCHEMY_DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

from alembic import context
from sqlalchemy import engine_from_config, pool

#Dynamic model imports
import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent / "src"))

from dotenv import load_dotenv
from core.constants import PROJECT_ROOT, Environment

# Load .env file
ENV = os.getenv("ENV", Environment.DEV.value)
ENV_FILE = (
    f".env.{Environment.DEV.value}"
    if ENV == Environment.DEV.value
    else f".env.{Environment.PROD.value}"
)
load_dotenv(dotenv_path=os.path.join(PROJECT_ROOT, ENV_FILE))

# --- DYNAMIC MODEL IMPORTS ---
import importlib

def _import_all_models():
    models_dir = os.path.join(os.path.dirname(__file__), "..", "src", "models")
    for root, _, files in os.walk(models_dir):
        for filename in files:
            if filename.endswith("_orm.py") and filename != "__init__.py":
                rel_path = os.path.relpath(os.path.join(root, filename), models_dir)
                module_name = "models." + rel_path.replace(os.sep, ".")[:-3]
                importlib.import_module(module_name)

_import_all_models()

from db.database import Base  # or from models.base import Base



# Set the sqlalchemy.url dynamically
config = context.config
config.set_main_option("sqlalchemy.url", SQLALCHEMY_DATABASE_URL)

# ...rest of your env.py...
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
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
