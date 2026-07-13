from typing import Callable, Dict

TASK_REGISTRY: Dict[str, Callable] = {}

def task(task_id: str | None = None, description: str | None = None):
    """
    Decorator to mark a function as a scheduler task and register it.
    Usage: @task("cleanup_temp_trips", "Cleanup expired temp trips")
    """
    def decorator(fn: Callable):
        tid = task_id or fn.__name__
        fn._is_scheduler_task = True
        fn._task_id = tid
        fn._task_description = description
        TASK_REGISTRY[tid] = fn
        return fn
    return decorator