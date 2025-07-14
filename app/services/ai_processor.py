"""AI processing service for contact extraction."""
import re
import json
from typing import Dict, List, Any, Optional
from datetime import datetime
import openai
from loguru import logger

from app.config import settings


class AIProcessor:
    """Handles AI-powered contact extraction and processing."""
    
    def __init__(self):
        if settings.openai_api_key:
            openai.api_key = settings.openai_api_key
        self.model = settings.ai_model_name
        self.max_tokens = settings.ai_max_tokens
    
    async def extract_contacts(self, content: str, url: str) -> Dict[str, Any]:
        """Extract contact information from scraped content using AI."""
        try:
            # Clean and prepare content
            cleaned_content = self._clean_content(content)
            
            if len(cleaned_content) < 50:  # Too little content
                return self._empty_contacts()
            
            # Extract contacts using pattern matching first (faster)
            pattern_contacts = self._extract_with_patterns(cleaned_content)
            
            # Use AI for enhanced extraction if enabled
            if settings.ai_enabled and settings.openai_api_key:
                ai_contacts = await self._extract_with_ai(cleaned_content, url)
                # Merge pattern and AI results
                contacts = self._merge_contact_results(pattern_contacts, ai_contacts)
            else:
                contacts = pattern_contacts
            
            # Calculate confidence score
            contacts['confidence'] = self._calculate_confidence(contacts, cleaned_content)
            
            logger.info(f"Extracted {len(contacts.get('emails', []))} emails, "
                       f"{len(contacts.get('phones', []))} phones from {url}")
            
            return contacts
            
        except Exception as e:
            logger.error(f"AI processing error for {url}: {e}")
            return self._empty_contacts()
    
    def _clean_content(self, content: str) -> str:
        """Clean and prepare content for processing."""
        if not content:
            return ""
        
        # Remove HTML tags
        import re
        content = re.sub(r'<[^>]+>', ' ', content)
        
        # Remove extra whitespace
        content = re.sub(r'\s+', ' ', content)
        
        # Limit content length
        max_length = 8000  # Leave room for prompt
        if len(content) > max_length:
            content = content[:max_length] + "..."
        
        return content.strip()
    
    def _extract_with_patterns(self, content: str) -> Dict[str, List[str]]:
        """Extract contacts using regex patterns."""
        contacts = {
            'emails': [],
            'phones': [],
            'names': [],
            'job_titles': [],
            'companies': [],
            'social_profiles': {}
        }
        
        # Email patterns
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        emails = re.findall(email_pattern, content, re.IGNORECASE)
        contacts['emails'] = list(set(emails))  # Remove duplicates
        
        # Phone patterns (US format)
        phone_patterns = [
            r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',  # 123-456-7890
            r'\(\d{3}\)\s*\d{3}[-.]?\d{4}',    # (123) 456-7890
            r'\+1[-.]?\d{3}[-.]?\d{3}[-.]?\d{4}' # +1-123-456-7890
        ]
        
        phones = []
        for pattern in phone_patterns:
            phones.extend(re.findall(pattern, content))
        contacts['phones'] = list(set(phones))
        
        # Name patterns (basic)
        name_patterns = [
            r'(?:CEO|CTO|CFO|Director|Manager|President|VP|Vice President)[\s:]+([A-Z][a-z]+ [A-Z][a-z]+)',
            r'Contact[\s:]+([A-Z][a-z]+ [A-Z][a-z]+)',
            r'([A-Z][a-z]+ [A-Z][a-z]+)[\s,]+(CEO|CTO|CFO|Director|Manager|President)'
        ]
        
        names = []
        for pattern in name_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                if isinstance(match, tuple):
                    names.extend([m for m in match if len(m.split()) == 2])
                else:
                    names.append(match)
        contacts['names'] = list(set(names))
        
        return contacts
    
    async def _extract_with_ai(self, content: str, url: str) -> Dict[str, List[str]]:
        """Extract contacts using OpenAI API."""
        try:
            prompt = self._build_extraction_prompt(content, url)
            
            response = await openai.ChatCompletion.acreate(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert at extracting contact information from web content."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=self.max_tokens,
                temperature=0.1
            )
            
            result_text = response.choices[0].message.content
            contacts = self._parse_ai_response(result_text)
            
            return contacts
            
        except Exception as e:
            logger.error(f"AI extraction error: {e}")
            return self._empty_contacts()
    
    def _build_extraction_prompt(self, content: str, url: str) -> str:
        """Build the AI extraction prompt."""
        prompt = f"""
Extract contact information from the following web content. Return the results in JSON format.

URL: {url}

Content:
{content}

Please extract:
1. Email addresses (valid email format only)
2. Phone numbers (clean format)
3. Names (first and last name combinations)
4. Job titles (CEO, CTO, Director, Manager, etc.)
5. Company names
6. Social media profiles (LinkedIn, Twitter URLs)

Return in this exact JSON format:
{{
    "emails": ["email1@example.com", "email2@example.com"],
    "phones": ["+1-234-567-8900", "234-567-8901"],
    "names": ["John Smith", "Jane Doe"],
    "job_titles": ["CEO", "Marketing Director"],
    "companies": ["Company Name"],
    "social_profiles": {{
        "linkedin": "https://linkedin.com/in/profile",
        "twitter": "https://twitter.com/handle"
    }}
}}

Only include valid, real contact information. Do not include generic examples or placeholders.
"""
        return prompt
    
    def _parse_ai_response(self, response_text: str) -> Dict[str, Any]:
        """Parse AI response and extract contact data."""
        try:
            # Try to extract JSON from response
            import json
            
            # Look for JSON block in response
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            
            if start_idx >= 0 and end_idx > start_idx:
                json_text = response_text[start_idx:end_idx]
                contacts = json.loads(json_text)
                
                # Validate structure
                expected_keys = ['emails', 'phones', 'names', 'job_titles', 'companies', 'social_profiles']
                for key in expected_keys:
                    if key not in contacts:
                        contacts[key] = [] if key != 'social_profiles' else {}
                
                return contacts
            else:
                logger.warning("No valid JSON found in AI response")
                return self._empty_contacts()
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {e}")
            return self._empty_contacts()
    
    def _merge_contact_results(self, pattern_contacts: Dict, ai_contacts: Dict) -> Dict:
        """Merge pattern-based and AI-extracted contacts."""
        merged = {
            'emails': [],
            'phones': [],
            'names': [],
            'job_titles': [],
            'companies': [],
            'social_profiles': {}
        }
        
        # Merge lists and remove duplicates
        for key in ['emails', 'phones', 'names', 'job_titles', 'companies']:
            combined = (pattern_contacts.get(key, []) + ai_contacts.get(key, []))
            merged[key] = list(set(combined))  # Remove duplicates
        
        # Merge social profiles
        merged['social_profiles'].update(pattern_contacts.get('social_profiles', {}))
        merged['social_profiles'].update(ai_contacts.get('social_profiles', {}))
        
        return merged
    
    def _calculate_confidence(self, contacts: Dict, content: str) -> float:
        """Calculate confidence score for extracted contacts."""
        score = 0.0
        total_contacts = 0
        
        # Email confidence
        emails = contacts.get('emails', [])
        if emails:
            # Higher confidence for multiple emails from same domain
            domains = [email.split('@')[1] for email in emails if '@' in email]
            unique_domains = set(domains)
            score += min(len(emails) * 0.2, 0.6)
            if len(unique_domains) == 1:  # Same domain
                score += 0.2
            total_contacts += len(emails)
        
        # Phone confidence
        phones = contacts.get('phones', [])
        if phones:
            score += min(len(phones) * 0.15, 0.4)
            total_contacts += len(phones)
        
        # Name confidence
        names = contacts.get('names', [])
        if names:
            score += min(len(names) * 0.1, 0.3)
            total_contacts += len(names)
        
        # Job title confidence
        job_titles = contacts.get('job_titles', [])
        if job_titles:
            score += min(len(job_titles) * 0.1, 0.2)
        
        # Content quality factor
        if len(content) > 1000:
            score += 0.1
        
        # Normalize to 0-1 range
        return min(score, 1.0)
    
    def _empty_contacts(self) -> Dict[str, Any]:
        """Return empty contact structure."""
        return {
            'emails': [],
            'phones': [],
            'names': [],
            'job_titles': [],
            'companies': [],
            'social_profiles': {},
            'confidence': 0.0
        } 