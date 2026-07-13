import logging

from apscheduler.schedulers.background import BackgroundScheduler
from scheduler.tasks import TASKS
scheduler = BackgroundScheduler()
log = logging.getLogger(__name__)
def start_scheduler():
    if scheduler.running:
        return
    
    for task in TASKS:
        scheduler.add_job(
            task["func"],
            trigger=task["trigger"],
            id=task["id"],
            replace_existing=task.get("replace_existing", True),
            max_instances=task.get("max_instances", 1),
            args=task.get("args", ()),
            kwargs=task.get("kwargs", {}),
        )
        log.info(f"Added job {task['id']} which runs every {task['trigger']} minutes")
    scheduler.start()
    log.info(f"APScheduler started with {len(TASKS)} jobs.")
    
     

def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        log.info("APScheduler stopped")