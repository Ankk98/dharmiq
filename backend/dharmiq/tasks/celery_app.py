from __future__ import annotations

from celery import Celery
from celery.signals import worker_process_init

from dharmiq.config.settings import get_settings
from dharmiq.core.logging import setup_logging

settings = get_settings()

celery_app = Celery(
    "dharmiq",
    broker=settings.redis.url,
    backend=settings.redis.url,
    include=[
        "dharmiq.tasks.sample_tasks",
        "dharmiq.tasks.ingestion_tasks",
        "dharmiq.tasks.eval_tasks",
        "dharmiq.tasks.beat_schedule",
    ],
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


@worker_process_init.connect
def _init_worker_logging(**_kwargs) -> None:
    setup_logging(get_settings())
