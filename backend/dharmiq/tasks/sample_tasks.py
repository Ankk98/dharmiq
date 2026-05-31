"""Sample Celery tasks for infrastructure verification."""

from __future__ import annotations

from dharmiq.tasks.celery_app import celery_app


@celery_app.task(name="dharmiq.ping")
def ping() -> str:
    return "pong"
