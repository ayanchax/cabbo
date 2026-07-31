import logging
from typing import Any, Optional
from pydantic_settings import BaseSettings
from pydantic import ValidationError
from rich.console import Console
from core.constants import Environment
from sqlalchemy.orm import Session
from services.environment_service import load_env
log = logging.getLogger(__name__)
class Settings(BaseSettings):

    # Mandatory application settings for configuring the application behavior, such as app name, description, version, URLs, ports, and other environment-specific settings. These settings are required for all environments to ensure consistent application behavior and proper functioning of the API endpoints.
    APP_URL: str
    ADMIN_CONSOLE_URL: str = "http://localhost:6173"
    APP_LOGO_URL: str
    ENV: str
    COUNTRY_CODE: str

    #Worker and Port. Ideally these are set in production environment variables, but can be set in local environment for testing and debugging purposes. 
    # These settings are optional and can be left empty if not required. If provided, they will override the default values for API port and number of workers used by the application in their respective entrypoint scripts
    API_PORT: Optional[int]=None
    API_WORKERS: Optional[int]=None

    #Mandatory database settings for connecting to the MySQL database. These settings are required for all environments, as the application relies on a database for storing and retrieving data. The database connection settings include the host, port, user, password, database name, and SSL certificate path for secure connections.
    DB_HOST: str
    DB_PORT: str
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str
    # Optional database SSL CA path for secure connections to the MySQL database. This setting is optional and can be left empty if SSL is not required. If provided, it should point to the SSL CA certificate file used for verifying the database server's identity.
    #This works on local mode or in containerized mode when the docker image is run through docker-compose and the certs are mounted in the container. For platforms like Railway where a Docker Compose file mount is not used, we can use the DB_SSL_CA_PEM env var to provide the PEM contents directly.
    DB_SSL_CA: Optional[str] =None
    # Optional PEM contents for platforms like Railway where a Docker Compose file mount is not used. Accepts raw/escaped PEM or base64 PEM.
    DB_SSL_CA_PEM: Optional[str] = None


    # Twilio Settings for sending SMSes
    TWILLIO_ACCOUNT_SID: Optional[str] =None
    TWILLIO_AUTH_TOKEN: Optional[str] =None
    TWILLIO_PHONE_NUMBER: Optional[str] =None

    # SendGrid Settings for sending emails
    SENDGRID_API_KEY: Optional[str] =None
    SENDGRID_FROM_NO_REPLY_EMAIL: Optional[str] =None  # Email address used for sending emails to customers on events of welcome email, booking confirmation, trip updates, etc.

    # AWS SES Settings for sending emails
    AWS_SES_SMTP_HOST: Optional[str] =None
    AWS_SES_SMTP_PORT: Optional[int] =None
    AWS_SES_SMTP_USERNAME: Optional[str] =None
    AWS_SES_SMTP_PASSWORD: Optional[str] =None
    AWS_SES_FROM_NO_REPLY_EMAIL: Optional[str] =None  # Email address used for sending emails to customers on events of welcome email, booking confirmation, trip updates, etc.

    # Brevo SMTP Settings for sending emails
    BREVO_API_KEY: Optional[str] = None
    BREVO_SMTP_HOST: Optional[str] =None
    BREVO_SMTP_PORT: Optional[int] =None
    BREVO_SMTP_USERNAME: Optional[str] =None
    BREVO_SMTP_PASSWORD: Optional[str] =None
    BREVO_FROM_NO_REPLY_EMAIL: Optional[str] =None  # Email address used for sending emails to customers on events of welcome email, booking confirmation, trip updates, etc.

    # Mandatory JWT secret key for signing and verifying JSON Web Tokens (JWTs) used for authentication and authorization in the application. This setting is required for all environments to ensure secure token-based authentication and to protect sensitive user data. 
    JWT_SECRET: str

    #SMS and OTP settings for sending OTPs to users for authentication and verification purposes. These settings are mandatory for all environments, as OTP functionality is a core feature of the application.
    SMS_SERVICE_PROVIDER: str
    SMS_PROVIDER_AUTHKEY:Optional[str]=None # Auth key is used when SMS_SERVICE_PROVIDER is MSG91
    LOGIN_OTP_DLT_TEMPLATE_ID:Optional[str] = None
    REGISTRATION_OTP_DLT_TEMPLATE_ID:Optional[str]= None
    RESEND_OTP_DLT_TEMPLATE_ID:Optional[str] = None
    OTP_LENGTH: int = 6
    OTP_EXPIRY_MINUTES: int = 5
    OTP_VERIFICATION_MAX_ATTEMPTS: int = 3
    OTP_RESEND_COOLDOWN_SECONDS: int = 60
    OTP_PHONE_WINDOW_SECONDS: int = 3600 # 1 hour window for phone number rate limiting | Count OTP sends from the phone number fromthe last 1 hour only, ignore/drop older events
    OTP_PHONE_MAX_SENDS_PER_WINDOW: int = 3 # Maximum OTP sends allowed per phone number within the window | A phone number can recieve max 3 otps in a rolling 1 hour window, after which it will be rate limited for the next hour. 1h = <=3 otps etc. | This is to prevent abuse and spam
    OTP_IP_WINDOW_SECONDS: int = 3600 # 1 hour window for IP rate limiting | Count OTP sends from the IP from the last 1 hour only, ignore/drop older events
    OTP_IP_MAX_SENDS_PER_WINDOW: int = 6 # Maximum OTP sends allowed per IP within the window | A single IP can send max 6 otps in a rolling 1 hour window, after which it will be rate limited for the next hour. 1h = <=6 otps etc. | This is to prevent abuse and spam
    OTP_PHONE_DAILY_CAP: int = 4 # Maximum OTP sends allowed per phone number per day
    OTP_FORCE_RATE_LIMIT_PHONE_NUMBER: Optional[str] = None # Non-prod testing hook. If this phone number requests OTP, return a 429 without sending SMS.
    
    EMAIL_SERVICE_PROVIDER: str
    
    # Payment provider settings for processing payments through Razorpay. These settings are mandatory for all environments, as payment processing is a core feature of the application.
    PAYMENT_PROVIDER: str
    RAZOR_PAY_KEY_ID: str
    RAZOR_PAY_KEY_SECRET: str
    
    # Cabbo specific settings for internal application functionality, such as trip booking, super admin access, default user password, timezone settings, etc. These settings are mandatory for all environments, as they are core to the application's functionality and user experience.
    CABBO_TRIP_BOOKING_SECRET_KEY: str
    CABBO_SUPER_ADMIN_SECRET: str
    CABBO_USER_DEFAULT_PASSWORD: str
    CABBO_DEFAULT_TIMEZONE: str
    CABBO_DEFAULT_UTC_OFFSET: int  = 330# in minutes, e.g., 330 for IST (UTC+5:30)
    
    # Configuration store for dynamic settings that can be updated at runtime without requiring a restart of the application. This is useful for feature flags, toggles, and other settings that may change based on business needs or operational requirements. The configuration store is initialized once and can be accessed throughout the application to retrieve the latest configuration values.
    CONFIG_STORE: Any = None

    #AWS S3 Settings are mandatory for all environments, as we are using S3 for storing images and other media files. Hence, these settings are required to be set in the environment variables for all environments.
    AWS_ACCESS_KEY: str
    AWS_SECRET_KEY: str
    AWS_REGION: str
    S3_BUCKET: str
    S3_BASE_URL: str   


    # Google Maps API Key for geocoding, reverse geocoding, and other map-related services
    # This is mandatory key and used for interacting with Google Maps services, such as converting addresses to geographic coordinates and vice versa.
    LOCATION_SERVICE_PROVIDER: str
    GOOGLE_MAPS_API_KEY: str

    #Customer support contact information, which is mandatory for all environments, as it is used for providing customer support to users in case of any issues or queries related to the application.
    CUSTOMER_SUPPORT_EMAIL: str
    CUSTOMER_SUPPORT_PHONE_NUMBER: str
    CUSTOMER_SUPPORT_WHATSAPP_NUMBER: str


    # Logging to Sentry for error tracking and monitoring. These settings are optional for local environments and can be configured in non-local environments for better error tracking and monitoring of the application.
    SENTRY_DSN: Optional[str] = ""  # Sentry DSN for error tracking
    SENTRY_ENVIRONMENT: Optional[str] = None
    SENTRY_RELEASE: Optional[str] = None
    SENTRY_ERROR_SAMPLE_RATE: float = 1.0
    SENTRY_TRACES_SAMPLE_RATE: float = 0.05
    SENTRY_PROFILES_SAMPLE_RATE: float = 0.0
    SENTRY_ENABLE_LOGS: bool = True

    #Optional logging directory for storing application logs. This setting is optional and can be left empty if logs are not required to be stored in a specific directory within container. If provided, it should point to the directory where application logs will be saved.
    # Generally this is turned off in dev and prod environments, but can be turned on in local environment for debugging and troubleshooting purposes. In production, logs are generally sent to a centralized logging system or service Sentry for better monitoring and analysis.
    LOG_DIR: Optional[str]=None
    
    class Config:
        env_file = load_env() #Get environment file path from the environment service, which will load the appropriate .env file based on the current environment (local, dev, prod). This allows for dynamic loading of environment variables based on the deployment environment.
                              # Here we just load the env file path and let pydantic do the rest of the work of loading the env vars into the settings object. This is a cleaner approach than loading the env vars directly in this file, as it allows for better separation of concerns and easier testing.
        env_file_encoding = "utf-8"
        extra = "ignore"

    def init_config_store(self, db: Session):
        """Initialize configuration store with a dedicated session."""

        log.info("Starting ConfigStore initialization...")
        from core.store import ConfigStore

        try:
            store = ConfigStore.get_instance()
            store.initialize_config_store(db)
            self.CONFIG_STORE = store
            log.info("ConfigStore initialization completed successfully.")
            return store
        except Exception as e:
            log.error(f"Error during ConfigStore initialization: {e}")
            raise

    def get_config_store(self, db: Session):
        """Get the configuration store, initializing it if necessary."""
        if not self.CONFIG_STORE:
            return self.init_config_store(db)
        else:
            log.info("ConfigStore already initialized, returning existing instance for retrieving configurations from in-memory store.")
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
