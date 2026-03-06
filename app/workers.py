from celery import Celery

from app.config import settings


celery_app = Celery(
    "reel_empire",
    broker=settings.rabbitmq_url,
    backend=settings.redis_url,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    timezone="UTC",
)
