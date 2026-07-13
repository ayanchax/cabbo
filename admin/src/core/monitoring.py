from core.config import settings
from cabbo_core.constants import APP_VERSION, Environment
from sentry_sdk.integrations.logging import LoggingIntegration
import logging
import sentry_sdk
from cabbo_core.sentry import before_send

log = logging.getLogger(__name__)


def configure_sentry() -> None:
    if settings.ENV not in {Environment.DEV.value, Environment.PROD.value}:
        return

    sentry_dsn = settings.SENTRY_DSN.strip().strip("\"'")
    if not sentry_dsn:
        return

    sentry_logging = LoggingIntegration(
        level=logging.WARNING,
        event_level=logging.ERROR,
        sentry_logs_level=logging.WARNING,
    )

    sentry_sdk.init(
        dsn=sentry_dsn,
        environment=settings.SENTRY_ENVIRONMENT or settings.ENV,
        release=settings.SENTRY_RELEASE or APP_VERSION,
        sample_rate=settings.SENTRY_ERROR_SAMPLE_RATE,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        profiles_sample_rate=settings.SENTRY_PROFILES_SAMPLE_RATE,
        send_default_pii=False,
        enable_logs=settings.SENTRY_ENABLE_LOGS,
        max_request_body_size="never",
        integrations=[sentry_logging],
        before_send=before_send,
    )
    log.info("Sentry configured successfully")
