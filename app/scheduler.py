from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings
from app.workers import celery_app


def enqueue_generation_batch() -> None:
    celery_app.send_task(
        "app.tasks.create_and_generate_batch_task",
        kwargs={"count": settings.default_batch_size, "force_topic": None},
    )


def enqueue_publish_processing() -> None:
    celery_app.send_task("app.tasks.process_publish_queue_task")


def run_scheduler() -> None:
    if not settings.enable_scheduler:
        print("Scheduler disabled via ENABLE_SCHEDULER=false")
        return

    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        enqueue_generation_batch,
        trigger=CronTrigger.from_crontab(settings.schedule_cron),
        id="generation_batch",
        replace_existing=True,
    )
    scheduler.add_job(
        enqueue_publish_processing,
        trigger="interval",
        minutes=5,
        id="publish_queue",
        replace_existing=True,
    )

    print(f"Scheduler started. Batch cron: {settings.schedule_cron}")
    scheduler.start()


if __name__ == "__main__":
    run_scheduler()
