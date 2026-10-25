"""Shared retry timing for payment recovery workers."""

RETRY_INITIAL_DELAY_SECONDS = 60
RETRY_BACKOFF_MULTIPLIER = 2
RETRY_MAX_DELAY_SECONDS = 900
# At exponent 4 the delay reaches 960 seconds, exceeding the 900-second cap.
RETRY_MAX_EXPONENT = 4


def get_retry_delay_seconds(attempt: int) -> int:
    """Return capped exponential backoff; attempt 1 waits one minute.

    Bound the exponent before calculating the power, without modifying the
    persisted attempt counter. Nonpositive counts use the initial delay.
    """
    exponent = min(max(attempt - 1, 0), RETRY_MAX_EXPONENT)
    return min(
        RETRY_INITIAL_DELAY_SECONDS * RETRY_BACKOFF_MULTIPLIER ** exponent,
        RETRY_MAX_DELAY_SECONDS,
    )
