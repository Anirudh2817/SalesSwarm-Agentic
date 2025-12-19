"""
Knowledge Store - Central state and event management for SalesSwarm-Agentic
"""
import threading
import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from .redis_cache import get_redis_cache, RedisSessionCache
from ..utils.logger import agent_logger


class EventType(str, Enum):
    """Event types for swarm communication"""
    # Campaign Events
    CAMPAIGN_CREATED = "campaign_created"
    CAMPAIGN_UPDATED = "campaign_updated"
    CAMPAIGN_LAUNCHED = "campaign_launched"
    
    # Lead Events
    LEAD_ENRICHMENT_REQUESTED = "lead_enrichment_requested"
    LEAD_ENRICHED = "lead_enriched"
    LEAD_QUALIFIED = "lead_qualified"
    LEAD_ADDED_TO_CAMPAIGN = "lead_added_to_campaign"
    
    # Lookalike Events
    LOOKALIKE_REQUESTED = "lookalike_requested"
    LOOKALIKE_FOUND = "lookalike_found"
    LOOKALIKE_APPROVED = "lookalike_approved"
    LOOKALIKE_REJECTED = "lookalike_rejected"
    
    # Email Events
    EMAIL_GENERATION_REQUESTED = "email_generation_requested"
    EMAIL_GENERATED = "email_generated"
    EMAIL_SENT = "email_sent"
    EMAIL_OPENED = "email_opened"
    EMAIL_RESPONDED = "email_responded"
    
    # Follow-up Events
    FOLLOWUP_SCHEDULED = "followup_scheduled"
    FOLLOWUP_DUE = "followup_due"
    FOLLOWUP_SENT = "followup_sent"
    
    # Company Intel Events
    COMPANY_INTEL_REQUESTED = "company_intel_requested"
    COMPANY_INTEL_SCRAPED = "company_intel_scraped"
    
    # CRM Events
    CRM_SYNC_REQUESTED = "crm_sync_requested"
    CRM_SYNCED = "crm_synced"
    
    # Session Events
    SESSION_STARTED = "session_started"
    SESSION_ENDED = "session_ended"


@dataclass
class SwarmEvent:
    """Event for agent communication"""
    event_type: EventType
    session_id: str
    agent_id: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentCapability:
    """Agent capability registration"""
    agent_id: str
    name: str
    description: str
    triggers: List[EventType] = field(default_factory=list)
    outputs: List[EventType] = field(default_factory=list)


