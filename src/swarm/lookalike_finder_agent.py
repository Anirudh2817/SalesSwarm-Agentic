"""
Lookalike Finder Agent - Finds similar leads based on ideal customer profiles
"""
import json
from typing import Dict, Any, List, Optional
from datetime import datetime

import openai

from ..core.knowledge_store import get_knowledge_store, SwarmEvent, EventType, AgentCapability
from ..utils.config import get_config
from ..utils.logger import agent_logger
from ..utils.models import LeadProfile, LookalikeRequest, LookalikeResponse, LeadStatus

from .lead_enrichment_agent import get_enrichment_agent


class LookalikeFinderAgent:
    """
    Finds lookalike leads based on provided ideal customer profiles.
    Analyzes sample profiles to extract ICP and finds matching leads.
    """
    
    def __init__(self):
        self.agent_id = "lookalike_finder"
        self.config = get_config()
        self.knowledge_store = get_knowledge_store()
        
        # OpenAI client
        self.client = openai.AsyncOpenAI(api_key=self.config.openai_api_key)
        self.model = self.config.llm_model
        
        # Enrichment agent for scraping sample profiles
        self.enrichment_agent = get_enrichment_agent()
        
        # Register with knowledge store
        self._register()
        
        agent_logger.log_system_info("AGENT_INIT", "Lookalike Finder Agent initialized")
    
    def _register(self):
        """Register agent with knowledge store"""
        capability = AgentCapability(
            agent_id=self.agent_id,
            name="Lookalike Finder",
            description="Finds similar leads based on ideal customer profiles",
            triggers=[EventType.LOOKALIKE_REQUESTED],
            outputs=[EventType.LOOKALIKE_FOUND]
        )
        self.knowledge_store.register_agent(self.agent_id, capability)
        self.knowledge_store.register_agent_handler(self.agent_id, self._handle_event)
    
    async def _handle_event(self, agent_id: str, event: SwarmEvent):
        """Handle incoming events"""
        if event.event_type == EventType.LOOKALIKE_REQUESTED:
            profile_urls = event.data.get("profile_urls", [])
            max_leads = event.data.get("max_leads", 100)
            
            if profile_urls:
                response = await self.find_lookalikes(
                    profile_urls=profile_urls,
                    max_leads=max_leads
                )
                
                # Publish event
                self.knowledge_store.publish_event(SwarmEvent(
                    event_type=EventType.LOOKALIKE_FOUND,
                    session_id=event.session_id,
                    agent_id=self.agent_id,
                    data={
                        "icp_summary": response.icp_summary,
                        "match_criteria": response.match_criteria,
                        "leads_count": response.total_found,
                        "leads": [l.model_dump() for l in response.leads]
                    }
                ))
    
    async def find_lookalikes(
        self,
        profile_urls: List[str],
        max_leads: int = 100,
        job_titles: Optional[List[str]] = None,
        locations: Optional[List[str]] = None,
        industries: Optional[List[str]] = None
    ) -> LookalikeResponse:
        """
        Find lookalike leads based on sample profiles.
        
        Args:
            profile_urls: LinkedIn URLs of ideal customer examples
            max_leads: Maximum number of leads to return
            job_titles: Optional title filters
            locations: Optional location filters
            industries: Optional industry filters
        
        Returns:
            LookalikeResponse with matching leads
        """
        agent_logger.log_agent_action(
            self.agent_id, "FIND_LOOKALIKES",
            f"Analyzing {len(profile_urls)} sample profiles"
        )
        
        # Step 1: Enrich sample profiles
        sample_profiles = []
        for url in profile_urls:
            profile = await self.enrichment_agent.enrich_single(url)
            if profile:
                sample_profiles.append(profile)
        
        if not sample_profiles:
            return LookalikeResponse(
                leads=[],
                icp_summary="Could not analyze sample profiles",
                match_criteria={},
                total_found=0
            )
        
        # Step 2: Analyze ICP from samples
        icp_analysis = await self._analyze_icp(sample_profiles)
        
        # Step 3: Generate lookalike leads
        # In production, this would query a lead database or use LinkedIn Sales Navigator
        # For now, we generate synthetic matching leads
        lookalikes = self._generate_lookalike_leads(
            icp_analysis,
            max_leads,
            job_titles=job_titles,
            locations=locations,
            industries=industries
        )
        
        agent_logger.log_agent_action(
            self.agent_id, "LOOKALIKES_FOUND",
            f"Found {len(lookalikes)} matching leads"
        )
        
        return LookalikeResponse(
            leads=lookalikes,
            icp_summary=icp_analysis.get("icp_summary", ""),
            match_criteria=icp_analysis,
            total_found=len(lookalikes)
        )
    
    async def _analyze_icp(self, profiles: List[LeadProfile]) -> Dict[str, Any]:
        """Analyze profiles to extract ideal customer profile"""
        try:
            profiles_text = "\n\n".join([
                f"Profile {i+1}:\n"
                f"- Name: {p.name}\n"
                f"- Title: {p.title}\n"
                f"- Company: {p.company}\n"
                f"- Industry: {p.industry}\n"
                f"- Location: {p.location}\n"
                f"- Company Size: {p.company_size}"
                for i, p in enumerate(profiles)
            ])
            
            prompt = f"""Analyze these ideal customer profiles and extract common traits.

PROFILES:
{profiles_text}

Identify patterns and return the Ideal Customer Profile (ICP).

Return ONLY valid JSON:
{{
    "icp_summary": "One paragraph describing the ideal customer",
    "common_titles": ["title1", "title2"],
    "common_industries": ["industry1", "industry2"],
    "common_company_sizes": ["11-50", "51-200"],
    "common_locations": ["location1", "location2"],
    "seniority_level": "Senior/Mid/Entry",
    "key_patterns": ["pattern1", "pattern2"]
}}"""

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert at identifying ideal customer profiles. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=500
            )
            
            content = response.choices[0].message.content.strip()
            return self._parse_json_response(content) or {}
            
        except Exception as e:
            agent_logger.log_error(f"ICP analysis error: {e}", self.agent_id)
            return {
                "icp_summary": "Analysis failed - using default criteria",
                "common_titles": [p.title for p in profiles if p.title][:3],
                "common_industries": [p.industry for p in profiles if p.industry][:2]
            }
    
    def _generate_lookalike_leads(
        self,
        icp: Dict[str, Any],
        max_leads: int,
        job_titles: Optional[List[str]] = None,
        locations: Optional[List[str]] = None,
        industries: Optional[List[str]] = None
    ) -> List[LeadProfile]:
        """Generate synthetic lookalike leads matching the ICP"""
        import hashlib
        import random
        
        # Use ICP criteria or provided filters
        titles = job_titles or icp.get("common_titles", ["VP of Sales", "Director of Marketing", "Head of Growth"])
        locs = locations or icp.get("common_locations", ["San Francisco, CA", "New York, NY", "Austin, TX"])
        inds = industries or icp.get("common_industries", ["Technology", "SaaS", "Fintech"])
        
        # Sample data for generation
        first_names = ["Alex", "Jordan", "Taylor", "Morgan", "Casey", "Riley", "Avery", "Quinn", "Reese", "Blake"]
        last_names = ["Anderson", "Thompson", "Martinez", "Robinson", "Clark", "Lewis", "Lee", "Walker", "Hall", "Young"]
        companies = ["Innovate Inc", "GrowthTech", "ScaleUp Co", "DataFirst", "CloudWorks", "TechPrime", "VentureLab", "NextGen Systems", "PrimeFlow", "CoreTech"]
        
        leads = []
        
        for i in range(min(max_leads, 100)):
            # Generate deterministic but varied data
            seed = f"lookalike_{i}_{icp.get('icp_summary', '')[:20]}"
            hash_val = int(hashlib.md5(seed.encode()).hexdigest()[:8], 16)
            
            first = first_names[hash_val % len(first_names)]
            last = last_names[(hash_val >> 4) % len(last_names)]
            title = titles[i % len(titles)] if titles else "Business Leader"
            company = companies[(hash_val >> 8) % len(companies)]
            industry = inds[i % len(inds)] if inds else "Technology"
            location = locs[i % len(locs)] if locs else "San Francisco, CA"
            
            lead = LeadProfile(
                id=f"lookalike_{hash_val:08x}",
                name=f"{first} {last}",
                email=f"{first.lower()}.{last.lower()}@{company.lower().replace(' ', '')}.com",
                title=title,
                company=company,
                linkedin_url=f"https://linkedin.com/in/{first.lower()}{last.lower()}{hash_val % 1000}",
                location=location,
                industry=industry,
                company_size=random.choice(["11-50", "51-200", "201-500"]),
                headline=f"{title} at {company}",
                status=LeadStatus.NEW,
                source="lookalike_generation"
            )
            leads.append(lead)
        
        return leads
    
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
_lookalike_finder_instance = None


def get_lookalike_finder() -> LookalikeFinderAgent:
    """Get global lookalike finder instance"""
    global _lookalike_finder_instance
    if _lookalike_finder_instance is None:
        _lookalike_finder_instance = LookalikeFinderAgent()
    return _lookalike_finder_instance
