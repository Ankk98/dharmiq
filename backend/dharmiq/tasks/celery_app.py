from __future__ import annotations

from celery import Celery
from celery.signals import worker_process_init, worker_ready

from dharmiq.config.settings import get_settings
from dharmiq.core.logging import get_logger, setup_logging

logger = get_logger(__name__)

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
        "dharmiq.tasks.chat_tasks",
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


@worker_ready.connect
def _recover_pending_chat_requests(**_kwargs) -> None:
    from dharmiq.tasks.chat_tasks import recover_pending_agent_graph_requests

    try:
        recovered = recover_pending_agent_graph_requests()
        if recovered:
            logger.info("recovered_pending_chat_requests", count=recovered)
    except Exception:
        logger.exception("recover_pending_chat_requests_failed")
