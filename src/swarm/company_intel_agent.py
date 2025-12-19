"""
Company Intelligence Agent - Scrapes and analyzes company data
"""
import json
from typing import Dict, Any, Optional
from datetime import datetime

import openai

from ..core.knowledge_store import get_knowledge_store, SwarmEvent, EventType, AgentCapability
from ..utils.config import get_config
from ..utils.logger import agent_logger
from ..utils.models import CompanyIntelligence, CompanyIntelRequest, CompanyIntelResponse

# Web scraping imports
try:
    import requests
    from bs4 import BeautifulSoup
    SCRAPING_AVAILABLE = True
except ImportError:
    SCRAPING_AVAILABLE = False


class CompanyIntelAgent:
    """
    Gathers intelligence about companies by scraping websites
    and using LLM to extract insights.
    """
    
    def __init__(self):
        self.agent_id = "company_intel"
        self.config = get_config()
        self.knowledge_store = get_knowledge_store()
        
        # OpenAI client
        self.client = openai.AsyncOpenAI(api_key=self.config.openai_api_key)
        self.model = self.config.llm_model
        
        # Register with knowledge store
        self._register()
        
        agent_logger.log_system_info("AGENT_INIT", "Company Intelligence Agent initialized")
    
    def _register(self):
        """Register agent with knowledge store"""
        capability = AgentCapability(
            agent_id=self.agent_id,
            name="Company Intelligence",
            description="Scrapes and analyzes company websites for sales insights",
            triggers=[EventType.COMPANY_INTEL_REQUESTED],
            outputs=[EventType.COMPANY_INTEL_SCRAPED]
        )
        self.knowledge_store.register_agent(self.agent_id, capability)
        self.knowledge_store.register_agent_handler(self.agent_id, self._handle_event)
    
    async def _handle_event(self, agent_id: str, event: SwarmEvent):
        """Handle incoming events"""
        if event.event_type == EventType.COMPANY_INTEL_REQUESTED:
            company_url = event.data.get("company_url")
            company_name = event.data.get("company_name")
            
            if company_url:
                response = await self.get_company_intel(company_url, company_name)
                
                if response.success:
                    # Store intel
                    self.knowledge_store.store_company_intel(
                        company_url,
                        response.intelligence.model_dump()
                    )
                    
                    # Publish event
                    self.knowledge_store.publish_event(SwarmEvent(
                        event_type=EventType.COMPANY_INTEL_SCRAPED,
                        session_id=event.session_id,
                        agent_id=self.agent_id,
                        data={
                            "company_url": company_url,
                            "intelligence": response.intelligence.model_dump()
                        }
                    ))
    
    async def get_company_intel(
        self,
        company_url: str,
        company_name: Optional[str] = None,
        include_news: bool = True
    ) -> CompanyIntelResponse:
        """
        Get intelligence about a company from their website.
        
        Args:
            company_url: Company website URL
            company_name: Optional company name
            include_news: Whether to try to find recent news
        
        Returns:
            CompanyIntelResponse with extracted intelligence
        """
        agent_logger.log_agent_action(self.agent_id, "GET_INTEL", f"Analyzing: {company_url}")
        
        # Check cache first
        cached = self.knowledge_store.get_company_intel(company_url)
        if cached:
            agent_logger.log_agent_action(self.agent_id, "CACHE_HIT", f"Using cached intel for {company_url}")
            return CompanyIntelResponse(
                intelligence=CompanyIntelligence(**cached),
                success=True
            )
        
        try:
            # Scrape website
            website_content = self._scrape_website(company_url)
            
            if not website_content:
                return CompanyIntelResponse(
                    intelligence=self._create_minimal_intel(company_url, company_name),
                    success=False,
                    errors=["Failed to scrape website"]
                )
            
            # Analyze with LLM
            intel = await self._analyze_with_llm(company_url, company_name, website_content)
            
            if intel:
                agent_logger.log_agent_action(
                    self.agent_id, "INTEL_EXTRACTED",
                    f"Company: {intel.company_name}, Industry: {intel.industry}"
                )
                return CompanyIntelResponse(intelligence=intel, success=True)
            else:
                return CompanyIntelResponse(
                    intelligence=self._create_minimal_intel(company_url, company_name),
                    success=False,
                    errors=["Failed to analyze website content"]
                )
            
        except Exception as e:
            agent_logger.log_error(f"Error getting company intel: {e}", self.agent_id)
            return CompanyIntelResponse(
                intelligence=self._create_minimal_intel(company_url, company_name),
                success=False,
                errors=[str(e)]
            )
    
    def _scrape_website(self, url: str) -> Optional[str]:
        """Scrape website content"""
        if not SCRAPING_AVAILABLE:
            agent_logger.log_warning("Web scraping libs not available", self.agent_id)
            return None
        
        try:
            # Normalize URL
            if not url.startswith(('http://', 'https://')):
                url = f"https://{url}"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Remove script and style elements
            for element in soup(['script', 'style', 'nav', 'footer', 'header']):
                element.decompose()
            
            # Get text content
            text = soup.get_text(separator=' ', strip=True)
            
            # Truncate to reasonable length for LLM
            max_chars = 5000
            if len(text) > max_chars:
                text = text[:max_chars] + "..."
            
            return text
            
        except Exception as e:
            agent_logger.log_error(f"Scraping error: {e}", self.agent_id)
            return None
    
    async def _analyze_with_llm(
        self,
        company_url: str,
        company_name: Optional[str],
        website_content: str
    ) -> Optional[CompanyIntelligence]:
        """Use LLM to analyze website content"""
        try:
            prompt = f"""Analyze this company's website content and extract sales-relevant insights.

COMPANY URL: {company_url}
COMPANY NAME: {company_name or 'Unknown'}

WEBSITE CONTENT:
{website_content}

Extract and return:
1. What the company does (products/services)
2. Their industry
3. Target market/customers
4. Any visible challenges or pain points
5. Opportunities for sales engagement
6. Key talking points for outreach

Return ONLY valid JSON:
{{
    "company_name": "Company Name",
    "industry": "Industry",
    "description": "What they do in 1-2 sentences",
    "products_services": ["product1", "product2"],
    "challenges": ["challenge1", "challenge2"],
    "opportunities": ["opportunity1", "opportunity2"]
}}"""

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a business analyst extracting sales intelligence. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=600
            )
            
            content = response.choices[0].message.content.strip()
            intel_data = self._parse_json_response(content)
            
            if intel_data:
                return CompanyIntelligence(
                    company_name=intel_data.get("company_name", company_name or "Unknown"),
                    website=company_url,
                    industry=intel_data.get("industry"),
                    description=intel_data.get("description"),
                    products_services=intel_data.get("products_services", []),
                    challenges=intel_data.get("challenges", []),
                    opportunities=intel_data.get("opportunities", []),
                    scraped_at=datetime.now(),
                    source_url=company_url
                )
            
            return None
            
        except Exception as e:
            agent_logger.log_error(f"LLM analysis error: {e}", self.agent_id)
            return None
    
    def _create_minimal_intel(self, company_url: str, company_name: Optional[str]) -> CompanyIntelligence:
        """Create minimal intel when scraping/analysis fails"""
        # Extract company name from URL if not provided
        if not company_name:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(company_url if '://' in company_url else f'https://{company_url}')
                company_name = parsed.netloc.replace('www.', '').split('.')[0].title()
            except:
                company_name = "Unknown"
        
        return CompanyIntelligence(
            company_name=company_name,
            website=company_url,
            description="Company information could not be automatically extracted.",
            scraped_at=datetime.now(),
            source_url=company_url
        )
    
    def _parse_json_response(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse JSON from LLM response"""
        try:
            cleaned = content.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            elif cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
            
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            agent_logger.log_error(f"JSON parse error: {e}", self.agent_id)
            return None


# Global instance
_company_intel_instance = None


def get_company_intel_agent() -> CompanyIntelAgent:
    """Get global company intel agent instance"""
    global _company_intel_instance
    if _company_intel_instance is None:
        _company_intel_instance = CompanyIntelAgent()
    return _company_intel_instance
