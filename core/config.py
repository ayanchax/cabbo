import os
from dotenv import load_dotenv
from core.constants import APP_NAME

ENV = os.getenv("ENV", "dev")
if ENV == "dev":
    load_dotenv(".env.dev") # Load development environment variables only when running in development/local mode
    #When running from Docker environment, in production or development mode, the .env.prod or .env.dev file will be loaded by the Docker container itself


class Settings:
    DB_HOST = os.getenv("DB_HOST")
    DB_PORT = os.getenv("DB_PORT")
    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_NAME = os.getenv("DB_NAME")
    SECRET_KEY = os.getenv("SECRET_KEY")
    ENV = ENV

settings = Settings()
