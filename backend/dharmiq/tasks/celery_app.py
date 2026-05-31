from __future__ import annotations

from celery import Celery

from dharmiq.config.settings import get_settings

settings = get_settings()

celery_app = Celery(
    "dharmiq",
    broker=settings.redis.url,
    backend=settings.redis.url,
    include=["dharmiq.tasks.sample_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
)
