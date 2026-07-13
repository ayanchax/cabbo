import logging
import os
from logging.handlers import TimedRotatingFileHandler
from cabbo_core.constants import APP_NAME, PROJECT_ROOT, Environment

ENV = os.getenv("ENV", Environment.LOCAL.value)
LOG_FORMAT = f'%(asctime)s [%(levelname)s] {APP_NAME} :: %(name)s: %(message)s'

# Prevent duplicate handlers (important for reload environments)
root_logger = logging.getLogger()

if not root_logger.handlers:
    handlers = []

    if ENV == Environment.LOCAL.value:
        LOG_DIR = os.path.join(PROJECT_ROOT, 'logs')
        os.makedirs(LOG_DIR, exist_ok=True)

        debug_handler = TimedRotatingFileHandler(
            os.path.join(LOG_DIR, 'debug.log'), when='midnight', interval=1, backupCount=15, encoding='utf-8', delay=True
        )
        debug_handler.setLevel(logging.DEBUG) # 10 -> DEBUG and above to debug.log

        error_handler = TimedRotatingFileHandler(
            os.path.join(LOG_DIR, 'error.log'), when='midnight', interval=1, backupCount=15, encoding='utf-8', delay=True
        )
        error_handler.setLevel(logging.ERROR) # 40 -> ERROR and above to error.log

        handlers.extend([debug_handler, error_handler])
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO) # 20 -> INFO and above to console
    handlers.append(console_handler)

    log_level = logging.DEBUG if ENV == Environment.LOCAL.value else logging.INFO
    logging.basicConfig(level=log_level, format=LOG_FORMAT, handlers=handlers)

