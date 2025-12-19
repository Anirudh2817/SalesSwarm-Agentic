"""
Follow-up Orchestrator Agent - Manages email sequence timing and delivery
"""
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import asyncio

from ..core.knowledge_store import get_knowledge_store, SwarmEvent, EventType, AgentCapability
from ..utils.config import get_config
from ..utils.logger import agent_logger
from ..utils.models import EmailSequence, EmailContent


class FollowupOrchestratorAgent:
    """
    Manages follow-up email scheduling and delivery.
    Tracks email engagement and triggers next steps.
    """
    
    def __init__(self):
        self.agent_id = "followup_orchestrator"
        self.config = get_config()
        self.knowledge_store = get_knowledge_store()
        
        # Track scheduled follow-ups
        self.scheduled_followups: Dict[str, List[Dict[str, Any]]] = {}
        
        # Register with knowledge store
        self._register()
        
        agent_logger.log_system_info("AGENT_INIT", "Follow-up Orchestrator Agent initialized")
    
    def _register(self):
        """Register agent with knowledge store"""
        capability = AgentCapability(
            agent_id=self.agent_id,
            name="Follow-up Orchestrator",
            description="Manages email sequence timing and follow-up scheduling",
            triggers=[
                EventType.EMAIL_GENERATED,
                EventType.EMAIL_SENT,
                EventType.EMAIL_OPENED,
                EventType.EMAIL_RESPONDED
            ],
            outputs=[
                EventType.FOLLOWUP_SCHEDULED,
                EventType.FOLLOWUP_DUE
            ]
        )
        self.knowledge_store.register_agent(self.agent_id, capability)
        self.knowledge_store.register_agent_handler(self.agent_id, self._handle_event)
    
    async def _handle_event(self, agent_id: str, event: SwarmEvent):
        """Handle incoming events"""
        try:
            if event.event_type == EventType.EMAIL_GENERATED:
                sequence = event.data.get("sequence")
                if sequence:
                    await self._schedule_sequence_followups(event.session_id, sequence)
            
            elif event.event_type == EventType.EMAIL_SENT:
                lead_id = event.data.get("lead_id")
                step = event.data.get("step", 1)
                await self._handle_email_sent(event.session_id, lead_id, step)
            
            elif event.event_type == EventType.EMAIL_RESPONDED:
                lead_id = event.data.get("lead_id")
                await self._cancel_followups(lead_id)
                
        except Exception as e:
            agent_logger.log_error(f"Event handling error: {e}", self.agent_id)
    
    async def _schedule_sequence_followups(
        self,
        session_id: str,
        sequence: Dict[str, Any]
    ):
        """Schedule follow-ups for an email sequence"""
        lead_id = sequence.get("lead_id")
        emails = sequence.get("emails", [])
        
        if not lead_id or len(emails) <= 1:
            return
        
        followups = []
        send_date = datetime.now()
        
        for email in emails[1:]:  # Skip introduction (index 0)
            delay_days = email.get("delay_days", 3)
            send_date = send_date + timedelta(days=delay_days)
            
            followup = {
                "lead_id": lead_id,
                "step": email.get("step"),
                "scheduled_for": send_date.isoformat(),
                "email_data": email,
                "status": "scheduled"
            }
            followups.append(followup)
        
        self.scheduled_followups[lead_id] = followups
        
        # Publish event
        self.knowledge_store.publish_event(SwarmEvent(
            event_type=EventType.FOLLOWUP_SCHEDULED,
            session_id=session_id,
            agent_id=self.agent_id,
            data={
                "lead_id": lead_id,
                "followups_count": len(followups),
                "next_followup": followups[0]["scheduled_for"] if followups else None
            }
        ))
        
        agent_logger.log_agent_action(
            self.agent_id, "FOLLOWUPS_SCHEDULED",
            f"Lead {lead_id}: {len(followups)} follow-ups scheduled"
        )
    
    async def _handle_email_sent(
        self,
        session_id: str,
        lead_id: str,
        step: int
    ):
        """Handle email sent notification"""
        if lead_id in self.scheduled_followups:
            # Mark appropriate follow-up as sent
            for followup in self.scheduled_followups[lead_id]:
                if followup["step"] == step:
                    followup["status"] = "sent"
                    followup["sent_at"] = datetime.now().isoformat()
                    break
        
        agent_logger.log_agent_action(
            self.agent_id, "EMAIL_SENT_LOGGED",
            f"Lead {lead_id}, Step {step}"
        )
    
    async def _cancel_followups(self, lead_id: str):
        """Cancel all pending follow-ups (e.g., when lead responds)"""
        if lead_id in self.scheduled_followups:
            cancelled_count = 0
            for followup in self.scheduled_followups[lead_id]:
                if followup["status"] == "scheduled":
                    followup["status"] = "cancelled"
                    followup["cancelled_at"] = datetime.now().isoformat()
                    cancelled_count += 1
            
            agent_logger.log_agent_action(
                self.agent_id, "FOLLOWUPS_CANCELLED",
                f"Lead {lead_id}: {cancelled_count} follow-ups cancelled (lead responded)"
            )
    
    def get_pending_followups(self, lead_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get pending follow-ups for a lead or all leads"""
        pending = []
        
        if lead_id:
            followups = self.scheduled_followups.get(lead_id, [])
            pending = [f for f in followups if f["status"] == "scheduled"]
        else:
            for lid, followups in self.scheduled_followups.items():
                pending.extend([f for f in followups if f["status"] == "scheduled"])
        
        return pending
    
    def get_due_followups(self) -> List[Dict[str, Any]]:
        """Get follow-ups that are due now"""
        now = datetime.now()
        due = []
        
        for lead_id, followups in self.scheduled_followups.items():
            for followup in followups:
                if followup["status"] == "scheduled":
                    scheduled = datetime.fromisoformat(followup["scheduled_for"])
                    if scheduled <= now:
                        due.append({**followup, "lead_id": lead_id})
        
        return due
    
    async def check_and_send_due_followups(self, session_id: str):
        """Check for due follow-ups and trigger sending"""
        due = self.get_due_followups()
        
        for followup in due:
            self.knowledge_store.publish_event(SwarmEvent(
                event_type=EventType.FOLLOWUP_DUE,
                session_id=session_id,
                agent_id=self.agent_id,
                data={
                    "lead_id": followup["lead_id"],
                    "step": followup["step"],
                    "email_data": followup["email_data"]
                }
            ))
            
            agent_logger.log_agent_action(
                self.agent_id, "FOLLOWUP_DUE",
                f"Lead {followup['lead_id']}, Step {followup['step']}"
            )
        
        return {"due_count": len(due), "followups": due}
    
    def get_sequence_status(self, lead_id: str) -> Dict[str, Any]:
        """Get status of email sequence for a lead"""
        if lead_id not in self.scheduled_followups:
            return {"lead_id": lead_id, "status": "not_found"}
        
        followups = self.scheduled_followups[lead_id]
        
        return {
            "lead_id": lead_id,
            "total_followups": len(followups),
            "sent": len([f for f in followups if f["status"] == "sent"]),
            "scheduled": len([f for f in followups if f["status"] == "scheduled"]),
            "cancelled": len([f for f in followups if f["status"] == "cancelled"]),
            "followups": followups
        }


# Global instance
_followup_orchestrator_instance = None


def get_followup_orchestrator() -> FollowupOrchestratorAgent:
    """Get global follow-up orchestrator instance"""
    global _followup_orchestrator_instance
    if _followup_orchestrator_instance is None:
        _followup_orchestrator_instance = FollowupOrchestratorAgent()
    return _followup_orchestrator_instance
