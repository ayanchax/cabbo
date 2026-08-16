import logging
import os
from dotenv import load_dotenv
from core.constants import PROJECT_ROOT, Environment
log = logging.getLogger(__name__)

def load_env(load_env_file: bool = False):
    ENV = os.getenv("ENV", Environment.LOCAL.value).lower()
    env_path = os.path.join(PROJECT_ROOT, f".env.{ENV}")
    if os.path.exists(env_path):
        if load_env_file:
            load_dotenv(dotenv_path=env_path, override=True)
            log.info(f"Loaded env file: {env_path}. Returning path to env file.")
        else:
            log.info(f"Env file exists: {env_path}, returning path without loading.")
        return env_path
    else:
        log.info(f"No env file found for {ENV}; relying on system env vars")
    return None

def get_env():
    return os.getenv("ENV", Environment.LOCAL.value).lower()
