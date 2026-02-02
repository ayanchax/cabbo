from typing import Callable, Any, Dict
from fastapi import BackgroundTasks
import inspect
import logging

logger = logging.getLogger(__name__)


class BackgroundTaskOrchestrator:
    """
    Generic orchestration service for managing FastAPI background tasks.
    """

    def __init__(self, background_tasks: BackgroundTasks):
        self._background_tasks = background_tasks

    def add_task(
        self,
        task_func: Callable[..., Any],
        *,
        task_name: str | None = None,
        **kwargs: Dict[str, Any],
    ) -> None:
        """
        Register a background task.

        :param task_func: Function to execute in background
        :param task_name: Optional human-readable name for logging
        :param kwargs: Arguments passed to the task function
        """

        if not callable(task_func):
            raise ValueError("task_func must be callable")

        name = task_name or task_func.__name__

        logger.info(
            "Registering background task",
            extra={
                "task": name,
                "args": kwargs,
            },
        )

        self._background_tasks.add_task(
            self._execute_task,
            task_func,
            name,
            kwargs,
        )

    async def _execute_task(
        self,
        task_func: Callable[..., Any],
        task_name: str,
        kwargs: Dict[str, Any],
    ) -> None:
        """
        Wrapper that executes the actual task.
        Handles sync & async functions uniformly.
        """

        try:
            logger.info(f"Starting background task: {task_name}")

            if inspect.iscoroutinefunction(task_func):
                await task_func(**kwargs)
            else:
                task_func(**kwargs)

            logger.info(f"Completed background task: {task_name}")

        except Exception as exc:
            logger.exception(
                f"Background task failed: {task_name}",
                extra={"error": str(exc)},
            )
