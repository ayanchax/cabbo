from typing import Any, Dict, List
from apscheduler.triggers.interval import IntervalTrigger
from .cleanup_temp_trips import cleanup_temp_trips_task

DEFAULT_INTERVAL_MINUTES = 15

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
]
