"""Stripe payment service for handling payments and webhooks."""
import logging
import stripe
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from ..config import get_settings
from ..database import get_db
from ..models.payment import Payment, PaymentStatus
from ..models.search import SearchQuery, SearchStatus
from ..models.user import User

logger = logging.getLogger(__name__)
settings = get_settings()

# Configure Stripe
if settings.stripe_api_key:
    stripe.api_key = settings.stripe_api_key
else:
    logger.warning("Stripe API key not configured. Payment functionality will be disabled.")


class PaymentServiceError(Exception):
    """Base exception for payment service errors."""
    pass


class PaymentService:
    """Service for handling Stripe payments and webhooks."""
    
    def __init__(self):
        self.settings = settings
        if not self.settings.stripe_api_key:
            logger.warning("PaymentService initialized without Stripe API key")
    
    async def create_checkout_session(
        self,
        search_id: int,
        user_id: int,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """Create a Stripe checkout session for a search enrichment."""
        try:
            # Validate that search exists and belongs to user
            search_query = await self._get_search_query(search_id, user_id, db)
            if not search_query:
                raise PaymentServiceError(f"Search {search_id} not found or doesn't belong to user {user_id}")
            
            # Check if search is in preview status
            if search_query.status != SearchStatus.preview:
                raise PaymentServiceError(f"Search {search_id} is not in preview status. Current status: {search_query.status}")
            
            # Check for existing pending payment
            existing_payment = await self._get_pending_payment(search_id, db)
            if existing_payment:
                # Return existing session if still valid
                try:
                    session = stripe.checkout.Session.retrieve(existing_payment.stripe_session_id)
                    if session.status == 'open':
                        return {
                            "payment_id": existing_payment.id,
                            "checkout_url": session.url,
                            "session_id": session.id
                        }
                except stripe.error.InvalidRequestError:
                    # Session expired or invalid, continue to create new one
                    pass
            
            # Get user for customer information
            user = await self._get_user(user_id, db)
            if not user:
                raise PaymentServiceError(f"User {user_id} not found")
            
            # Create Stripe checkout session
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': self.settings.stripe_currency,
                        'product_data': {
                            'name': f'Search Enrichment - "{search_query.query[:50]}..."',
                            'description': 'Get full contact details with email addresses and phone numbers',
                        },
                        'unit_amount': int(self.settings.stripe_price_per_search * 100),  # Convert to cents
                    },
                    'quantity': 1,
                }],
                mode='payment',
                success_url=self.settings.stripe_success_url + f"?session_id={{CHECKOUT_SESSION_ID}}&search_id={search_id}",
                cancel_url=self.settings.stripe_cancel_url + f"?search_id={search_id}",
                metadata={
                    'search_id': str(search_id),
                    'user_id': str(user_id),
                },
                customer_email=user.email if hasattr(user, 'email') else None,
            )
            
            # Create or update payment record
            if existing_payment:
                existing_payment.stripe_session_id = checkout_session.id
                existing_payment.status = PaymentStatus.pending
                payment = existing_payment
            else:
                payment = Payment(
                    user_id=user_id,
                    search_id=search_id,
                    stripe_session_id=checkout_session.id,
                    amount=self.settings.stripe_price_per_search,
                    status=PaymentStatus.pending
                )
                db.add(payment)
            
            await db.commit()
            await db.refresh(payment)
            
            logger.info(f"Created checkout session {checkout_session.id} for search {search_id}")
            
            return {
                "payment_id": payment.id,
                "checkout_url": checkout_session.url,
                "session_id": checkout_session.id
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error creating checkout session: {e}")
            raise PaymentServiceError(f"Failed to create checkout session: {str(e)}")
        except Exception as e:
            logger.error(f"Error creating checkout session: {e}")
            await db.rollback()
            raise PaymentServiceError(f"Failed to create checkout session: {str(e)}")
    
    async def handle_webhook(self, payload: bytes, signature: str, db: AsyncSession) -> Dict[str, Any]:
        """Handle Stripe webhook events."""
        try:
            if not self.settings.stripe_webhook_secret:
                raise PaymentServiceError("Stripe webhook secret not configured")
            
            # Verify webhook signature
            event = stripe.Webhook.construct_event(
                payload, signature, self.settings.stripe_webhook_secret
            )
            
            logger.info(f"Received Stripe webhook: {event['type']}")
            
            if event['type'] == 'checkout.session.completed':
                return await self._handle_checkout_completed(event['data']['object'], db)
            elif event['type'] == 'payment_intent.payment_failed':
                return await self._handle_payment_failed(event['data']['object'], db)
            else:
                logger.info(f"Unhandled webhook event type: {event['type']}")
                return {"status": "ignored", "event_type": event['type']}
                
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Invalid webhook signature: {e}")
            raise PaymentServiceError("Invalid webhook signature")
        except Exception as e:
            logger.error(f"Error handling webhook: {e}")
            raise PaymentServiceError(f"Failed to handle webhook: {str(e)}")
    
    async def _handle_checkout_completed(self, session: Dict[str, Any], db: AsyncSession) -> Dict[str, Any]:
        """Handle successful checkout completion."""
        try:
            session_id = session['id']
            search_id = int(session['metadata']['search_id'])
            user_id = int(session['metadata']['user_id'])
            
            # Find and update payment record
            payment = await self._get_payment_by_session_id(session_id, db)
            if not payment:
                logger.error(f"Payment record not found for session {session_id}")
                return {"status": "error", "message": "Payment record not found"}
            
            # Update payment status
            payment.status = PaymentStatus.paid
            
            # Update search status to paid (ready for enrichment)
            search_query = await self._get_search_query(search_id, user_id, db)
            if search_query:
                search_query.status = SearchStatus.paid
            
            await db.commit()
            
            logger.info(f"Payment completed for search {search_id}, session {session_id}")
            
            # TODO: Trigger background enrichment job here
            # This will be implemented in T-5 (Background Worker System)
            
            return {
                "status": "success",
                "payment_id": payment.id,
                "search_id": search_id,
                "message": "Payment processed successfully"
            }
            
        except Exception as e:
            logger.error(f"Error handling checkout completion: {e}")
            await db.rollback()
            return {"status": "error", "message": str(e)}
    
    async def _handle_payment_failed(self, payment_intent: Dict[str, Any], db: AsyncSession) -> Dict[str, Any]:
        """Handle failed payment."""
        try:
            # Find payment by session ID (if available in metadata)
            if 'metadata' in payment_intent and 'session_id' in payment_intent['metadata']:
                session_id = payment_intent['metadata']['session_id']
                payment = await self._get_payment_by_session_id(session_id, db)
                
                if payment:
                    payment.status = PaymentStatus.failed
                    await db.commit()
                    
                    logger.info(f"Payment failed for session {session_id}")
                    return {
                        "status": "success",
                        "payment_id": payment.id,
                        "message": "Payment failure recorded"
                    }
            
            logger.warning(f"Could not find payment record for failed payment intent {payment_intent['id']}")
            return {"status": "ignored", "message": "Payment record not found"}
            
        except Exception as e:
            logger.error(f"Error handling payment failure: {e}")
            await db.rollback()
            return {"status": "error", "message": str(e)}
    
    async def get_payment_status(self, payment_id: int, user_id: int, db: AsyncSession) -> Optional[Dict[str, Any]]:
        """Get payment status for a user."""
        try:
            stmt = select(Payment).where(
                Payment.id == payment_id,
                Payment.user_id == user_id
            ).options(selectinload(Payment.search_query))
            
            result = await db.execute(stmt)
            payment = result.scalar_one_or_none()
            
            if not payment:
                return None
            
            return {
                "payment_id": payment.id,
                "search_id": payment.search_id,
                "amount": payment.amount,
                "status": payment.status.value,
                "stripe_session_id": payment.stripe_session_id,
                "created_at": payment.created_at.isoformat(),
                "updated_at": payment.updated_at.isoformat() if payment.updated_at else None,
                "search_status": payment.search_query.status.value if payment.search_query else None
            }
            
        except Exception as e:
            logger.error(f"Error getting payment status: {e}")
            return None
    
    async def _get_search_query(self, search_id: int, user_id: int, db: AsyncSession) -> Optional[SearchQuery]:
        """Get search query by ID and user ID."""
        stmt = select(SearchQuery).where(
            SearchQuery.id == search_id,
            SearchQuery.user_id == user_id
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def _get_user(self, user_id: int, db: AsyncSession) -> Optional[User]:
        """Get user by ID."""
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def _get_payment_by_session_id(self, session_id: str, db: AsyncSession) -> Optional[Payment]:
        """Get payment by Stripe session ID."""
        stmt = select(Payment).where(Payment.stripe_session_id == session_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def _get_pending_payment(self, search_id: int, db: AsyncSession) -> Optional[Payment]:
        """Get existing pending payment for a search."""
        stmt = select(Payment).where(
            Payment.search_id == search_id,
            Payment.status == PaymentStatus.pending
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()


# Global instance
payment_service = PaymentService()
