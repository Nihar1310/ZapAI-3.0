"""Apollo.io API client for contact enrichment."""
import asyncio
import logging
from typing import List, Dict, Any, Optional
import aiohttp
import time
from app.config import get_settings

logger = logging.getLogger(__name__)


class ApolloClient:
    """Apollo.io API client for contact enrichment."""
    
    def __init__(self):
        self.settings = get_settings()
        self.api_key = self.settings.apollo_api_key
        self.base_url = self.settings.apollo_base_url
        self.max_contacts_per_request = self.settings.apollo_max_contacts_per_request
        self.timeout = self.settings.apollo_timeout
        self.max_retries = self.settings.apollo_max_retries
        self.rate_limit_per_minute = self.settings.apollo_rate_limit_per_minute
        
        # Rate limiting
        self._request_times = []
        self._last_request_time = 0
        
        # Circuit breaker
        self._consecutive_failures = 0
        self._circuit_open_until = 0
        self._max_failures = 5
        self._circuit_timeout = 300  # 5 minutes
        
    async def _check_rate_limit(self):
        """Check and enforce rate limiting."""
        current_time = time.time()
        
        # Remove requests older than 1 minute
        cutoff_time = current_time - 60
        self._request_times = [t for t in self._request_times if t > cutoff_time]
        
        # Check if we've exceeded rate limit
        if len(self._request_times) >= self.rate_limit_per_minute:
            sleep_time = 60 - (current_time - self._request_times[0])
            if sleep_time > 0:
                logger.warning(f"Rate limit reached, sleeping for {sleep_time:.2f} seconds")
                await asyncio.sleep(sleep_time)
        
        self._request_times.append(current_time)
        
    def _check_circuit_breaker(self):
        """Check if circuit breaker is open."""
        if self._circuit_open_until > time.time():
            raise Exception(f"Apollo circuit breaker is open until {self._circuit_open_until}")
            
    def _record_success(self):
        """Record successful API call."""
        self._consecutive_failures = 0
        
    def _record_failure(self):
        """Record failed API call and potentially open circuit breaker."""
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._max_failures:
            self._circuit_open_until = time.time() + self._circuit_timeout
            logger.error(f"Apollo circuit breaker opened due to {self._consecutive_failures} failures")
            
    async def _make_request(
        self, 
        endpoint: str, 
        method: str = "GET", 
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make HTTP request to Apollo API with retry logic."""
        if not self.api_key:
            raise ValueError("Apollo API key not configured")
            
        self._check_circuit_breaker()
        await self._check_rate_limit()
        
        headers = {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "X-Api-Key": self.api_key
        }
        
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        for attempt in range(self.max_retries + 1):
            try:
                timeout = aiohttp.ClientTimeout(total=self.timeout)
                async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                    if method.upper() == "POST":
                        async with session.post(url, json=data, params=params) as response:
                            result = await self._handle_response(response)
                            self._record_success()
                            return result
                    else:
                        async with session.get(url, params=params) as response:
                            result = await self._handle_response(response)
                            self._record_success()
                            return result
                            
            except Exception as e:
                logger.warning(f"Apollo API request failed (attempt {attempt + 1}): {str(e)}")
                if attempt == self.max_retries:
                    self._record_failure()
                    raise
                    
                # Exponential backoff
                wait_time = (2 ** attempt) + (asyncio.get_event_loop().time() % 1)
                await asyncio.sleep(wait_time)
        
        # This should never be reached due to the raise in the loop
        raise Exception("Max retries exceeded")
                
    async def _handle_response(self, response: aiohttp.ClientResponse) -> Dict[str, Any]:
        """Handle Apollo API response."""
        if response.status == 200:
            return await response.json()
        elif response.status == 429:
            # Rate limited
            retry_after = response.headers.get('Retry-After', '60')
            raise Exception(f"Apollo rate limited, retry after {retry_after} seconds")
        elif response.status == 401:
            raise Exception("Apollo API authentication failed - check API key")
        elif response.status == 403:
            raise Exception("Apollo API access forbidden - check API permissions")
        else:
            error_text = await response.text()
            raise Exception(f"Apollo API error {response.status}: {error_text}")
            
    async def enrich_contacts(self, contacts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Enrich contacts using Apollo.io API.
        
        Args:
            contacts: List of contact dictionaries with email/name/company info
            
        Returns:
            List of enriched contact dictionaries
        """
        if not contacts:
            return []
            
        # Limit batch size
        if len(contacts) > self.max_contacts_per_request:
            logger.warning(f"Contact batch size {len(contacts)} exceeds limit {self.max_contacts_per_request}")
            contacts = contacts[:self.max_contacts_per_request]
            
        logger.info(f"Enriching {len(contacts)} contacts with Apollo")
        
        try:
            # Prepare Apollo API request
            enrichment_data = {
                "api_key": self.api_key,
                "contacts": []
            }
            
            for contact in contacts:
                contact_data = {}
                
                # Add email if available
                if contact.get("email"):
                    contact_data["email"] = contact["email"]
                    
                # Add name if available
                if contact.get("name"):
                    contact_data["name"] = contact["name"]
                    
                # Add company if available
                if contact.get("company"):
                    contact_data["organization_name"] = contact["company"]
                    
                if contact_data:
                    enrichment_data["contacts"].append(contact_data)
                    
            if not enrichment_data["contacts"]:
                logger.warning("No valid contacts to enrich")
                return []
                
            # Make API request
            response = await self._make_request(
                "contacts/enrich",
                method="POST",
                data=enrichment_data
            )
            
            # Process response
            enriched_contacts = []
            if response.get("contacts"):
                for contact in response["contacts"]:
                    enriched_contact = self._process_enriched_contact(contact)
                    if enriched_contact:
                        enriched_contacts.append(enriched_contact)
                        
            logger.info(f"Successfully enriched {len(enriched_contacts)} contacts")
            return enriched_contacts
            
        except Exception as e:
            logger.error(f"Failed to enrich contacts with Apollo: {str(e)}")
            # Return original contacts as fallback
            return contacts
            
    def _process_enriched_contact(self, apollo_contact: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Process enriched contact data from Apollo response."""
        try:
            enriched = {
                "source": "apollo",
                "confidence": apollo_contact.get("confidence", 0.0),
                "enriched_at": time.time()
            }
            
            # Basic contact info
            if apollo_contact.get("email"):
                enriched["email"] = apollo_contact["email"]
            if apollo_contact.get("first_name") or apollo_contact.get("last_name"):
                name_parts = []
                if apollo_contact.get("first_name"):
                    name_parts.append(apollo_contact["first_name"])
                if apollo_contact.get("last_name"):
                    name_parts.append(apollo_contact["last_name"])
                enriched["name"] = " ".join(name_parts)
                
            # Job and company info
            if apollo_contact.get("title"):
                enriched["job_title"] = apollo_contact["title"]
            if apollo_contact.get("organization"):
                org = apollo_contact["organization"]
                if org.get("name"):
                    enriched["company"] = org["name"]
                if org.get("industry"):
                    enriched["industry"] = org["industry"]
                if org.get("website_url"):
                    enriched["company_website"] = org["website_url"]
                    
            # Contact details
            if apollo_contact.get("phone_numbers"):
                enriched["phone_numbers"] = apollo_contact["phone_numbers"]
                
            # Social profiles
            social_profiles = {}
            if apollo_contact.get("linkedin_url"):
                social_profiles["linkedin"] = apollo_contact["linkedin_url"]
            if apollo_contact.get("twitter_url"):
                social_profiles["twitter"] = apollo_contact["twitter_url"]
            if social_profiles:
                enriched["social_profiles"] = social_profiles
                
            # Location info
            if apollo_contact.get("city") or apollo_contact.get("state") or apollo_contact.get("country"):
                location = {}
                if apollo_contact.get("city"):
                    location["city"] = apollo_contact["city"]
                if apollo_contact.get("state"):
                    location["state"] = apollo_contact["state"]
                if apollo_contact.get("country"):
                    location["country"] = apollo_contact["country"]
                enriched["location"] = location
                
            return enriched if len(enriched) > 3 else None  # Must have more than just source, confidence, enriched_at
            
        except Exception as e:
            logger.error(f"Failed to process Apollo contact: {str(e)}")
            return None
            
    async def health_check(self) -> bool:
        """Check if Apollo API is accessible."""
        try:
            if not self.api_key:
                return False
                
            # Make a simple API call to check health
            await self._make_request("auth/health")
            return True
            
        except Exception as e:
            logger.error(f"Apollo health check failed: {str(e)}")
            return False
            
    def get_cost_estimate(self, num_contacts: int) -> float:
        """Get cost estimate for enriching contacts."""
        return num_contacts * self.settings.api_costs.apollo_per_contact 