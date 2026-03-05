from typing import Any
from pydantic_settings import BaseSettings
from pydantic import ValidationError
import os
from rich.console import Console
from core.constants import Environment
from sqlalchemy.orm import Session


ENV = os.getenv("ENV", Environment.DEV.value)
ENV_FILE = (
    f".env.{Environment.DEV.value}"
    if ENV == Environment.DEV.value
    else f".env.{Environment.PROD.value}"
)


class Settings(BaseSettings):

    APP_URL: str
    API_URL: str
    APP_LOGO_URL: str
    ENV: str = ENV
    COUNTRY_CODE: str
    DB_HOST: str
    DB_PORT: str
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str
    SECRET_KEY: str
    #Twilio Settings for sending SMSes
    TWILLIO_ACCOUNT_SID: str
    TWILLIO_AUTH_TOKEN: str
    TWILLIO_PHONE_NUMBER: str


    #SendGrid Settings for sending emails
    SENDGRID_API_KEY: str
    SENDGRID_FROM_NO_REPLY_EMAIL: str  # Email address used for sending emails to customers on events of welcome email, booking confirmation, trip updates, etc.
    
    #AWS SES Settings for sending emails
    AWS_SES_SMTP_HOST: str
    AWS_SES_SMTP_PORT: int
    AWS_SES_SMTP_USERNAME: str
    AWS_SES_SMTP_PASSWORD: str
    AWS_SES_FROM_NO_REPLY_EMAIL: str # Email address used for sending emails to customers on events of welcome email, booking confirmation, trip updates, etc.
    
    #Brevo SMTP Settings for sending emails
    BREVO_SMTP_HOST: str
    BREVO_SMTP_PORT: int
    BREVO_SMTP_USERNAME: str
    BREVO_SMTP_PASSWORD: str
    BREVO_FROM_NO_REPLY_EMAIL: str # Email address used for sending emails to customers on events of welcome email, booking confirmation, trip updates, etc.

    JWT_SECRET: str
    SHARE_PATH: str
    MAPBOX_TOKEN: str
    LOCATION_SERVICE_PROVIDER: str
    EMAIL_SERVICE_PROVIDER: str
    PAYMENT_PROVIDER: str
    RAZOR_PAY_KEY_ID: str
    RAZOR_PAY_KEY_SECRET: str
    CABBO_TRIP_BOOKING_SECRET_KEY: str
    CABBO_SUPER_ADMIN_SECRET: str
    CABBO_USER_DEFAULT_PASSWORD: str
    CABBO_DEFAULT_TIMEZONE: str
    CONFIG_STORE: Any = None

    class Config:
        env_file = ENV_FILE
        env_file_encoding = "utf-8"
        extra = "ignore"

    def init_config_store(self, db: Session):
        """Initialize configuration store with a dedicated session."""

        print("Starting ConfigStore initialization...")
        from core.store import ConfigStore

        try:
            store = ConfigStore.get_instance()
            store.initialize_config_store(db)
            self.CONFIG_STORE = store
            print("ConfigStore initialization completed successfully.")
            return store
        except Exception as e:
            print(f"Error during ConfigStore initialization: {e}")
            raise
    
    def get_config_store(self, db: Session):
        """Get the configuration store, initializing it if necessary."""
        if not self.CONFIG_STORE:
            return self.init_config_store(db)
        return self.CONFIG_STORE

try:
    settings = Settings()
except ValidationError as e:
    console = Console()
    console.print(
        "[bold red]ERROR:[/bold red] Missing required environment variables!\n",
        style="bold red",
    )
    for err in e.errors():
        loc = ".".join(str(x) for x in err["loc"])
        console.print(f"[red]- {loc}: {err['msg']}")
    raise SystemExit(
        "Environment validation failed. Please set all required environment variables"
    )
