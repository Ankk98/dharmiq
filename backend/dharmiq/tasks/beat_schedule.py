from celery.schedules import crontab

from dharmiq.tasks.celery_app import celery_app

celery_app.conf.beat_schedule = {
    "sync-india-code-pdfs-daily": {
        "task": "dharmiq.ingestion.sync_india_code_pdfs",
        "schedule": crontab(hour=2, minute=0),
    },
}
