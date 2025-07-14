"""Payment API endpoints for Stripe integration."""
import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from ...database import get_db
from ...services.payment_service import payment_service, PaymentServiceError
from ...utils.auth import get_current_user_id  # Assuming auth utility exists
from ...models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


class CheckoutRequest(BaseModel):
    """Request model for creating checkout session."""
    search_id: int = Field(..., description="ID of the search to purchase enrichment for")


class CheckoutResponse(BaseModel):
    """Response model for checkout session creation."""
    payment_id: int = Field(..., description="Internal payment ID")
    checkout_url: str = Field(..., description="Stripe checkout URL")
    session_id: str = Field(..., description="Stripe session ID")


class PaymentStatusResponse(BaseModel):
    """Response model for payment status."""
    payment_id: int
    search_id: int
    amount: float
    status: str
    stripe_session_id: str
    created_at: str
    updated_at: str | None = None
    search_status: str | None = None


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout_session(
    request: CheckoutRequest,
    db: AsyncSession = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
) -> CheckoutResponse:
    """
    Create a Stripe checkout session for search enrichment.
    
    This endpoint creates a Stripe checkout session that allows users to pay
    for enrichment of their search results with full contact details.
    """
    try:
        result = await payment_service.create_checkout_session(
            search_id=request.search_id,
            user_id=current_user_id,
            db=db
        )
        
        return CheckoutResponse(
            payment_id=result["payment_id"],
            checkout_url=result["checkout_url"],
            session_id=result["session_id"]
        )
        
    except PaymentServiceError as e:
        logger.error(f"Payment service error for user {current_user_id}, search {request.search_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error creating checkout session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create checkout session"
        )


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> JSONResponse:
    """
    Handle Stripe webhook events.
    
    This endpoint receives and processes webhook events from Stripe,
    including payment completions and failures.
    """
    try:
        # Get raw body and signature
        payload = await request.body()
        signature = request.headers.get("stripe-signature")
        
        if not signature:
            logger.error("Missing Stripe signature header")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing signature header"
            )
        
        # Process webhook
        result = await payment_service.handle_webhook(payload, signature, db)
        
        logger.info(f"Webhook processed: {result}")
        return JSONResponse(content=result)
        
    except PaymentServiceError as e:
        logger.error(f"Payment service error in webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error processing webhook: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process webhook"
        )


@router.get("/status/{payment_id}", response_model=PaymentStatusResponse)
async def get_payment_status(
    payment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
) -> PaymentStatusResponse:
    """
    Get payment status for a specific payment.
    
    Returns the current status of a payment, including associated search status.
    """
    try:
        result = await payment_service.get_payment_status(
            payment_id=payment_id,
            user_id=current_user_id,
            db=db
        )
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment not found"
            )
        
        return PaymentStatusResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error getting payment status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get payment status"
        )


@router.get("/success")
async def payment_success(
    session_id: str,
    search_id: int,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Payment success page endpoint.
    
    This endpoint is called when users return from successful Stripe checkout.
    """
    try:
        # In a real implementation, you might want to verify the session
        # and provide a success page or redirect to the search results
        return {
            "status": "success",
            "message": "Payment completed successfully",
            "search_id": search_id,
            "session_id": session_id
        }
        
    except Exception as e:
        logger.error(f"Error in payment success handler: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to handle payment success"
        )


@router.get("/cancel")
async def payment_cancel(search_id: int) -> Dict[str, Any]:
    """
    Payment cancellation endpoint.
    
    This endpoint is called when users cancel the Stripe checkout.
    """
    try:
        return {
            "status": "cancelled",
            "message": "Payment was cancelled",
            "search_id": search_id
        }
        
    except Exception as e:
        logger.error(f"Error in payment cancel handler: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to handle payment cancellation"
        )
