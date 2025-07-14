from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Dict, Any, Optional, cast
from uuid import UUID
from pydantic import BaseModel, Field
from datetime import datetime

from app.database import get_db
from app.models.search import SearchQuery, SearchStatus
from app.models.user import User
from app.services.search_orchestrator import SearchOrchestrator
from app.utils.auth import get_current_user_id
from loguru import logger

router = APIRouter()


class SearchRequest(BaseModel):
    """Request model for search preview."""
    query: str = Field(..., min_length=1, max_length=500, description="Search query text")
    filters: Optional[Dict[str, Any]] = Field(None, description="Search filters (location, contact types, etc.)")
    max_pages: int = Field(default=4, ge=1, le=10, description="Maximum pages to process")


class SearchResponse(BaseModel):
    """Response model for search operations."""
    search_id: str
    status: str
    message: str
    data: Optional[Dict[str, Any]] = None


@router.post("/search", response_model=SearchResponse)
async def create_search_preview(
    request: SearchRequest,
    db: AsyncSession = Depends(get_db),
    user_id: Optional[UUID] = Depends(get_current_user_id)
):
    """
    Create a new search and generate preview with masked contact data.
    
    This is the first step in the preview→pay→enrich flow.
    Returns masked contact information and basic search results.
    """
    try:
        # Create new search query in database
        search_query = SearchQuery(
            query_text=request.query,
            user_id=user_id,
            filters=request.filters,
            max_pages=request.max_pages,
            status=SearchStatus.preview
        )
        
        db.add(search_query)
        await db.commit()
        await db.refresh(search_query)
        
        # Cast to UUID to satisfy type checker - after refresh, this is the actual UUID value
        query_uuid = cast(UUID, search_query.id)
        
        logger.info(f"Created search query {query_uuid} for user {user_id}")
        
        # Generate preview using search orchestrator
        orchestrator = SearchOrchestrator(db)
        preview_data = await orchestrator.generate_preview(query_uuid, request)
        
        if "error" in preview_data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=preview_data["error"]
            )
        
        return SearchResponse(
            search_id=str(query_uuid),
            status="preview_ready",
            message="Search preview generated successfully",
            data=preview_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating search preview: {str(e)}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create search preview"
        )


@router.get("/search/{search_id}", response_model=SearchResponse)
async def get_search_status(
    search_id: UUID,
    db: AsyncSession = Depends(get_db),
    user_id: Optional[UUID] = Depends(get_current_user_id)
):
    """
    Get the current status of a search query.
    
    Returns the search status and any available data based on the current stage.
    """
    try:
        # Get search query from database
        result = await db.execute(
            select(SearchQuery).where(SearchQuery.id == search_id)
        )
        search_query = result.scalar_one_or_none()
        
        if not search_query:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Search not found"
            )
        
        # Check if user has access to this search - properly handle nullable values
        user_has_no_access = (
            user_id is not None and 
            search_query.user_id is not None and 
            search_query.user_id != user_id
        )
        if user_has_no_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        # Cast values to satisfy type checker
        query_uuid = cast(UUID, search_query.id)
        query_status = cast(SearchStatus, search_query.status)
        
        # Prepare response data based on status
        response_data = {
            "search_id": str(query_uuid),
            "query": search_query.query_text,
            "status": query_status.value,
            "created_at": search_query.created_at.isoformat(),
            "updated_at": search_query.updated_at.isoformat(),
            "total_results": search_query.total_results,
            "pages_processed": search_query.pages_processed,
            "processing_time": search_query.processing_time
        }
        
        # Add cost information if available
        if search_query.total_cost is not None and search_query.total_cost > 0:
            response_data["cost_breakdown"] = search_query.cost_breakdown
            response_data["total_cost"] = search_query.total_cost
        
        # For preview status, include the firecrawl raw data
        if query_status == SearchStatus.preview and search_query.firecrawl_raw is not None:
            response_data["preview_data"] = search_query.firecrawl_raw
        
        # Status-specific messages
        status_messages = {
            SearchStatus.preview: "Preview ready - upgrade to access full enriched data",
            SearchStatus.paid: "Payment confirmed - starting enrichment process",
            SearchStatus.enriching: "Enriching contacts with additional data",
            SearchStatus.ready: "Search complete - all data available",
            SearchStatus.failed: "Search processing failed"
        }
        
        message = status_messages.get(query_status, "Unknown status")
        
        return SearchResponse(
            search_id=str(query_uuid),
            status=query_status.value,
            message=message,
            data=response_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting search status {search_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get search status"
        ) 