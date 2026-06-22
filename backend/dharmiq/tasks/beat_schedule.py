from celery.schedules import crontab

from dharmiq.config.settings import get_settings
from dharmiq.tasks.celery_app import celery_app

settings = get_settings()

if settings.beat_schedule.enabled:
    celery_app.conf.beat_schedule = {
        "sync-india-code-pdfs-daily": {
            "task": "dharmiq.ingestion.sync_india_code_pdfs",
            "schedule": crontab(hour=2, minute=0),
        },
    }
else:
    celery_app.conf.beat_schedule = {}
