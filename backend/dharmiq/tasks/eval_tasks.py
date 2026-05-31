"""Celery tasks for evaluation runs."""

from __future__ import annotations

import asyncio

from dharmiq.config.settings import get_settings
from dharmiq.core.logging import get_logger, setup_logging
from dharmiq.db.session import close_db, get_session_factory, init_db
from dharmiq.eval.runner import run_eval_dataset
from dharmiq.tasks.celery_app import celery_app

logger = get_logger(__name__)


def _run_async(coro):
    return asyncio.run(coro)


async def _with_db_session(coro_factory):
    await init_db()
    factory = get_session_factory()
    try:
        async with factory() as db:
            return await coro_factory(db)
    finally:
        await close_db()


@celery_app.task(name="dharmiq.eval.run_dataset", bind=True, max_retries=1)
def run_dataset_eval(self, dataset_name: str) -> dict[str, str | float | int]:
    """Run an evaluation dataset through the RAG pipeline and store results."""
    settings = get_settings()
    setup_logging(settings)
    logger.info("eval_run_started", dataset=dataset_name)

    async def _run(db):
        summary = await run_eval_dataset(db, dataset_name, settings=settings)
        return summary

    try:
        summary = _run_async(_with_db_session(_run))
    except Exception as exc:
        logger.exception("eval_run_failed", dataset=dataset_name, error=str(exc))
        raise self.retry(exc=exc, countdown=120) from exc

    return {
        "run_id": str(summary.run_id),
        "dataset": summary.dataset_name,
        "model": summary.model,
        "question_count": summary.question_count,
        "output_path": str(summary.output_path),
        **{f"metric_{key}": value for key, value in summary.aggregate_metrics.items()},
    }
