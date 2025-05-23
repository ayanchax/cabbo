from pydantic_settings import BaseSettings
from pydantic import ValidationError
import os
from rich.console import Console

ENV = os.getenv("ENV", "dev")
ENV_FILE = ".env.dev" if ENV == "dev" else ".env.prod"

class Settings(BaseSettings):
    API_URL:str
    ENV: str = ENV
    REGION: str
    DB_HOST: str
    DB_PORT: str
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str
    SECRET_KEY: str
    TWILLIO_ACCOUNT_SID:str
    TWILLIO_AUTH_TOKEN:str
    TWILLIO_PHONE_NUMBER:str
    SENDGRID_API_KEY:str
    SENDGRID_FROM_EMAIL:str
    JWT_SECRET:str

    
    
    class Config:
        env_file = ENV_FILE
        env_file_encoding = "utf-8"

try:
    settings = Settings()
except ValidationError as e:
    console = Console()
    console.print("[bold red]ERROR:[/bold red] Missing required environment variables!\n", style="bold red")
    for err in e.errors():
        loc = '.'.join(str(x) for x in err['loc'])
        console.print(f"[red]- {loc}: {err['msg']}")
    raise SystemExit("Environment validation failed. Please set all required environment variables")
