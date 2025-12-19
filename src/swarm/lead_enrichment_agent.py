"""
Lead Enrichment Agent - Extracts data from LinkedIn profiles
"""
import json
import os
from typing import Dict, Any, List, Optional
from datetime import datetime

from ..core.knowledge_store import get_knowledge_store, SwarmEvent, EventType, AgentCapability
from ..utils.config import get_config
from ..utils.logger import agent_logger
from ..utils.models import LeadProfile, LeadEnrichmentRequest, LeadEnrichmentResponse, LeadStatus

# Try to import Apify client
try:
    from apify_client import ApifyClient
    APIFY_AVAILABLE = True
except ImportError:
    APIFY_AVAILABLE = False


class LeadEnrichmentAgent:
    """
    Enriches lead data by scraping LinkedIn profiles.
    Uses Apify for compliant LinkedIn scraping.
    """
    
    def __init__(self):
        self.agent_id = "lead_enrichment"
        self.config = get_config()
        self.knowledge_store = get_knowledge_store()
        
        # Apify client for LinkedIn scraping
        self.apify_client = None
        if APIFY_AVAILABLE and self.config.apify_api_key:
            self.apify_client = ApifyClient(self.config.apify_api_key)
            agent_logger.log_system_info("APIFY_CONNECTED", "Apify client initialized")
        else:
            agent_logger.log_warning("Apify not available - will use mock data", self.agent_id)
        
        # Register with knowledge store
        self._register()
        
        agent_logger.log_system_info("AGENT_INIT", "Lead Enrichment Agent initialized")
    
    def _register(self):
        """Register agent with knowledge store"""
        capability = AgentCapability(
            agent_id=self.agent_id,
            name="Lead Enrichment",
            description="Enriches lead data from LinkedIn profiles",
            triggers=[EventType.LEAD_ENRICHMENT_REQUESTED],
            outputs=[EventType.LEAD_ENRICHED]
        )
        self.knowledge_store.register_agent(self.agent_id, capability)
        self.knowledge_store.register_agent_handler(self.agent_id, self._handle_event)
    
    async def _handle_event(self, agent_id: str, event: SwarmEvent):
        """Handle incoming events"""
        if event.event_type == EventType.LEAD_ENRICHMENT_REQUESTED:
            linkedin_urls = event.data.get("linkedin_urls", [])
            campaign_id = event.data.get("campaign_id")
            
            if linkedin_urls:
                response = await self.enrich_leads(linkedin_urls)
                
                for lead in response.leads:
                    # Store enriched data
                    self.knowledge_store.store_lead_data(
                        lead.id or lead.email or lead.linkedin_url,
                        lead.model_dump()
                    )
                    
                    # Publish event for each enriched lead
                    self.knowledge_store.publish_event(SwarmEvent(
                        event_type=EventType.LEAD_ENRICHED,
                        session_id=event.session_id,
                        agent_id=self.agent_id,
                        data={
                            "lead": lead.model_dump(),
                            "campaign_id": campaign_id
                        }
                    ))
    
    async def enrich_leads(self, linkedin_urls: List[str]) -> LeadEnrichmentResponse:
        """
        Enrich leads from LinkedIn URLs.
        
        Args:
            linkedin_urls: List of LinkedIn profile URLs
        
        Returns:
            LeadEnrichmentResponse with enriched lead profiles
        """
        agent_logger.log_agent_action(self.agent_id, "ENRICH_LEADS", f"Processing {len(linkedin_urls)} URLs")
        
        leads = []
        errors = []
        
        for url in linkedin_urls:
            try:
                if self.apify_client:
                    lead = await self._scrape_with_apify(url)
                else:
                    lead = self._create_mock_lead(url)
                
                if lead:
                    leads.append(lead)
                    agent_logger.log_agent_action(self.agent_id, "LEAD_ENRICHED", f"Enriched: {lead.name}")
            except Exception as e:
                error_msg = f"Failed to enrich {url}: {str(e)}"
                errors.append(error_msg)
                agent_logger.log_error(error_msg, self.agent_id)
        
        return LeadEnrichmentResponse(
            leads=leads,
            success=len(leads) > 0,
            errors=errors if errors else None
        )
    
    async def _scrape_with_apify(self, linkedin_url: str) -> Optional[LeadProfile]:
        """Scrape LinkedIn profile using Apify"""
        try:
            # LinkedIn Profile Scraper actor
            run_input = {
                "profileUrls": [linkedin_url],
                "proxyConfiguration": {"useApifyProxy": True}
            }
            
            # Run the actor
            run = self.apify_client.actor("2SyF0bVxmgGr8IVCZ").call(run_input=run_input)
            
            # Get results
            items = list(self.apify_client.dataset(run["defaultDatasetId"]).iterate_items())
            
            if items:
                item = items[0]
                return LeadProfile(
                    name=item.get("name", "Unknown"),
                    email=item.get("email"),
                    phone=item.get("phone"),
                    title=item.get("headline", "").split(" at ")[0] if " at " in item.get("headline", "") else item.get("headline"),
                    company=item.get("company") or (item.get("headline", "").split(" at ")[1] if " at " in item.get("headline", "") else None),
                    linkedin_url=linkedin_url,
                    location=item.get("location"),
                    industry=item.get("industry"),
                    headline=item.get("headline"),
                    summary=item.get("summary"),
                    skills=item.get("skills", []),
                    status=LeadStatus.ENRICHED,
                    enriched_at=datetime.now(),
                    source="linkedin_apify"
                )
            
            return None
            
        except Exception as e:
            agent_logger.log_error(f"Apify scraping error: {e}", self.agent_id)
            # Fallback to mock data
            return self._create_mock_lead(linkedin_url)
    
    def _create_mock_lead(self, linkedin_url: str) -> LeadProfile:
        """Create mock lead data for development/testing"""
        import hashlib
        
        # Generate deterministic mock data based on URL
        url_hash = hashlib.md5(linkedin_url.encode()).hexdigest()
        
        # Sample data pools
        first_names = ["John", "Sarah", "Michael", "Emily", "David", "Jessica", "Robert", "Amanda"]
        last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis"]
        titles = ["VP of Sales", "Head of Marketing", "CEO", "CTO", "Director of Operations", "Product Manager", "Founder"]
        companies = ["TechCorp", "InnovateLabs", "GrowthFirst", "ScaleCo", "VentureHub", "DataDriven Inc"]
        industries = ["Technology", "SaaS", "Fintech", "Healthcare", "E-commerce", "Consulting"]
        locations = ["San Francisco, CA", "New York, NY", "Austin, TX", "Seattle, WA", "Boston, MA"]
        
        # Use hash to select consistent mock data
        idx = int(url_hash[:8], 16)
        
        first_name = first_names[idx % len(first_names)]
        last_name = last_names[(idx >> 4) % len(last_names)]
        title = titles[(idx >> 8) % len(titles)]
        company = companies[(idx >> 12) % len(companies)]
        industry = industries[(idx >> 16) % len(industries)]
        location = locations[(idx >> 20) % len(locations)]
        
        return LeadProfile(
            id=f"mock_{url_hash[:12]}",
            name=f"{first_name} {last_name}",
            email=f"{first_name.lower()}.{last_name.lower()}@{company.lower().replace(' ', '')}.com",
            title=title,
            company=company,
            linkedin_url=linkedin_url,
            location=location,
            industry=industry,
            company_size="51-200",
            headline=f"{title} at {company}",
            summary=f"Experienced {title} with a track record of driving growth and innovation.",
            skills=["Leadership", "Strategy", "Sales", "Marketing", "Business Development"],
            status=LeadStatus.ENRICHED,
            enriched_at=datetime.now(),
            source="mock_data"
        )
    
    async def enrich_single(self, linkedin_url: str) -> Optional[LeadProfile]:
        """Convenience method to enrich a single lead"""
        response = await self.enrich_leads([linkedin_url])
        return response.leads[0] if response.leads else None


# Global instance
_enrichment_agent_instance = None


def get_enrichment_agent() -> LeadEnrichmentAgent:
    """Get global enrichment agent instance"""
    global _enrichment_agent_instance
    if _enrichment_agent_instance is None:
        _enrichment_agent_instance = LeadEnrichmentAgent()
    return _enrichment_agent_instance
