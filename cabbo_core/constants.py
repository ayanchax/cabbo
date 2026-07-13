from enum import Enum
import os


APP_NAME = "cabbo"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = "Backend API for cab booking platform."
APP_ADMIN_EMAIL = "admin@cabbo.co.in"
SUPER_ADMIN={
    "name":"Super Admin",
    "email":APP_ADMIN_EMAIL,
    "username":"superadmin",
    "phone_number":"9999999999",
}
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class Environment(str, Enum):
    LOCAL="local"
    DEV = "dev"
    PROD = "prod"


CABBO_DEFAULT_TIMEZONE="Asia/Kolkata"
CABBO_DEFAULT_UTC_OFFSET=330
CABBO_DEFAULT_LOCATION_SERVICE_PROVIDER="google"