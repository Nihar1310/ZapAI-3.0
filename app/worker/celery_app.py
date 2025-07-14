"""Celery application configuration."""
import os
from celery import Celery
from app.config import get_settings

# Get settings
settings = get_settings()

# Create Celery instance
celery_app = Celery(
    "zapai_worker",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.worker.enrichment_worker"]
)

# Configure Celery
celery_app.conf.update(
    task_serializer=settings.celery_task_serializer,
    result_serializer=settings.celery_result_serializer,
    accept_content=settings.celery_accept_content,
    timezone=settings.celery_timezone,
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes max per task
    task_soft_time_limit=240,  # 4 minute warning
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_disable_rate_limits=False,
    task_compression="gzip",
    result_compression="gzip",
    result_expires=3600,  # Results expire after 1 hour
    task_routes={
        "app.worker.enrichment_worker.enrich_search_task": {"queue": "enrichment"},
        "app.worker.enrichment_worker.process_contact_batch": {"queue": "enrichment"},
    },
)

# Configure task retry settings
celery_app.conf.task_annotations = {
    "*": {
        "rate_limit": "10/m",  # 10 tasks per minute by default
        "time_limit": 300,
        "soft_time_limit": 240,
    },
    "app.worker.enrichment_worker.enrich_search_task": {
        "rate_limit": "5/m",  # 5 enrichment tasks per minute
        "max_retries": 3,
        "default_retry_delay": 60,  # 1 minute retry delay
    },
}

# Auto-discover tasks
celery_app.autodiscover_tasks(["app.worker"]) 