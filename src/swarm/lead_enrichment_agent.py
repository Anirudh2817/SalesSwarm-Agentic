"""
Lead Enrichment Agent - Extracts data from LinkedIn profiles using Apollo.io
"""
import json
import httpx
from typing import Dict, Any, List, Optional
from datetime import datetime

from ..core.knowledge_store import get_knowledge_store, SwarmEvent, EventType, AgentCapability
from ..utils.config import get_config
from ..utils.logger import agent_logger
from ..utils.models import LeadProfile, LeadEnrichmentRequest, LeadEnrichmentResponse, LeadStatus


class LeadEnrichmentAgent:
    """
    Enriches lead data from LinkedIn profiles.
    Uses Apollo.io People Enrichment API for comprehensive lead data.
    """
    
    APOLLO_API_BASE = "https://api.apollo.io/v1"
    
    def __init__(self):
        self.agent_id = "lead_enrichment"
        self.config = get_config()
        self.knowledge_store = get_knowledge_store()
        
        # Apollo API key
        self.apollo_api_key = self.config.apollo_api_key
        if self.apollo_api_key:
            agent_logger.log_system_info("APOLLO_CONFIGURED", "Apollo.io API key found")
        else:
            agent_logger.log_warning("Apollo API key not found - will use mock data", self.agent_id)
        
        # Register with knowledge store
        self._register()
        
        agent_logger.log_system_info("AGENT_INIT", "Lead Enrichment Agent initialized (Apollo.io)")
    
    def _register(self):
        """Register agent with knowledge store"""
        capability = AgentCapability(
            agent_id=self.agent_id,
            name="Lead Enrichment",
            description="Enriches lead data from LinkedIn profiles using Apollo.io",
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
        Enrich leads from LinkedIn URLs using Apollo.io.
        
        Args:
            linkedin_urls: List of LinkedIn profile URLs
        
        Returns:
            LeadEnrichmentResponse with enriched lead profiles
        """
        agent_logger.log_agent_action(self.agent_id, "ENRICH_LEADS", f"Processing {len(linkedin_urls)} URLs via Apollo")
        
        leads = []
        errors = []
        
        for url in linkedin_urls:
            try:
                if self.apollo_api_key:
                    lead = await self._enrich_with_apollo(url)
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
    
    async def _enrich_with_apollo(self, linkedin_url: str) -> Optional[LeadProfile]:
        """Enrich lead using Apollo.io People Enrichment API"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Apollo People Enrichment endpoint
                response = await client.post(
                    f"{self.APOLLO_API_BASE}/people/match",
                    headers={
                        "Content-Type": "application/json",
                        "Cache-Control": "no-cache"
                    },
                    json={
                        "api_key": self.apollo_api_key,
                        "linkedin_url": linkedin_url
                    }
                )
                
                if response.status_code != 200:
                    agent_logger.log_error(
                        f"Apollo API error: {response.status_code} - {response.text}",
                        self.agent_id
                    )
                    return self._create_mock_lead(linkedin_url)
                
                data = response.json()
                person = data.get("person", {})
                
                if not person:
                    agent_logger.log_warning(f"No data found for {linkedin_url}", self.agent_id)
                    return self._create_mock_lead(linkedin_url)
                
                # Extract organization info
                org = person.get("organization", {}) or {}
                employment = person.get("employment_history", [])
                current_job = employment[0] if employment else {}
                
                return LeadProfile(
                    id=person.get("id"),
                    name=f"{person.get('first_name', '')} {person.get('last_name', '')}".strip() or "Unknown",
                    first_name=person.get("first_name"),
                    last_name=person.get("last_name"),
                    email=person.get("email"),
                    phone=person.get("phone_numbers", [{}])[0].get("sanitized_number") if person.get("phone_numbers") else None,
                    title=person.get("title"),
                    company=org.get("name") or person.get("organization_name"),
                    company_url=org.get("website_url"),
                    linkedin_url=linkedin_url,
                    location=f"{person.get('city', '')}, {person.get('state', '')}, {person.get('country', '')}".strip(", "),
                    industry=org.get("industry"),
                    company_size=org.get("estimated_num_employees"),
                    headline=person.get("headline"),
                    summary=person.get("summary"),
                    seniority=person.get("seniority"),
                    departments=person.get("departments", []),
                    status=LeadStatus.ENRICHED,
                    enriched_at=datetime.now(),
                    source="apollo"
                )
                
        except httpx.TimeoutException:
            agent_logger.log_error(f"Apollo API timeout for {linkedin_url}", self.agent_id)
            return self._create_mock_lead(linkedin_url)
        except Exception as e:
            agent_logger.log_error(f"Apollo enrichment error: {e}", self.agent_id)
            return self._create_mock_lead(linkedin_url)
    
    async def enrich_by_email(self, email: str) -> Optional[LeadProfile]:
        """Enrich lead by email address using Apollo.io"""
        if not self.apollo_api_key:
            agent_logger.log_warning("Apollo API key not configured", self.agent_id)
            return None
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.APOLLO_API_BASE}/people/match",
                    headers={
                        "Content-Type": "application/json",
                        "Cache-Control": "no-cache"
                    },
                    json={
                        "api_key": self.apollo_api_key,
                        "email": email
                    }
                )
                
                if response.status_code != 200:
                    return None
                
                data = response.json()
                person = data.get("person", {})
                
                if not person:
                    return None
                
                org = person.get("organization", {}) or {}
                
                return LeadProfile(
                    id=person.get("id"),
                    name=f"{person.get('first_name', '')} {person.get('last_name', '')}".strip() or "Unknown",
                    first_name=person.get("first_name"),
                    last_name=person.get("last_name"),
                    email=email,
                    phone=person.get("phone_numbers", [{}])[0].get("sanitized_number") if person.get("phone_numbers") else None,
                    title=person.get("title"),
                    company=org.get("name"),
                    company_url=org.get("website_url"),
                    linkedin_url=person.get("linkedin_url"),
                    location=f"{person.get('city', '')}, {person.get('state', '')}".strip(", "),
                    industry=org.get("industry"),
                    seniority=person.get("seniority"),
                    status=LeadStatus.ENRICHED,
                    enriched_at=datetime.now(),
                    source="apollo"
                )
                
        except Exception as e:
            agent_logger.log_error(f"Apollo email enrichment error: {e}", self.agent_id)
            return None
    
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
            first_name=first_name,
            last_name=last_name,
            email=f"{first_name.lower()}.{last_name.lower()}@{company.lower().replace(' ', '')}.com",
            title=title,
            company=company,
            linkedin_url=linkedin_url,
            location=location,
            industry=industry,
            company_size="51-200",
            headline=f"{title} at {company}",
            summary=f"Experienced {title} with a track record of driving growth and innovation.",
            seniority="director",
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
