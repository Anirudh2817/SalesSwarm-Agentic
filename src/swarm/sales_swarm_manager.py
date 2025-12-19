"""
Sales Swarm Manager - Master orchestrator for all sales agents
"""
from typing import Dict, Any, List, Optional
from datetime import datetime

from ..core.knowledge_store import get_knowledge_store, SwarmEvent, EventType, KnowledgeStore
from ..utils.config import get_config
from ..utils.logger import agent_logger
from ..utils.models import (
    LeadProfile, CampaignData, EmailSequence,
    CompanyIntelligence, LookalikeResponse
)

# Import agents (only frontend-visible ones)
from .email_generator_agent import get_email_generator, EmailGeneratorAgent
from .lead_enrichment_agent import get_enrichment_agent, LeadEnrichmentAgent
from .company_intel_agent import get_company_intel_agent, CompanyIntelAgent
from .lookalike_finder_agent import get_lookalike_finder, LookalikeFinderAgent
from .followup_orchestrator import get_followup_orchestrator, FollowupOrchestratorAgent
from .email_scheduler_agent import get_email_scheduler, EmailSchedulerAgent


class SalesSwarmManager:
    """
    Master orchestrator for the SalesSwarm agent system.
    Coordinates all agents and handles workflow routing.
    
    Agents (Frontend-visible only):
    - Email Generator: Creates personalized email sequences
    - Email Scheduler: Schedules emails based on date/time/timezone
    - Lead Enrichment: Extracts data from LinkedIn profiles
    - Company Intel: Scrapes company websites for insights
    - Lookalike Finder: Finds similar leads based on ICP
    - Follow-up Orchestrator: Manages email sequence timing
    """
    
    def __init__(self):
        self.agent_id = "sales_swarm_manager"
        self.config = get_config()
        self.knowledge_store: KnowledgeStore = get_knowledge_store()
        
        # Initialize all agents
        self._init_agents()
        
        agent_logger.log_system_info("SWARM_MANAGER", "Sales Swarm Manager initialized")
    
    def _init_agents(self):
        """Initialize all swarm agents"""
        self.email_generator: EmailGeneratorAgent = get_email_generator()
        self.email_scheduler: EmailSchedulerAgent = get_email_scheduler()
        self.enrichment_agent: LeadEnrichmentAgent = get_enrichment_agent()
        self.company_intel_agent: CompanyIntelAgent = get_company_intel_agent()
        self.lookalike_finder: LookalikeFinderAgent = get_lookalike_finder()
        self.followup_orchestrator: FollowupOrchestratorAgent = get_followup_orchestrator()
        
        agent_logger.log_system_info(
            "AGENTS_INITIALIZED",
            f"Registered agents: {', '.join(self.knowledge_store.get_registered_agents())}"
        )
    
    # === CAMPAIGN WORKFLOWS ===
    
    async def process_campaign_creation(
        self,
        campaign: CampaignData,
        leads: List[LeadProfile],
        session_id: str
    ) -> Dict[str, Any]:
        """
        Process a new campaign creation with leads.
        Generates email sequences for all leads.
        """
        agent_logger.log_agent_action(
            self.agent_id, "PROCESS_CAMPAIGN",
            f"Campaign: {campaign.name}, Leads: {len(leads)}"
        )
        
        # Create session
        self.knowledge_store.create_session(session_id, "campaign", {
            "campaign_id": campaign.id,
            "campaign_name": campaign.name
        })
        
        results = {
            "campaign_id": campaign.id,
            "session_id": session_id,
            "leads_processed": 0,
            "emails_generated": 0,
            "steps": []
        }
        
        try:
            # Generate emails for all leads
            for lead in leads:
                # Get company intel if URL available
                company_insights = None
                if lead.company_url:
                    intel_response = await self.company_intel_agent.get_company_intel(lead.company_url)
                    if intel_response.success:
                        company_insights = intel_response.intelligence.description
                
                # Generate email sequence
                sequence = await self.email_generator.generate_sequence(
                    campaign_goal=campaign.goal,
                    lead=lead,
                    company_insights=company_insights
                )
                
                if sequence:
                    results["emails_generated"] += 1
                    
                    # Store sequence
                    self.knowledge_store.store_email_sequence(
                        lead.id or lead.email,
                        campaign.id,
                        sequence.model_dump()
                    )
            
            results["leads_processed"] = len(leads)
            results["steps"].append({
                "step": "email_generation",
                "status": "completed",
                "details": f"Generated {results['emails_generated']} email sequences"
            })
            
            # Publish campaign created event
            self.knowledge_store.publish_event(SwarmEvent(
                event_type=EventType.CAMPAIGN_CREATED,
                session_id=session_id,
                agent_id=self.agent_id,
                data=results
            ))
            
            return results
            
        except Exception as e:
            agent_logger.log_error(f"Campaign processing error: {e}", self.agent_id)
            results["error"] = str(e)
            return results
    
    # === LEAD WORKFLOWS ===
    
    async def enrich_leads(
        self,
        linkedin_urls: List[str],
        session_id: str
    ) -> Dict[str, Any]:
        """Enrich leads from LinkedIn URLs"""
        agent_logger.log_agent_action(
            self.agent_id, "ENRICH_LEADS",
            f"Processing {len(linkedin_urls)} URLs"
        )
        
        # Create session
        self.knowledge_store.create_session(session_id, "enrichment")
        
        # Publish event to trigger enrichment agent
        self.knowledge_store.publish_event(SwarmEvent(
            event_type=EventType.LEAD_ENRICHMENT_REQUESTED,
            session_id=session_id,
            agent_id=self.agent_id,
            data={"linkedin_urls": linkedin_urls}
        ))
        
        # Direct call for immediate response
        response = await self.enrichment_agent.enrich_leads(linkedin_urls)
        
        return {
            "session_id": session_id,
            "leads": [l.model_dump() for l in response.leads],
            "success": response.success,
            "errors": response.errors
        }
    
    async def find_lookalikes(
        self,
        profile_urls: List[str],
        max_leads: int,
        session_id: str
    ) -> Dict[str, Any]:
        """Find lookalike leads from sample profiles"""
        agent_logger.log_agent_action(
            self.agent_id, "FIND_LOOKALIKES",
            f"Samples: {len(profile_urls)}, Max: {max_leads}"
        )
        
        self.knowledge_store.create_session(session_id, "lookalike")
        
        response = await self.lookalike_finder.find_lookalikes(
            profile_urls=profile_urls,
            max_leads=max_leads
        )
        
        return {
            "session_id": session_id,
            "icp_summary": response.icp_summary,
            "match_criteria": response.match_criteria,
            "leads": [l.model_dump() for l in response.leads],
            "total_found": response.total_found
        }
    
    # === EMAIL WORKFLOWS ===
    
    async def generate_emails(
        self,
        campaign_goal: str,
        lead: LeadProfile,
        company_insights: Optional[str] = None,
        num_followups: int = 2,
        session_id: str = None
    ) -> Dict[str, Any]:
        """Generate email sequence for a lead"""
        session_id = session_id or f"email_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        agent_logger.log_agent_action(
            self.agent_id, "GENERATE_EMAILS",
            f"For: {lead.name}"
        )
        
        self.knowledge_store.create_session(session_id, "email_generation")
        
        sequence = await self.email_generator.generate_sequence(
            campaign_goal=campaign_goal,
            lead=lead,
            company_insights=company_insights,
            num_followups=num_followups
        )
        
        if sequence:
            return {
                "session_id": session_id,
                "sequence": sequence.model_dump(),
                "success": True
            }
        else:
            return {
                "session_id": session_id,
                "sequence": None,
                "success": False,
                "error": "Failed to generate emails"
            }
    
    # === COMPANY INTEL WORKFLOW ===
    
    async def get_company_intel(
        self,
        company_url: str,
        company_name: Optional[str] = None,
        session_id: str = None
    ) -> Dict[str, Any]:
        """Get company intelligence"""
        session_id = session_id or f"intel_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        agent_logger.log_agent_action(
            self.agent_id, "GET_COMPANY_INTEL",
            f"URL: {company_url}"
        )
        
        response = await self.company_intel_agent.get_company_intel(company_url, company_name)
        
        return {
            "session_id": session_id,
            "intelligence": response.intelligence.model_dump() if response.intelligence else None,
            "success": response.success,
            "errors": response.errors
        }
    
    # === FOLLOW-UP WORKFLOW ===
    
    def get_pending_followups(self, lead_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get pending follow-ups"""
        return self.followup_orchestrator.get_pending_followups(lead_id)
    
    def get_sequence_status(self, lead_id: str) -> Dict[str, Any]:
        """Get email sequence status for a lead"""
        return self.followup_orchestrator.get_sequence_status(lead_id)
    
    # === UTILITY METHODS ===
    
    def get_session_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a processing session"""
        return self.knowledge_store.get_all_session_data(session_id)
    
    def get_agent_status(self) -> Dict[str, Any]:
        """Get status of all agents"""
        return {
            "agents": self.knowledge_store.get_registered_agents(),
            "active_sessions": len(self.knowledge_store.sessions)
        }


# Global instance
_swarm_manager_instance = None


def get_swarm_manager() -> SalesSwarmManager:
    """Get global swarm manager instance"""
    global _swarm_manager_instance
    if _swarm_manager_instance is None:
        _swarm_manager_instance = SalesSwarmManager()
    return _swarm_manager_instance
