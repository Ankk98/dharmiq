"""Celery application entry point for CLI usage.

Usage:
    celery -A celery_app worker --loglevel=info
"""

from dharmiq.tasks.celery_app import celery_app

__all__ = ["celery_app"]
