"""Cost tracking service for API usage monitoring."""
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from loguru import logger

from app.models.user import ApiUsage
from app.models.analytics import CostMetrics
from app.models.cost import Cost
from app.models.search import SearchQuery
from app.config import settings


class CostTracker:
    """Tracks API costs and usage across all services."""
    
    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db
        self.costs = settings.api_costs
        self.current_session_costs: Dict[str, List[Dict]] = {}
    
    async def track_api_usage(
        self, 
        service_name: str, 
        requests_count: int, 
        cost_per_request: float,
        user_id: Optional[UUID] = None,
        query_id: Optional[UUID] = None
    ) -> bool:
        """Track API usage and costs."""
        try:
            total_cost = Decimal(str(cost_per_request)) * requests_count
            
            usage_record = {
                'service_name': service_name,
                'requests_count': requests_count,
                'cost_per_request': cost_per_request,
                'total_cost': float(total_cost),
                'timestamp': datetime.utcnow().isoformat(),
                'user_id': str(user_id) if user_id else None,
                'query_id': str(query_id) if query_id else None
            }
            
            # Store in session for aggregation
            session_key = str(query_id) if query_id else 'global'
            if session_key not in self.current_session_costs:
                self.current_session_costs[session_key] = []
            
            self.current_session_costs[session_key].append(usage_record)
            
            # Store in database if available
            if self.db:
                api_usage = ApiUsage(
                    user_id=user_id,
                    service_name=service_name,
                    requests_count=requests_count,
                    cost=float(total_cost),
                    timestamp=datetime.utcnow()
                )
                
                self.db.add(api_usage)
                await self.db.commit()
            
            logger.debug(f"Tracked {service_name}: {requests_count} requests, ${total_cost:.4f}")
            return True
            
        except Exception as e:
            logger.error(f"Error tracking API usage for {service_name}: {e}")
            return False

    async def track_firecrawl_cost(
        self, 
        search_id: UUID, 
        pages_scraped: int, 
        user_id: Optional[UUID] = None
    ) -> float:
        """Track Firecrawl scraping costs."""
        try:
            cost_per_page = self.costs.firecrawl_per_scrape
            total_cost = pages_scraped * cost_per_page
            
            # Track in general API usage
            await self.track_api_usage(
                service_name="firecrawl",
                requests_count=pages_scraped,
                cost_per_request=cost_per_page,
                user_id=user_id,
                query_id=search_id
            )
            
            # Update cost table if database available
            if self.db:
                # Get or create cost record
                stmt = select(Cost).where(Cost.search_id == search_id)
                result = await self.db.execute(stmt)
                cost_record = result.scalar_one_or_none()
                
                if not cost_record:
                    cost_record = Cost(
                        search_id=search_id,
                        firecrawl_cost=total_cost,
                        apollo_cost=0.0,
                        stripe_fee=0.0
                    )
                    self.db.add(cost_record)
                else:
                    # Use SQL update to avoid type issues
                    current_cost = cost_record.firecrawl_cost if cost_record.firecrawl_cost is not None else 0.0
                    setattr(cost_record, 'firecrawl_cost', current_cost + total_cost)
                
                await self.db.commit()
            
            logger.info(f"Tracked Firecrawl cost: {pages_scraped} pages, ${total_cost:.4f}")
            return total_cost
            
        except Exception as e:
            logger.error(f"Error tracking Firecrawl cost: {e}")
            return 0.0

    async def track_apollo_cost(
        self, 
        search_id: UUID, 
        contacts_enriched: int, 
        user_id: Optional[UUID] = None
    ) -> float:
        """Track Apollo.io enrichment costs."""
        try:
            cost_per_contact = self.costs.apollo_per_contact
            total_cost = contacts_enriched * cost_per_contact
            
            # Track in general API usage
            await self.track_api_usage(
                service_name="apollo",
                requests_count=contacts_enriched,
                cost_per_request=cost_per_contact,
                user_id=user_id,
                query_id=search_id
            )
            
            # Update cost table if database available
            if self.db:
                # Get or create cost record
                stmt = select(Cost).where(Cost.search_id == search_id)
                result = await self.db.execute(stmt)
                cost_record = result.scalar_one_or_none()
                
                if not cost_record:
                    cost_record = Cost(
                        search_id=search_id,
                        firecrawl_cost=0.0,
                        apollo_cost=total_cost,
                        stripe_fee=0.0
                    )
                    self.db.add(cost_record)
                else:
                    cost_record.apollo_cost += total_cost
                
                await self.db.commit()
            
            logger.info(f"Tracked Apollo cost: {contacts_enriched} contacts, ${total_cost:.4f}")
            return total_cost
            
        except Exception as e:
            logger.error(f"Error tracking Apollo cost: {e}")
            return 0.0

    async def track_stripe_fee(
        self, 
        search_id: UUID, 
        payment_amount: float, 
        user_id: Optional[UUID] = None
    ) -> float:
        """Track Stripe processing fees."""
        try:
            # Stripe fees: 2.9% + $0.30 per transaction
            stripe_fee = (payment_amount * 0.029) + 0.30
            
            # Track in general API usage
            await self.track_api_usage(
                service_name="stripe",
                requests_count=1,
                cost_per_request=stripe_fee,
                user_id=user_id,
                query_id=search_id
            )
            
            # Update cost table if database available
            if self.db:
                # Get or create cost record
                stmt = select(Cost).where(Cost.search_id == search_id)
                result = await self.db.execute(stmt)
                cost_record = result.scalar_one_or_none()
                
                if not cost_record:
                    cost_record = Cost(
                        search_id=search_id,
                        firecrawl_cost=0.0,
                        apollo_cost=0.0,
                        stripe_fee=stripe_fee
                    )
                    self.db.add(cost_record)
                else:
                    cost_record.stripe_fee += stripe_fee
                
                await self.db.commit()
            
            logger.info(f"Tracked Stripe fee: ${payment_amount:.2f} payment, ${stripe_fee:.4f} fee")
            return stripe_fee
            
        except Exception as e:
            logger.error(f"Error tracking Stripe fee: {e}")
            return 0.0

    async def get_search_cost_breakdown(self, search_id: UUID) -> Dict[str, Any]:
        """Get detailed cost breakdown for a specific search."""
        try:
            if not self.db:
                return await self.get_cost_breakdown(search_id)
            
            # Get cost record from database
            stmt = select(Cost).where(Cost.search_id == search_id)
            result = await self.db.execute(stmt)
            cost_record = result.scalar_one_or_none()
            
            # Get session costs for additional services
            session_breakdown = await self.get_cost_breakdown(search_id)
            
            breakdown = {
                'search_id': str(search_id),
                'firecrawl': {
                    'cost': cost_record.firecrawl_cost if cost_record else 0.0,
                    'description': 'Web page scraping and content extraction'
                },
                'apollo': {
                    'cost': cost_record.apollo_cost if cost_record else 0.0,
                    'description': 'Contact enrichment and verification'
                },
                'stripe': {
                    'cost': cost_record.stripe_fee if cost_record else 0.0,
                    'description': 'Payment processing fee'
                },
                'total_cost': 0.0
            }
            
            # Add session costs (legacy services)
            for service, data in session_breakdown.items():
                if service not in breakdown:
                    breakdown[service] = {
                        'cost': data['cost'],
                        'requests': data['requests'],
                        'cost_per_request': data['cost_per_request']
                    }
            
            # Calculate total
            breakdown['total_cost'] = sum(
                item['cost'] for item in breakdown.values() 
                if isinstance(item, dict) and 'cost' in item
            )
            breakdown['total_cost'] = round(breakdown['total_cost'], 4)
            
            return breakdown
            
        except Exception as e:
            logger.error(f"Error getting search cost breakdown: {e}")
            return {}
    
    async def calculate_total_cost(self, query_id: UUID) -> float:
        """Calculate total cost for a specific query."""
        session_key = str(query_id)
        
        if session_key not in self.current_session_costs:
            return 0.0
        
        total_cost = sum(
            usage['total_cost'] 
            for usage in self.current_session_costs[session_key]
        )
        
        return round(total_cost, 4)
    
    async def get_cost_breakdown(self, query_id: UUID) -> Dict[str, Any]:
        """Get detailed cost breakdown for a query."""
        session_key = str(query_id)
        
        if session_key not in self.current_session_costs:
            return {}
        
        breakdown = {}
        for usage in self.current_session_costs[session_key]:
            service = usage['service_name']
            if service not in breakdown:
                breakdown[service] = {
                    'requests': 0,
                    'cost': 0.0,
                    'cost_per_request': usage['cost_per_request']
                }
            
            breakdown[service]['requests'] += usage['requests_count']
            breakdown[service]['cost'] += usage['total_cost']
        
        # Round costs
        for service in breakdown:
            breakdown[service]['cost'] = round(breakdown[service]['cost'], 4)
        
        return breakdown
    
    async def get_user_usage_stats(
        self, 
        user_id: UUID, 
        days: int = 30
    ) -> Dict[str, Any]:
        """Get usage statistics for a user."""
        if not self.db:
            return {}
        
        try:
            since_date = datetime.utcnow() - timedelta(days=days)
            
            # Query usage data
            stmt = select(
                ApiUsage.service_name,
                func.sum(ApiUsage.requests_count).label('total_requests'),
                func.sum(ApiUsage.cost).label('total_cost'),
                func.count(ApiUsage.id).label('api_calls')
            ).where(
                ApiUsage.user_id == user_id,
                ApiUsage.timestamp >= since_date
            ).group_by(ApiUsage.service_name)
            
            result = await self.db.execute(stmt)
            usage_data = result.fetchall()
            
            stats = {
                'period_days': days,
                'total_cost': 0.0,
                'total_requests': 0,
                'total_api_calls': 0,
                'services': {}
            }
            
            for row in usage_data:
                service_name = row.service_name
                stats['services'][service_name] = {
                    'requests': row.total_requests,
                    'cost': round(float(row.total_cost), 4),
                    'api_calls': row.api_calls,
                    'avg_cost_per_call': round(float(row.total_cost) / row.api_calls, 4) if row.api_calls > 0 else 0
                }
                
                stats['total_cost'] += float(row.total_cost)
                stats['total_requests'] += row.total_requests
                stats['total_api_calls'] += row.api_calls
            
            stats['total_cost'] = round(stats['total_cost'], 4)
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting user usage stats: {e}")
            return {}
    
    async def get_service_costs(self) -> Dict[str, float]:
        """Get current service cost configuration."""
        return {
            'google_search': self.costs.google_search_per_request,
            'bing_search': self.costs.bing_search_per_request,
            'openai_gpt4': self.costs.openai_gpt4_per_1k_tokens,
            'openai_gpt35': self.costs.openai_gpt35_per_1k_tokens,
            'playwright_scraping': self.costs.playwright_per_page,
            'redis_operations': self.costs.redis_per_operation,
            'firecrawl_per_scrape': self.costs.firecrawl_per_scrape,
            'apollo_per_contact': self.costs.apollo_per_contact,
            'stripe_fee_percentage': 0.029, # Default for now, will be updated with actual settings
            'stripe_fee_flat': 0.30 # Default for now, will be updated with actual settings
        }
    
    async def estimate_search_cost(
        self, 
        engines: List[str], 
        max_pages: int,
        ai_processing: bool = True,
        scraping: bool = True
    ) -> Dict[str, Any]:
        """Estimate cost for a search operation."""
        estimate = {
            'search_engines': {},
            'scraping': 0.0,
            'ai_processing': 0.0,
            'total': 0.0
        }
        
        # Search engine costs
        for engine in engines:
            requests_per_engine = max_pages
            if engine == 'google':
                cost = requests_per_engine * self.costs.google_search_per_request
            elif engine == 'bing':
                cost = requests_per_engine * self.costs.bing_search_per_request
            else:  # duckduckgo is free
                cost = 0.0
            
            estimate['search_engines'][engine] = {
                'requests': requests_per_engine,
                'cost': round(cost, 4)
            }
            estimate['total'] += cost
        
        # Scraping costs (estimated)
        if scraping:
            estimated_pages = max_pages * len(engines) * 8  # Avg 8 results per page
            scraping_cost = estimated_pages * self.costs.playwright_per_page
            estimate['scraping'] = round(scraping_cost, 4)
            estimate['total'] += scraping_cost
        
        # AI processing costs (estimated)
        if ai_processing:
            estimated_tokens = estimated_pages * 1000  # Avg 1k tokens per page
            ai_cost = (estimated_tokens / 1000) * self.costs.openai_gpt4_per_1k_tokens
            estimate['ai_processing'] = round(ai_cost, 4)
            estimate['total'] += ai_cost
        
        estimate['total'] = round(estimate['total'], 4)
        
        return estimate
    
    async def check_user_limits(self, user_id: UUID) -> Dict[str, Any]:
        """Check if user is within their usage limits."""
        if not self.db:
            return {'within_limits': True, 'reason': 'No database connection'}
        
        try:
            # Get user's current month usage
            current_month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            
            stmt = select(
                func.sum(ApiUsage.cost).label('total_cost'),
                func.sum(ApiUsage.requests_count).label('total_requests')
            ).where(
                ApiUsage.user_id == user_id,
                ApiUsage.timestamp >= current_month
            )
            
            result = await self.db.execute(stmt)
            usage = result.fetchone()
            
            current_cost = float(usage.total_cost) if usage.total_cost else 0.0
            current_requests = usage.total_requests if usage.total_requests else 0
            
            # Check limits (these would come from user subscription tier)
            monthly_cost_limit = 100.0  # Default limit
            monthly_request_limit = 10000  # Default limit
            
            limits_check = {
                'within_limits': True,
                'current_cost': round(current_cost, 4),
                'cost_limit': monthly_cost_limit,
                'current_requests': current_requests,
                'request_limit': monthly_request_limit,
                'cost_percentage': round((current_cost / monthly_cost_limit) * 100, 2),
                'request_percentage': round((current_requests / monthly_request_limit) * 100, 2)
            }
            
            if current_cost >= monthly_cost_limit:
                limits_check['within_limits'] = False
                limits_check['reason'] = 'Monthly cost limit exceeded'
            elif current_requests >= monthly_request_limit:
                limits_check['within_limits'] = False
                limits_check['reason'] = 'Monthly request limit exceeded'
            
            return limits_check
            
        except Exception as e:
            logger.error(f"Error checking user limits: {e}")
            return {'within_limits': True, 'reason': f'Error checking limits: {e}'}
    
    async def generate_cost_report(
        self, 
        start_date: datetime, 
        end_date: datetime
    ) -> Dict[str, Any]:
        """Generate cost report for a date range."""
        if not self.db:
            return {}
        
        try:
            stmt = select(
                ApiUsage.service_name,
                func.date(ApiUsage.timestamp).label('date'),
                func.sum(ApiUsage.cost).label('daily_cost'),
                func.sum(ApiUsage.requests_count).label('daily_requests'),
                func.count(ApiUsage.id).label('daily_calls')
            ).where(
                ApiUsage.timestamp.between(start_date, end_date)
            ).group_by(
                ApiUsage.service_name,
                func.date(ApiUsage.timestamp)
            ).order_by(
                func.date(ApiUsage.timestamp).desc()
            )
            
            result = await self.db.execute(stmt)
            data = result.fetchall()
            
            report = {
                'period': {
                    'start': start_date.isoformat(),
                    'end': end_date.isoformat()
                },
                'summary': {
                    'total_cost': 0.0,
                    'total_requests': 0,
                    'total_calls': 0,
                    'services': {}
                },
                'daily_breakdown': {}
            }
            
            for row in data:
                date_str = row.date.isoformat()
                service = row.service_name
                
                # Update daily breakdown
                if date_str not in report['daily_breakdown']:
                    report['daily_breakdown'][date_str] = {}
                
                report['daily_breakdown'][date_str][service] = {
                    'cost': round(float(row.daily_cost), 4),
                    'requests': row.daily_requests,
                    'calls': row.daily_calls
                }
                
                # Update summary
                if service not in report['summary']['services']:
                    report['summary']['services'][service] = {
                        'cost': 0.0,
                        'requests': 0,
                        'calls': 0
                    }
                
                report['summary']['services'][service]['cost'] += float(row.daily_cost)
                report['summary']['services'][service]['requests'] += row.daily_requests
                report['summary']['services'][service]['calls'] += row.daily_calls
                
                report['summary']['total_cost'] += float(row.daily_cost)
                report['summary']['total_requests'] += row.daily_requests
                report['summary']['total_calls'] += row.daily_calls
            
            # Round summary costs
            report['summary']['total_cost'] = round(report['summary']['total_cost'], 4)
            for service in report['summary']['services']:
                report['summary']['services'][service]['cost'] = round(
                    report['summary']['services'][service]['cost'], 4
                )
            
            return report
            
        except Exception as e:
            logger.error(f"Error generating cost report: {e}")
            return {}
    
    def clear_session_costs(self, query_id: Optional[UUID] = None):
        """Clear session cost tracking."""
        if query_id:
            session_key = str(query_id)
            if session_key in self.current_session_costs:
                del self.current_session_costs[session_key]
        else:
            self.current_session_costs.clear()
        
        logger.debug(f"Cleared session costs for {query_id or 'all sessions'}") 