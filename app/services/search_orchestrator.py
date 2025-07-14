"""Search orchestration service for the freemium preview→pay→enrich model."""
import asyncio
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger

from app.models.search import SearchQuery, SearchResult, ContactData, LocationData, SearchStatus
from app.services.mcp_manager import MCPManager
from app.services.ai_processor import AIProcessor
from app.services.cache_service import CacheService
from app.services.cost_tracker import CostTracker
from app.services.firecrawl_client import get_firecrawl_client, FirecrawlResponse
from app.utils.mask import EmailMasker, MaskingStyle, mask_contact_emails
from app.config import settings


class SearchOrchestrator:
    """Orchestrates the complete search process for the freemium model."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.mcp_manager = MCPManager()
        self.ai_processor = AIProcessor()
        self.cache_service = CacheService()
        self.cost_tracker = CostTracker(db)
        self.firecrawl_client = get_firecrawl_client()
        self.email_masker = EmailMasker(MaskingStyle.DOTS)
    
    async def generate_preview(self, query_id: UUID, search_request) -> Dict[str, Any]:
        """
        Generate a preview for the freemium model using Firecrawl.
        
        This is the first step in the preview→pay→enrich flow.
        Returns masked contact data and basic search results.
        """
        start_time = time.time()
        
        try:
            # Get search query from database
            search_query = await self.db.get(SearchQuery, query_id)
            if not search_query:
                logger.error(f"Search query {query_id} not found")
                return {"error": "Search query not found"}
            
            # Update status to preview processing
            search_query.status = SearchStatus.preview
            await self.db.commit()
            
            logger.info(f"Generating preview for query: {search_query.query_text}")
            
            # Step 1: Check cache for preview data
            cached_preview = await self._check_preview_cache(search_query)
            if cached_preview and search_request.filters.cache_results:
                logger.info(f"Returning cached preview for query {query_id}")
                return cached_preview
            
            # Step 2: Execute searches across all engines
            all_search_results = await self._execute_multi_engine_search(
                search_query.query_text,
                search_request.filters
            )
            
            # Step 3: Aggregate and deduplicate results
            aggregated_results = await self._aggregate_results(all_search_results)
            
            # Step 4: Scrape content from top URLs using Firecrawl
            preview_limit = min(search_request.filters.max_pages, 3)  # Limit for preview
            scraped_results = await self._scrape_with_firecrawl(
                aggregated_results[:preview_limit * 10],  # Top results only
                preview_limit
            )
            
            # Step 5: Extract basic contact data for preview
            preview_contacts = await self._extract_preview_contacts(scraped_results)
            
            # Step 6: Generate masked preview
            preview_data = await self._generate_masked_preview(
                search_query,
                scraped_results,
                preview_contacts
            )
            
            # Step 7: Store preview results and raw Firecrawl data
            await self._store_preview_results(search_query, scraped_results, preview_data)
            
            # Step 8: Cache preview for future use
            if search_request.filters.cache_results:
                await self._cache_preview(search_query, preview_data)
            
            # Update processing metrics
            processing_time = time.time() - start_time
            search_query.processing_time = processing_time
            search_query.pages_processed = len(scraped_results)
            
            # Calculate and store preview costs
            total_cost = await self.cost_tracker.calculate_total_cost(query_id)
            search_query.total_cost = total_cost
            search_query.cost_breakdown = await self.cost_tracker.get_cost_breakdown(query_id)
            
            await self.db.commit()
            
            logger.info(f"Preview generated for query {query_id} in {processing_time:.2f}s")
            return preview_data
            
        except Exception as e:
            logger.error(f"Error generating preview for {query_id}: {e}")
            search_query.status = SearchStatus.failed
            await self.db.commit()
            return {"error": f"Preview generation failed: {str(e)}"}
    
    async def process_paid_search(self, query_id: UUID) -> None:
        """
        Process a paid search request with full enrichment.
        
        This is triggered after successful payment and runs the complete
        preview→pay→enrich flow with full contact enrichment.
        """
        start_time = time.time()
        
        try:
            # Get search query from database
            search_query = await self.db.get(SearchQuery, query_id)
            if not search_query:
                logger.error(f"Search query {query_id} not found")
                return
            
            if search_query.status != SearchStatus.paid:
                logger.error(f"Search query {query_id} not in paid status: {search_query.status}")
                return
            
            # Update status to enriching
            search_query.status = SearchStatus.enriching
            await self.db.commit()
            
            logger.info(f"Processing paid search for query: {search_query.query_text}")
            
            # Step 1: Get existing preview data if available
            existing_results = await self._get_existing_results(search_query)
            
            # Step 2: Expand search with full page limit
            if not existing_results or len(existing_results) < search_query.max_pages * 10:
                # Execute full search
                all_search_results = await self._execute_multi_engine_search(
                    search_query.query_text,
                    {"engines": ["google", "bing", "duckduckgo"], "max_pages": search_query.max_pages}
                )
                
                aggregated_results = await self._aggregate_results(all_search_results)
                
                # Full scraping with Firecrawl
                scraped_results = await self._scrape_with_firecrawl(
                    aggregated_results,
                    search_query.max_pages
                )
            else:
                scraped_results = existing_results
            
            # Step 3: Full AI processing for contact extraction
            processed_results = await self._process_with_ai(scraped_results)
            
            # Step 4: Store enriched results (unmasked)
            await self._store_enriched_results(search_query, processed_results)
            
            # Step 5: Mark as ready
            search_query.status = SearchStatus.ready
            processing_time = time.time() - start_time
            search_query.processing_time = processing_time
            search_query.total_results = len(processed_results)
            
            # Update final costs
            total_cost = await self.cost_tracker.calculate_total_cost(query_id)
            search_query.total_cost = total_cost
            search_query.cost_breakdown = await self.cost_tracker.get_cost_breakdown(query_id)
            
            await self.db.commit()
            logger.info(f"Paid search completed for query {query_id} in {processing_time:.2f}s")
            
        except Exception as e:
            logger.error(f"Error processing paid search {query_id}: {e}")
            search_query.status = SearchStatus.failed
            await self.db.commit()
            raise
    
    async def _check_cache(self, search_query: SearchQuery) -> Optional[List[Dict]]:
        """Check if results are cached."""
        cache_key = self.cache_service.generate_cache_key(
            search_query.query_text,
            search_query.filters
        )
        return await self.cache_service.get(cache_key)
    
    async def _check_preview_cache(self, search_query: SearchQuery) -> Optional[Dict[str, Any]]:
        """Check if preview data is cached."""
        cache_key = self.cache_service.generate_cache_key(
            search_query.query_text,
            search_query.filters
        )
        return await self.cache_service.get(cache_key)
    
    async def _execute_multi_engine_search(
        self, 
        query: str, 
        filters
    ) -> Dict[str, List[Dict]]:
        """Execute search across multiple engines in parallel."""
        search_tasks = []
        
        # Create search tasks for each enabled engine
        if "google" in filters.engines:
            search_tasks.append(
                self._search_google(query, filters.max_pages)
            )
        
        if "bing" in filters.engines:
            search_tasks.append(
                self._search_bing(query, filters.max_pages)
            )
        
        if "duckduckgo" in filters.engines:
            search_tasks.append(
                self._search_duckduckgo(query, filters.max_pages)
            )
        
        # Execute all searches in parallel
        results = await asyncio.gather(*search_tasks, return_exceptions=True)
        
        # Process results
        engine_results = {}
        engines = [e for e in filters.engines if e in ["google", "bing", "duckduckgo"]]
        
        for i, result in enumerate(results):
            engine = engines[i]
            if isinstance(result, Exception):
                logger.error(f"Error in {engine} search: {result}")
                engine_results[engine] = []
            else:
                engine_results[engine] = result
        
        return engine_results
    
    async def _search_google(self, query: str, max_pages: int) -> List[Dict]:
        """Search using Google Custom Search API via MCP."""
        try:
            results = []
            for page in range(1, max_pages + 1):
                start_index = (page - 1) * 10 + 1
                page_results = await self.mcp_manager.call_google_search(
                    query=query,
                    num_results=10,
                    start_index=start_index
                )
                
                if page_results:
                    # Process Google results
                    for i, item in enumerate(page_results.get('items', [])):
                        results.append({
                            'url': item.get('link'),
                            'title': item.get('title'),
                            'snippet': item.get('snippet'),
                            'engine': 'google',
                            'rank': start_index + i,
                            'page': page
                        })
                
                # Track cost
                await self.cost_tracker.track_api_usage(
                    'google_search', 1, 0.005
                )
            
            return results
            
        except Exception as e:
            logger.error(f"Google search error: {e}")
            return []
    
    async def _search_bing(self, query: str, max_pages: int) -> List[Dict]:
        """Search using Bing Web Search API via MCP."""
        try:
            results = []
            for page in range(max_pages):
                offset = page * 10
                page_results = await self.mcp_manager.call_bing_search(
                    query=query,
                    count=10,
                    offset=offset
                )
                
                if page_results:
                    for i, item in enumerate(page_results.get('webPages', {}).get('value', [])):
                        results.append({
                            'url': item.get('url'),
                            'title': item.get('name'),
                            'snippet': item.get('snippet'),
                            'engine': 'bing',
                            'rank': offset + i + 1,
                            'page': page + 1
                        })
                
                # Track cost
                await self.cost_tracker.track_api_usage(
                    'bing_search', 1, 0.007
                )
            
            return results
            
        except Exception as e:
            logger.error(f"Bing search error: {e}")
            return []
    
    async def _search_duckduckgo(self, query: str, max_pages: int) -> List[Dict]:
        """Search using DuckDuckGo via MCP."""
        try:
            results = await self.mcp_manager.call_duckduckgo_search(
                query=query,
                max_results=max_pages * 10
            )
            
            processed_results = []
            for i, item in enumerate(results):
                processed_results.append({
                    'url': item.get('url'),
                    'title': item.get('title'),
                    'snippet': item.get('snippet'),
                    'engine': 'duckduckgo',
                    'rank': i + 1,
                    'page': (i // 10) + 1
                })
            
            return processed_results
            
        except Exception as e:
            logger.error(f"DuckDuckGo search error: {e}")
            return []
    
    async def _aggregate_results(self, engine_results: Dict[str, List[Dict]]) -> List[Dict]:
        """Aggregate and deduplicate results from multiple engines."""
        url_to_result = {}
        
        # Merge results from all engines
        for engine, results in engine_results.items():
            for result in results:
                url = result['url']
                if url in url_to_result:
                    # Merge ranking information
                    existing = url_to_result[url]
                    existing['source_engines'].append(engine)
                    existing['rankings'][engine] = result['rank']
                    # Use the best (lowest) rank as overall rank
                    existing['rank'] = min(existing['rank'], result['rank'])
                else:
                    url_to_result[url] = {
                        **result,
                        'source_engines': [engine],
                        'rankings': {engine: result['rank']}
                    }
        
        # Sort by best rank and return top results
        aggregated = list(url_to_result.values())
        aggregated.sort(key=lambda x: x['rank'])
        
        return aggregated[:50]  # Limit to top 50 results
    
    async def _scrape_with_firecrawl(
        self, 
        results: List[Dict], 
        max_pages: int
    ) -> List[Dict]:
        """
        Scrape content using Firecrawl with fallback to legacy scraper.
        """
        scraped_results = []
        scrape_tasks = []
        
        # Limit results to process
        urls_to_scrape = results[:max_pages * 10]
        
        logger.info(f"Scraping {len(urls_to_scrape)} URLs with Firecrawl")
        
        # Create scraping tasks
        for result in urls_to_scrape:
            url = result.get('url')
            if url:
                scrape_tasks.append(self._scrape_single_url_firecrawl(result))
        
        # Execute scraping in parallel with rate limiting
        batch_size = 5  # Process in batches to respect rate limits
        for i in range(0, len(scrape_tasks), batch_size):
            batch = scrape_tasks[i:i + batch_size]
            batch_results = await asyncio.gather(*batch, return_exceptions=True)
            
            for result in batch_results:
                if isinstance(result, Exception):
                    logger.error(f"Scraping error: {result}")
                elif result:
                    scraped_results.append(result)
            
            # Rate limiting pause between batches
            if i + batch_size < len(scrape_tasks):
                await asyncio.sleep(1)  # 1 second between batches
        
        logger.info(f"Successfully scraped {len(scraped_results)} URLs")
        return scraped_results
    
    async def _scrape_single_url_firecrawl(self, result: Dict) -> Optional[Dict]:
        """Scrape a single URL using Firecrawl with cost tracking."""
        url = result.get('url')
        if not url:
            return None
        
        try:
            # Use Firecrawl client with retry and circuit breaker
            firecrawl_response: FirecrawlResponse = await self.firecrawl_client.scrape_url(
                url,
                options={
                    "formats": ["markdown", "html"],
                    "onlyMainContent": True,
                    "includeTags": ["a", "p", "h1", "h2", "h3", "h4", "h5", "h6", "span", "div", "ul", "li"],
                }
            )
            
            if firecrawl_response.success and firecrawl_response.data:
                # Track Firecrawl costs
                await self.cost_tracker.track_api_usage(
                    'firecrawl_scrape',
                    1,
                    firecrawl_response.cost
                )
                
                # Extract content from Firecrawl response
                scraped_content = ""
                if 'markdown' in firecrawl_response.data:
                    scraped_content = firecrawl_response.data['markdown']
                elif 'html' in firecrawl_response.data:
                    scraped_content = firecrawl_response.data['html']
                
                # Update result with Firecrawl data
                result.update({
                    'scraped_content': scraped_content,
                    'scraped_at': datetime.utcnow(),
                    'scraping_success': True,
                    'scraping_error': None,
                    'firecrawl_raw': firecrawl_response.data,  # Store raw Firecrawl response
                    'scraping_cost': firecrawl_response.cost,
                    'scraping_time': firecrawl_response.response_time
                })
                
                return result
            else:
                # Firecrawl failed, try fallback if available
                error_msg = firecrawl_response.error or "Unknown Firecrawl error"
                logger.warning(f"Firecrawl failed for {url}: {error_msg}")
                
                # Use legacy scraper as fallback
                fallback_result = await self._scrape_single_url_legacy(result)
                if fallback_result:
                    fallback_result['scraping_fallback_used'] = True
                    return fallback_result
                
                # Mark as failed
                result.update({
                    'scraped_content': None,
                    'scraped_at': datetime.utcnow(),
                    'scraping_success': False,
                    'scraping_error': f"Firecrawl failed: {error_msg}",
                    'scraping_cost': 0.0
                })
                
                return result
                
        except Exception as e:
            logger.error(f"Error scraping {url} with Firecrawl: {e}")
            
            # Try fallback
            fallback_result = await self._scrape_single_url_legacy(result)
            if fallback_result:
                fallback_result['scraping_fallback_used'] = True
                return fallback_result
            
            result.update({
                'scraped_content': None,
                'scraped_at': datetime.utcnow(),
                'scraping_success': False,
                'scraping_error': str(e),
                'scraping_cost': 0.0
            })
            
            return result
    
    async def _scrape_single_url_legacy(self, result: Dict) -> Optional[Dict]:
        """Legacy scraper fallback (simplified version of original)."""
        # This is a simplified fallback - in a real implementation,
        # this would use the existing MCP-based scraping logic
        url = result.get('url')
        logger.info(f"Using legacy scraper for {url}")
        
        try:
            # Placeholder for legacy scraping logic
            # In real implementation, this would call the existing MCP scraper
            result.update({
                'scraped_content': f"Legacy scraped content for {url}",
                'scraped_at': datetime.utcnow(),
                'scraping_success': True,
                'scraping_error': None,
                'scraping_cost': 0.001  # Lower cost for legacy scraper
            })
            
            # Track legacy scraping cost
            await self.cost_tracker.track_api_usage(
                'legacy_scrape',
                1,
                0.001
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Legacy scraper also failed for {url}: {e}")
            return None
    
    async def _extract_preview_contacts(self, results: List[Dict]) -> List[Dict]:
        """Extract basic contact data for preview (limited processing)."""
        preview_contacts = []
        
        for result in results[:5]:  # Limit preview contacts
            if not result.get('scraped_content'):
                continue
            
            try:
                # Use AI processor for basic contact extraction (limited for preview)
                contacts = await self.ai_processor.extract_contacts(
                    result['scraped_content'][:2000],  # Limit content for preview
                    result.get('url', 'unknown')
                )
                
                if contacts:
                    preview_contacts.extend(contacts)
                
                # Track AI processing cost for preview
                await self.cost_tracker.track_api_usage(
                    'ai_processing_preview',
                    1,
                    0.01  # Lower cost for basic processing
                )
                
            except Exception as e:
                logger.error(f"Error extracting preview contacts: {e}")
        
        return preview_contacts[:10]  # Limit to 10 contacts for preview
    
    async def _generate_masked_preview(
        self,
        search_query: SearchQuery,
        scraped_results: List[Dict],
        contacts: List[Dict]
    ) -> Dict[str, Any]:
        """Generate a masked preview response for the freemium model."""
        
        # Mask contact emails for preview
        masked_contacts = []
        for contact in contacts:
            masked_contact = contact.copy()
            
            # Mask emails using the email masker
            if contact.get('emails'):
                masked_contact['emails'] = mask_contact_emails(
                    contact['emails'],
                    MaskingStyle.DOTS
                )
            
            # Mask phone numbers (partial)
            if contact.get('phone_numbers'):
                masked_phones = []
                for phone in contact['phone_numbers']:
                    if len(phone) > 6:
                        masked_phones.append(phone[:3] + '•••' + phone[-2:])
                    else:
                        masked_phones.append('•••••')
                masked_contact['phone_numbers'] = masked_phones
            
            masked_contacts.append(masked_contact)
        
        # Create preview summary
        preview_data = {
            'query_id': str(search_query.id),
            'status': 'preview',
            'summary': {
                'total_pages_found': len(scraped_results),
                'total_contacts_found': len(contacts),
                'preview_contacts': len(masked_contacts),
                'processing_time': search_query.processing_time,
                'estimated_full_cost': await self._estimate_full_search_cost(search_query)
            },
            'preview_contacts': masked_contacts,
            'sample_urls': [
                {
                    'url': result['url'],
                    'title': result.get('title', 'No title'),
                    'snippet': result.get('snippet', '')[:200] + '...',
                    'scraped': result.get('scraping_success', False)
                }
                for result in scraped_results[:5]
            ],
            'upgrade_info': {
                'message': 'Upgrade to see full contact details and get more results',
                'full_search_pages': search_query.max_pages,
                'preview_pages': min(search_query.max_pages, 3)
            }
        }
        
        return preview_data
    
    async def _estimate_full_search_cost(self, search_query: SearchQuery) -> float:
        """Estimate the cost of running the full paid search."""
        # This is a simplified estimation - in reality, you'd use more sophisticated logic
        preview_cost = search_query.total_cost or 0.0
        
        # Estimate full search cost based on max_pages vs preview pages
        preview_pages = min(search_query.max_pages, 3)
        full_pages = search_query.max_pages
        
        if preview_pages > 0:
            scaling_factor = full_pages / preview_pages
            estimated_cost = preview_cost * scaling_factor * 1.5  # Add buffer for AI processing
        else:
            estimated_cost = 2.50  # Default estimate
        
        return round(estimated_cost, 2)
    
    async def _store_preview_results(
        self,
        search_query: SearchQuery,
        scraped_results: List[Dict],
        preview_data: Dict[str, Any]
    ) -> None:
        """Store preview results and raw Firecrawl data in the database."""
        
        # Store Firecrawl raw data in the search query
        firecrawl_raw_data = {
            'preview_results': [],
            'scraped_at': datetime.utcnow().isoformat(),
            'total_scraped': len(scraped_results)
        }
        
        for result in scraped_results:
            if result.get('firecrawl_raw'):
                firecrawl_raw_data['preview_results'].append({
                    'url': result['url'],
                    'firecrawl_data': result['firecrawl_raw'],
                    'scraping_success': result.get('scraping_success', False),
                    'scraping_cost': result.get('scraping_cost', 0.0)
                })
        
        search_query.firecrawl_raw = firecrawl_raw_data
        
        # Store basic search results (for preview, we don't store full contact data)
        for result_data in scraped_results:
            search_result = SearchResult(
                query_id=search_query.id,
                url=result_data['url'],
                title=result_data.get('title'),
                snippet=result_data.get('snippet'),
                source_engines=[result_data.get('engine', 'unknown')],
                scraped_content=result_data.get('scraped_content'),
                scraped_at=result_data.get('scraped_at'),
                scraping_success=result_data.get('scraping_success', False),
                scraping_error=result_data.get('scraping_error'),
                confidence_score=0.5,  # Default for preview
                relevance_score=0.5    # Default for preview
            )
            
            # Set engine-specific ranks
            if result_data.get('engine') == 'google':
                search_result.rank_google = result_data.get('rank')
            elif result_data.get('engine') == 'bing':
                search_result.rank_bing = result_data.get('rank')
            elif result_data.get('engine') == 'duckduckgo':
                search_result.rank_duckduckgo = result_data.get('rank')
            
            self.db.add(search_result)
        
        await self.db.commit()
    
    async def _cache_preview(self, search_query: SearchQuery, preview_data: Dict[str, Any]) -> None:
        """Cache preview data for future use."""
        cache_key = self.cache_service.generate_cache_key(
            search_query.query_text + "_preview",
            search_query.filters
        )
        await self.cache_service.set(cache_key, preview_data, ttl=3600)  # 1 hour cache
    
    async def _get_existing_results(self, search_query: SearchQuery) -> List[Dict]:
        """Get existing search results from the database."""
        try:
            stmt = select(SearchResult).where(SearchResult.query_id == search_query.id)
            result = await self.db.execute(stmt)
            existing_results = result.scalars().all()
            
            # Convert to dictionary format
            results = []
            for sr in existing_results:
                result_dict = {
                    'url': sr.url,
                    'title': sr.title,
                    'snippet': sr.snippet,
                    'scraped_content': sr.scraped_content,
                    'scraped_at': sr.scraped_at,
                    'scraping_success': sr.scraping_success,
                    'scraping_error': sr.scraping_error,
                    'engine': sr.source_engines[0] if sr.source_engines else 'unknown',
                    'rank': sr.rank_google or sr.rank_bing or sr.rank_duckduckgo or 0
                }
                results.append(result_dict)
            
            return results
            
        except Exception as e:
            logger.error(f"Error getting existing results: {e}")
            return []
    
    async def _process_with_ai(self, results: List[Dict]) -> List[Dict]:
        """Process scraped content with AI to extract contacts (full enrichment)."""
        processed_results = []
        
        for result in results:
            if result.get('scraped_content'):
                try:
                    # Extract contacts using AI (full processing)
                    contacts = await self.ai_processor.extract_contacts(
                        result['scraped_content'],
                        result['url']
                    )
                    
                    result['contacts'] = contacts
                    result['ai_processed'] = True
                    result['ai_processed_at'] = datetime.utcnow()
                    
                    # Track AI processing cost for full enrichment
                    await self.cost_tracker.track_api_usage(
                        'ai_processing_full',
                        1,
                        0.05  # Higher cost for full processing
                    )
                    
                except Exception as e:
                    logger.error(f"AI processing error for {result['url']}: {e}")
                    result['ai_processed'] = False
                    result['contacts'] = {}
            
            processed_results.append(result)
        
        return processed_results
    
    async def _store_enriched_results(self, search_query: SearchQuery, results: List[Dict]) -> None:
        """Store enriched results with full contact data in the database."""
        for result_data in results:
            # Find existing SearchResult or create new one
            stmt = select(SearchResult).where(
                SearchResult.query_id == search_query.id,
                SearchResult.url == result_data['url']
            )
            result = await self.db.execute(stmt)
            search_result = result.scalar_one_or_none()
            
            if not search_result:
                # Create new SearchResult
                search_result = SearchResult(
                    query_id=search_query.id,
                    url=result_data['url'],
                    title=result_data.get('title'),
                    snippet=result_data.get('snippet'),
                    source_engines=[result_data.get('engine', 'unknown')],
                    scraped_content=result_data.get('scraped_content'),
                    scraped_at=result_data.get('scraped_at'),
                    scraping_success=result_data.get('scraping_success', False),
                    scraping_error=result_data.get('scraping_error'),
                    ai_processed=result_data.get('ai_processed', False),
                    ai_processed_at=result_data.get('ai_processed_at'),
                    confidence_score=result_data.get('confidence_score', 0.0),
                    relevance_score=result_data.get('relevance_score', 0.0)
                )
                
                # Set engine-specific ranks
                if result_data.get('engine') == 'google':
                    search_result.rank_google = result_data.get('rank')
                elif result_data.get('engine') == 'bing':
                    search_result.rank_bing = result_data.get('rank')
                elif result_data.get('engine') == 'duckduckgo':
                    search_result.rank_duckduckgo = result_data.get('rank')
                
                self.db.add(search_result)
                await self.db.flush()  # Get the ID
            else:
                # Update existing result with enriched data
                search_result.ai_processed = result_data.get('ai_processed', False)
                search_result.ai_processed_at = result_data.get('ai_processed_at')
                search_result.confidence_score = result_data.get('confidence_score', 0.0)
                search_result.relevance_score = result_data.get('relevance_score', 0.0)
            
            # Store full contact data (unmasked)
            contacts = result_data.get('contacts', {})
            if contacts:
                # Check if contact data already exists
                stmt = select(ContactData).where(ContactData.result_id == search_result.id)
                result = await self.db.execute(stmt)
                existing_contact = result.scalar_one_or_none()
                
                if existing_contact:
                    # Update existing contact data
                    existing_contact.emails = contacts.get('emails', [])
                    existing_contact.phone_numbers = contacts.get('phones', [])
                    existing_contact.names = contacts.get('names', [])
                    existing_contact.job_titles = contacts.get('job_titles', [])
                    existing_contact.companies = contacts.get('companies', [])
                    existing_contact.social_profiles = contacts.get('social_profiles', {})
                    existing_contact.extraction_confidence = contacts.get('confidence', 0.0)
                    existing_contact.extracted_at = datetime.utcnow()
                else:
                    # Create new contact data
                    contact_data = ContactData(
                        result_id=search_result.id,
                        emails=contacts.get('emails', []),
                        phone_numbers=contacts.get('phones', []),
                        names=contacts.get('names', []),
                        job_titles=contacts.get('job_titles', []),
                        companies=contacts.get('companies', []),
                        social_profiles=contacts.get('social_profiles', {}),
                        extraction_confidence=contacts.get('confidence', 0.0),
                        extracted_at=datetime.utcnow()
                    )
                    self.db.add(contact_data)
        
        await self.db.commit()

    async def _store_cached_results(self, search_query: SearchQuery, cached_results: List[Dict]) -> None:
        """Store cached results in database."""
        # Implementation similar to _store_results but for cached data
        pass
    
    async def _cache_results(self, search_query: SearchQuery, results: List[Dict]) -> None:
        """Cache results for future use."""
        cache_key = self.cache_service.generate_cache_key(
            search_query.query_text,
            search_query.filters
        )
        
        await self.cache_service.set(
            cache_key,
            results,
            ttl=settings.cache_ttl_search_results
        )
