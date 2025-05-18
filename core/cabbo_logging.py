import logging
import os
from logging.handlers import TimedRotatingFileHandler
from core.constants import APP_NAME
# Ensure logs directory exists
LOG_DIR = os.path.join(os.path.dirname(__file__), '..', 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

## Debug and Info log handler for capturing all logs(Rotating Setup)
cabbo_debug_handler = TimedRotatingFileHandler(
    os.path.join(LOG_DIR, 'debug.log'), when='midnight', interval=1, backupCount=30, encoding='utf-8'
)
cabbo_debug_handler.setLevel(logging.DEBUG)
cabbo_debug_handler.setFormatter(logging.Formatter(f'%(asctime)s [%(levelname)s] {APP_NAME} :: %(name)s: %(message)s'))

## Error log handler for capturing error messages(Rotating Setup)
cabbo_error_handler = TimedRotatingFileHandler(
    os.path.join(LOG_DIR, 'error.log'), when='midnight', interval=1, backupCount=30, encoding='utf-8'
)
cabbo_error_handler.setLevel(logging.ERROR)
cabbo_error_handler.setFormatter(logging.Formatter(f'%(asctime)s [%(levelname)s] {APP_NAME} :: %(name)s: %(message)s'))

# Console handler for real-time logging
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(f'%(asctime)s [%(levelname)s] {APP_NAME} :: %(name)s: %(message)s'))

# Set up the app logger
logging.basicConfig(
    level=logging.DEBUG,
    handlers=[cabbo_debug_handler, cabbo_error_handler, console_handler]
)
