from typing import Any, Dict, List
from apscheduler.triggers.interval import IntervalTrigger

from scheduler.tasks.process_refund import sync_pending_refund_statuses_task
from .cleanup_temp_trips import cleanup_temp_trips_task

DEFAULT_INTERVAL_MINUTES = 15
REFUND_POLL_INTERVAL_MINUTES = 60


# Centralized TASKS list for the scheduler to consume
TASKS: List[Dict[str, Any]] = [
    {
        "func": cleanup_temp_trips_task,
        "trigger": IntervalTrigger(minutes=DEFAULT_INTERVAL_MINUTES),
        "id": "ap_scheduler_job:cleanup_temp_trips",
        # "args": (),  # positional args passed to the task function
        # "kwargs": {},
        # "replace_existing": True,
        # "max_instances": 1,
    },
    {
        "func": sync_pending_refund_statuses_task,   
        "trigger": IntervalTrigger(minutes=REFUND_POLL_INTERVAL_MINUTES),
        "id": "ap_scheduler_job:sync_pending_refund_statuses",
    },
]
