from enum import Enum
import os


APP_NAME = "cabbo"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = "Backend API for cab booking platform."
APP_ADMIN_EMAIL = "admin@cabbo.co.in"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class Environment(str, Enum):
    DEV = "dev"
    PROD = "prod"


