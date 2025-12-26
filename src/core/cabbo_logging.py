import logging
import os
from logging.handlers import TimedRotatingFileHandler
from core.constants import APP_NAME

LOG_DIR = os.path.join(os.path.dirname(__file__), '..', 'logs')
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

    logger.setLevel(logging.DEBUG)
    logger.addHandler(cabbo_debug_handler)
    logger.addHandler(cabbo_error_handler)
    logger.addHandler(console_handler)

# Optionally, set root logger to propagate if you want logs everywhere
#logging.getLogger().setLevel(logging.DEBUG)
