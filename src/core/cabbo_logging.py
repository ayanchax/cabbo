import logging
import os
from logging.handlers import TimedRotatingFileHandler
from core.constants import APP_NAME, PROJECT_ROOT

LOG_DIR = os.path.join(PROJECT_ROOT, 'logs')
print(f"LOG_DIR: {LOG_DIR}")
os.makedirs(LOG_DIR, exist_ok=True)

# Prevent duplicate handlers (important for reload environments)
logger = logging.getLogger(APP_NAME)
if not logger.handlers:
    cabbo_debug_handler = TimedRotatingFileHandler(
        os.path.join(LOG_DIR, 'debug.log'), when='midnight', interval=1, backupCount=15, encoding='utf-8', delay=True
    )
    cabbo_debug_handler.setLevel(logging.DEBUG)
    cabbo_debug_handler.setFormatter(logging.Formatter(f'%(asctime)s [%(levelname)s] {APP_NAME} :: %(name)s: %(message)s'))

    cabbo_error_handler = TimedRotatingFileHandler(
        os.path.join(LOG_DIR, 'error.log'), when='midnight', interval=1, backupCount=15, encoding='utf-8', delay=True
    )
    cabbo_error_handler.setLevel(logging.ERROR)
    cabbo_error_handler.setFormatter(logging.Formatter(f'%(asctime)s [%(levelname)s] {APP_NAME} :: %(name)s: %(message)s'))

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(f'%(asctime)s [%(levelname)s] {APP_NAME} :: %(name)s: %(message)s'))

    root_logger = logging.getLogger()  # root logger to catch any logs from libraries that don't use the app logger
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(cabbo_debug_handler)
    root_logger.addHandler(cabbo_error_handler)

# Optionally, set root logger to propagate if you want logs everywhere
#logging.getLogger().setLevel(logging.DEBUG)
