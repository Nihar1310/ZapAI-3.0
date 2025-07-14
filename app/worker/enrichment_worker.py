"""Background worker for contact enrichment using Apollo.io."""
import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

# Note: These imports will work once dependencies are installed
try:
    from celery import Task
    from celery.exceptions import Retry
    from app.worker.celery_app import celery_app
    from app.services.apollo_client import ApolloClient
    from app.config import get_settings
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False
    # Fallback for development without Celery
    class Task:
        def on_success(self, retval, task_id, args, kwargs):
            pass
        def on_failure(self, exc, task_id, args, kwargs, einfo):
            pass

logger = logging.getLogger(__name__)


class CallbackTask(Task):
    """Base task class with callbacks."""
    
    def on_success(self, retval, task_id, args, kwargs):
        """Called on task success."""
        logger.info(f"Task {self.name} [{task_id}] succeeded")
        
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Called on task failure."""
        logger.error(f"Task {self.name} [{task_id}] failed: {exc}")


def create_enrichment_task():
    """Create enrichment task if Celery is available."""
    if not CELERY_AVAILABLE:
        logger.warning("Celery not available, enrichment tasks will run synchronously")
        return None
        
    @celery_app.task(bind=True, base=CallbackTask)
    def enrich_search_task(self, search_id: str) -> Dict[str, Any]:
        """
        Main task to enrich a search after payment confirmation.
        
        Args:
            search_id: UUID of the search to enrich
            
        Returns:
            Dict with enrichment results and statistics
        """
        logger.info(f"Starting enrichment for search {search_id}")
        
        try:
            # Run the async enrichment process
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                result = loop.run_until_complete(_enrich_search_async(search_id))
                return result
            finally:
                loop.close()
                
        except Exception as e:
            logger.error(f"Enrichment failed for search {search_id}: {str(e)}")
            
            # Update search status to failed
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(_update_search_status(search_id, "failed"))
            finally:
                loop.close()
                
            # Retry the task if it's a temporary failure
            if isinstance(e, (ConnectionError, TimeoutError)) and self.request.retries < 3:
                logger.info(f"Retrying enrichment for search {search_id} (attempt {self.request.retries + 1})")
                raise self.retry(countdown=60 * (2 ** self.request.retries), exc=e)
                
            raise e
    
    return enrich_search_task


# Create task if Celery is available
enrich_search_task = create_enrichment_task()


async def _enrich_search_async(search_id: str) -> Dict[str, Any]:
    """Async implementation of search enrichment."""
    # This is a simplified version that will be enhanced once database layer is properly set up
    logger.info(f"Processing enrichment for search {search_id}")
    
    # Initialize Apollo client
    apollo_client = ApolloClient()
    
    enrichment_stats = {
        "search_id": search_id,
        "status": "processing",
        "started_at": datetime.utcnow().isoformat()
    }
    
    try:
        # Health check Apollo service
        apollo_healthy = await apollo_client.health_check()
        if not apollo_healthy:
            raise Exception("Apollo service is not available")
            
        # For now, return a placeholder result
        # This will be enhanced with actual database integration
        enrichment_stats["status"] = "completed"
        enrichment_stats["apollo_available"] = str(apollo_healthy)
        enrichment_stats["completed_at"] = datetime.utcnow().isoformat()
        
        logger.info(f"Enrichment completed for search {search_id}")
        return enrichment_stats
        
    except Exception as e:
        enrichment_stats["status"] = "failed"
        enrichment_stats["error"] = str(e)
        enrichment_stats["completed_at"] = datetime.utcnow().isoformat()
        logger.error(f"Enrichment failed for search {search_id}: {str(e)}")
        raise e


async def _update_search_status(search_id: str, status: str):
    """Update search status."""
    # Placeholder for database status update
    logger.info(f"Updating search {search_id} status to {status}")


async def enrich_contacts_batch(contacts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Enrich a batch of contacts using Apollo.io.
    
    Args:
        contacts: List of contact dictionaries with email/name/company info
        
    Returns:
        List of enriched contact dictionaries
    """
    logger.info(f"Enriching {len(contacts)} contacts")
    
    try:
        apollo_client = ApolloClient()
        enriched_contacts = await apollo_client.enrich_contacts(contacts)
        
        logger.info(f"Successfully enriched {len(enriched_contacts)} out of {len(contacts)} contacts")
        return enriched_contacts
        
    except Exception as e:
        logger.error(f"Failed to enrich contacts: {str(e)}")
        return contacts  # Return original contacts as fallback


def create_batch_processing_task():
    """Create batch processing task if Celery is available."""
    if not CELERY_AVAILABLE:
        return None
        
    @celery_app.task(bind=True, base=CallbackTask)
    def process_contact_batch(self, contacts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Process a batch of contacts for enrichment.
        
        Args:
            contacts: List of contact dictionaries to enrich
            
        Returns:
            Dict with batch processing results
        """
        logger.info(f"Processing contact batch with {len(contacts)} contacts")
        
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                enriched_contacts = loop.run_until_complete(
                    enrich_contacts_batch(contacts)
                )
                
                apollo_client = ApolloClient()
                cost = apollo_client.get_cost_estimate(len(contacts))
                
                return {
                    "status": "success",
                    "input_count": len(contacts),
                    "output_count": len(enriched_contacts),
                    "enriched_contacts": enriched_contacts,
                    "cost": cost
                }
                
            finally:
                loop.close()
                
        except Exception as e:
            logger.error(f"Contact batch processing failed: {str(e)}")
            
            # Retry for temporary failures
            if isinstance(e, (ConnectionError, TimeoutError)) and self.request.retries < 2:
                logger.info(f"Retrying contact batch processing (attempt {self.request.retries + 1})")
                raise self.retry(countdown=30 * (2 ** self.request.retries), exc=e)
                
            return {
                "status": "failed",
                "error": str(e),
                "input_count": len(contacts),
                "output_count": 0
            }
    
    return process_contact_batch


# Create batch task if Celery is available
process_contact_batch = create_batch_processing_task()


# Utility functions for manual task management
def start_enrichment(search_id: str) -> Optional[str]:
    """Start enrichment task for a search."""
    if not enrich_search_task:
        logger.warning("Celery not available, cannot start background enrichment")
        return None
        
    task = enrich_search_task.delay(search_id)
    logger.info(f"Started enrichment task {task.id} for search {search_id}")
    return task.id


def get_task_status(task_id: str) -> Dict[str, Any]:
    """Get status of a Celery task."""
    if not CELERY_AVAILABLE:
        return {"error": "Celery not available"}
        
    task_result = celery_app.AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status": task_result.status,
        "result": task_result.result if task_result.ready() else None,
        "traceback": task_result.traceback if task_result.failed() else None
    }


def get_worker_health() -> Dict[str, Any]:
    """Get worker system health status."""
    return {
        "celery_available": CELERY_AVAILABLE,
        "timestamp": datetime.utcnow().isoformat(),
        "worker_ready": True
    }
