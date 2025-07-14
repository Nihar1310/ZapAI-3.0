"""Worker package for background tasks."""

# Import with fallback for development without Celery
try:
    from .celery_app import celery_app
    from .enrichment_worker import enrich_search_task, process_contact_batch, start_enrichment, get_task_status, get_worker_health
    __all__ = ["celery_app", "enrich_search_task", "process_contact_batch", "start_enrichment", "get_task_status", "get_worker_health"]
except ImportError:
    # Celery not available
    celery_app = None
    enrich_search_task = None
    process_contact_batch = None
    
    def start_enrichment(search_id: str):
        """Fallback function when Celery is not available."""
        return None
        
    def get_task_status(task_id: str):
        return {"error": "Celery not available"}
        
    def get_worker_health():
        return {"celery_available": False, "worker_ready": False}
    
    __all__ = ["start_enrichment", "get_task_status", "get_worker_health"]
