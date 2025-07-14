#!/usr/bin/env python
"""Script to start the Celery worker for ZapAI background tasks."""

import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def start_worker():
    """Start the Celery worker."""
    try:
        from app.worker.celery_app import celery_app
        
        # Start the worker
        celery_app.worker_main([
            'worker',
            '--loglevel=info',
            '--concurrency=2',
            '--queues=enrichment',
            '--hostname=zapai-worker@%h'
        ])
        
    except ImportError as e:
        print(f"Error: Failed to import Celery dependencies: {e}")
        print("Please install dependencies with: pip install -r requirements.txt")
        sys.exit(1)
    except Exception as e:
        print(f"Error starting worker: {e}")
        sys.exit(1)

if __name__ == "__main__":
    start_worker() 