class KnowledgeStore:
    """
    Central knowledge store for SalesSwarm-Agentic.
    Manages shared state, events, and agent coordination.
    """
    
    def __init__(self):
        # Thread safety
        self.lock = threading.Lock()
        
        # Session management
        self.sessions: Dict[str, Dict[str, Any]] = {}
        
        # Agent registry
        self.registered_agents: Dict[str, AgentCapability] = {}
        self.event_subscribers: Dict[EventType, Set[str]] = defaultdict(set)
        self.agent_handlers: Dict[str, Callable] = {}
        
        # In-memory data stores (backed by Redis when available)
        self.agent_data: Dict[str, Dict[str, Any]] = {
            "campaigns": {},
            "leads": {},
            "emails": {},
            "qualifications": {},
            "company_intel": {},
        }
        
        # Redis cache
        self.redis_cache: RedisSessionCache = get_redis_cache()
        
        agent_logger.log_system_info("KNOWLEDGE_STORE", "Initialized SalesSwarm Knowledge Store")
    
    # Session Management
    def create_session(self, session_id: str, context: str = "campaign", initial_data: Optional[Dict[str, Any]] = None) -> None:
        """Create a new session"""
        with self.lock:
            self.sessions[session_id] = {
                "session_id": session_id,
                "context": context,
                "created_at": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "status": "active",
                "events": [],
                "metadata": initial_data or {}
            }
            agent_logger.log_system_info("SESSION_CREATED", f"Session {session_id} created for {context}")
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session data"""
        return self.sessions.get(session_id)
    
    def update_session(self, session_id: str, updates: Dict[str, Any]) -> None:
        """Update session data"""
        with self.lock:
            if session_id in self.sessions:
                self.sessions[session_id].update(updates)
                self.sessions[session_id]["last_updated"] = datetime.now().isoformat()
    
    def end_session(self, session_id: str) -> None:
        """End a session"""
        with self.lock:
            if session_id in self.sessions:
                self.sessions[session_id]["status"] = "ended"
                self.sessions[session_id]["ended_at"] = datetime.now().isoformat()
    
    # Agent Registration
    def register_agent(self, agent_id: str, capability: AgentCapability) -> None:
        """Register an agent with its capabilities"""
        self.registered_agents[agent_id] = capability
        for event_type in capability.triggers:
            self.event_subscribers[event_type].add(agent_id)
        agent_logger.log_system_info("AGENT_REGISTERED", f"Agent {agent_id} registered")
    
    def register_agent_handler(self, agent_id: str, handler: Callable) -> None:
        """Register event handler for an agent"""
        self.agent_handlers[agent_id] = handler
    
    # Event Publishing
    def publish_event(self, event: SwarmEvent) -> None:
        """Publish event to subscribed agents"""
        # Store event in session
        if event.session_id in self.sessions:
            self.sessions[event.session_id]["events"].append({
                "type": event.event_type.value,
                "agent": event.agent_id,
                "timestamp": event.timestamp,
                "data_keys": list(event.data.keys())
            })
        
        # Log event
        agent_logger.log_event(event.event_type.value, event.session_id, f"From: {event.agent_id}")
        
        # Notify subscribers
        subscribers = self.event_subscribers.get(event.event_type, set())
        for agent_id in subscribers:
            if agent_id in self.agent_handlers and agent_id != event.agent_id:
                try:
                    handler = self.agent_handlers[agent_id]
                    self._run_handler_async(handler, agent_id, event)
                except Exception as e:
                    agent_logger.log_error(f"Handler error for {agent_id}: {e}")
    
    def _run_handler_async(self, handler: Callable, agent_id: str, event: SwarmEvent) -> None:
        """Run handler in a background thread"""
        def run_notification():
            try:
                if asyncio.iscoroutinefunction(handler):
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(handler(agent_id, event))
                    loop.close()
                else:
                    handler(agent_id, event)
            except Exception as e:
                agent_logger.log_error(f"Handler error for {agent_id}: {e}")
        
        thread = threading.Thread(target=run_notification)
        thread.start()
    
    # Data Storage - Campaigns
    def store_campaign_data(self, campaign_id: str, data: Dict[str, Any]) -> None:
        """Store campaign processing data"""
        with self.lock:
            self.agent_data["campaigns"][campaign_id] = {
                **data,
                "stored_at": datetime.now().isoformat()
            }
        self.redis_cache.store_campaign_data(campaign_id, data)
    
    def get_campaign_data(self, campaign_id: str) -> Optional[Dict[str, Any]]:
        """Get campaign data"""
        redis_data = self.redis_cache.get_campaign_data(campaign_id)
        if redis_data:
            return redis_data
        return self.agent_data["campaigns"].get(campaign_id)
    
    # Data Storage - Leads
    def store_lead_data(self, lead_id: str, data: Dict[str, Any]) -> None:
        """Store lead data"""
        with self.lock:
            self.agent_data["leads"][lead_id] = {
                **data,
                "stored_at": datetime.now().isoformat()
            }
        self.redis_cache.store_enrichment_data(lead_id, data)
    
    def get_lead_data(self, lead_id: str) -> Optional[Dict[str, Any]]:
        """Get lead data"""
        redis_data = self.redis_cache.get_enrichment_data(lead_id)
        if redis_data:
            return redis_data
        return self.agent_data["leads"].get(lead_id)
    
    # Data Storage - Email Sequences
    def store_email_sequence(self, lead_id: str, campaign_id: str, data: Dict[str, Any]) -> None:
        """Store email sequence"""
        key = f"{campaign_id}:{lead_id}"
        with self.lock:
            self.agent_data["emails"][key] = {
                **data,
                "stored_at": datetime.now().isoformat()
            }
        self.redis_cache.store_email_sequence(lead_id, campaign_id, data)
    
    def get_email_sequence(self, lead_id: str, campaign_id: str) -> Optional[Dict[str, Any]]:
        """Get email sequence"""
        redis_data = self.redis_cache.get_email_sequence(lead_id, campaign_id)
        if redis_data:
            return redis_data
        key = f"{campaign_id}:{lead_id}"
        return self.agent_data["emails"].get(key)
    
    # Data Storage - Qualifications
    def store_qualification_data(self, lead_id: str, data: Dict[str, Any]) -> None:
        """Store qualification result"""
        with self.lock:
            self.agent_data["qualifications"][lead_id] = {
                **data,
                "stored_at": datetime.now().isoformat()
            }
        self.redis_cache.store_qualification_data(lead_id, data)
    
    def get_qualification_data(self, lead_id: str) -> Optional[Dict[str, Any]]:
        """Get qualification result"""
        redis_data = self.redis_cache.get_qualification_data(lead_id)
        if redis_data:
            return redis_data
        return self.agent_data["qualifications"].get(lead_id)
    
    # Data Storage - Company Intelligence
    def store_company_intel(self, company_url: str, data: Dict[str, Any]) -> None:
        """Store company intelligence"""
        with self.lock:
            self.agent_data["company_intel"][company_url] = {
                **data,
                "stored_at": datetime.now().isoformat()
            }
        self.redis_cache.store_company_intel(company_url, data)
    
    def get_company_intel(self, company_url: str) -> Optional[Dict[str, Any]]:
        """Get company intelligence"""
        redis_data = self.redis_cache.get_company_intel(company_url)
        if redis_data:
            return redis_data
        return self.agent_data["company_intel"].get(company_url)
    
    # Utility Methods
    def get_all_session_data(self, session_id: str) -> Dict[str, Any]:
        """Get all data for a session"""
        return {
            "session": self.get_session(session_id),
            "redis_data": self.redis_cache.get_all_session_data(session_id)
        }
    
    def get_registered_agents(self) -> List[str]:
        """Get list of registered agent IDs"""
        return list(self.registered_agents.keys())


# Global instance
_knowledge_store_instance = None


def get_knowledge_store() -> KnowledgeStore:
    """Get global knowledge store instance"""
    global _knowledge_store_instance
    if _knowledge_store_instance is None:
        _knowledge_store_instance = KnowledgeStore()
    return _knowledge_store_instance
