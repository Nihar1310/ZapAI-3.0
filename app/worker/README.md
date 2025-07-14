# ZapAI Background Worker System

This directory contains the background worker system for ZapAI, implementing contact enrichment using Apollo.io integration with Celery for job queue management.

## Components

### 1. Celery Application (`celery_app.py`)
- Configures Celery with Redis as broker and result backend
- Sets up task routing and retry policies
- Configures compression and timeout settings

### 2. Enrichment Worker (`enrichment_worker.py`)
- Main worker implementation for contact enrichment
- Apollo.io API integration for contact data enhancement
- Batch processing with rate limiting
- Error handling and retry mechanisms

### 3. Apollo Client (`../services/apollo_client.py`)
- Apollo.io API wrapper with circuit breaker pattern
- Rate limiting and quota management
- Contact enrichment and data processing
- Cost tracking and health checks

## Key Features

### Background Processing
- **Asynchronous Tasks**: Contact enrichment runs in background after payment
- **Job Queues**: Organized task processing with proper queue management
- **Retry Logic**: Automatic retry for temporary failures with exponential backoff
- **Status Tracking**: Real-time task status and progress monitoring

### Apollo.io Integration
- **Contact Enrichment**: Enhance contact data with job titles, company info, social profiles
- **Batch Processing**: Process up to 10 contacts per API request (configurable)
- **Rate Limiting**: Respect Apollo.io API limits (100 requests/minute default)
- **Cost Tracking**: Monitor API usage costs ($0.10 per contact enrichment)

### Reliability Features
- **Circuit Breaker**: Prevent cascade failures when Apollo.io is down
- **Health Checks**: Monitor service availability
- **Fallback Mechanisms**: Graceful degradation when services unavailable
- **Error Recovery**: Comprehensive error handling and logging

## Configuration

### Environment Variables
```bash
# Celery Configuration
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Apollo.io Configuration
APOLLO_API_KEY=your_apollo_api_key
APOLLO_MAX_CONTACTS_PER_REQUEST=10
APOLLO_RATE_LIMIT_PER_MINUTE=100
```

### Dependencies
- `celery==5.3.4` - Task queue management
- `redis==5.0.1` - Message broker and result backend
- `apolloapi==1.0.3` - Apollo.io API client (placeholder)

## Usage

### Starting the Worker
```bash
# Method 1: Using the start script
python scripts/start_worker.py

# Method 2: Direct Celery command
celery -A app.worker.celery_app worker --loglevel=info --concurrency=2 --queues=enrichment
```

### Monitoring Tasks
```python
from app.worker import start_enrichment, get_task_status

# Start enrichment for a search
task_id = start_enrichment("search-uuid-here")

# Check task status
status = get_task_status(task_id)
print(f"Status: {status['status']}, Result: {status['result']}")
```

### Health Checks
```python
from app.worker import get_worker_health

health = get_worker_health()
print(f"Worker Ready: {health['worker_ready']}")
print(f"Celery Available: {health['celery_available']}")
```

## Task Flow

### 1. Search Preview → Payment → Enrichment
```
1. User gets search preview (masked emails)
2. User pays for full enrichment
3. Payment service triggers enrichment task
4. Worker processes contacts in batches
5. Apollo.io enriches contact data
6. Results saved to database
7. Search status updated to "ready"
```

### 2. Batch Processing
```
1. Extract contacts from search results
2. Group into batches (≤10 contacts)
3. Send to Apollo.io for enrichment
4. Process and save enriched data
5. Update costs and statistics
6. Continue with next batch
```

## Error Handling

### Retry Strategy
- **Temporary Failures**: Retry with exponential backoff
- **Rate Limiting**: Wait and retry after rate limit reset
- **Circuit Breaker**: Stop requests when service is down
- **Maximum Retries**: Fail after 3 attempts for enrichment tasks

### Fallback Behavior
- **Apollo.io Down**: Return original contact data
- **Celery Unavailable**: Log warning, continue with synchronous processing
- **Database Issues**: Retry database operations, log errors

## Monitoring and Logging

### Task Monitoring
- Task status tracking (pending, running, success, failure)
- Processing time and performance metrics
- Cost tracking per search and per contact
- Error rates and failure analysis

### Logging
- Structured logging with correlation IDs
- Performance metrics (latency, throughput)
- Error tracking with stack traces
- Apollo.io API response monitoring

## Development

### Testing Without Dependencies
The worker system includes fallback mechanisms for development without Celery:
- Import errors are handled gracefully
- Functions return appropriate error messages
- System remains functional in preview mode

### Local Development
1. Install Redis: `brew install redis` (macOS) or `apt-get install redis-server` (Ubuntu)
2. Start Redis: `redis-server`
3. Install dependencies: `pip install -r requirements.txt`
4. Start worker: `python scripts/start_worker.py`

## Production Deployment

### Scaling
- Run multiple worker processes for higher throughput
- Use separate queues for different task types
- Monitor queue length and processing times

### Monitoring
- Set up Celery monitoring with Flower
- Configure alerts for failed tasks
- Monitor Apollo.io API usage and costs

### Security
- Secure Redis instance with authentication
- Encrypt sensitive configuration data
- Monitor API key usage and rotation 