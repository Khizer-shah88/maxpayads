from celery import Celery
from app.config import settings

celery_app = Celery(
    "ppc_network",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "app.tasks.click_tasks",
        "app.tasks.fraud_tasks",
        "app.tasks.analytics_tasks",
        "app.tasks.earnings_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "daily-analytics": {
            "task": "app.tasks.analytics_tasks.compute_daily_analytics",
            "schedule": 3600.0,  # Every hour
        },
    },
)
