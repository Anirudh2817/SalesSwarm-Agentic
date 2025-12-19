"""
Email Scheduler Agent - Schedules emails based on date, time, and timezone
"""
import pytz
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass

from ..core.knowledge_store import get_knowledge_store, SwarmEvent, EventType, AgentCapability
from ..utils.config import get_config
from ..utils.logger import agent_logger


@dataclass
class ScheduledEmail:
    """Represents a scheduled email"""
    lead_id: str
    campaign_id: str
    email_step: int
    scheduled_time: datetime
    timezone: str
    status: str = "scheduled"  # scheduled, sent, cancelled


class EmailSchedulerAgent:
    """
    Schedules emails based on campaign date, time, and timezone settings.
    Handles recipient timezone conversion when enabled.
    """
    
    def __init__(self):
        self.agent_id = "email_scheduler"
        self.config = get_config()
        self.knowledge_store = get_knowledge_store()
        
        # Store scheduled emails
        self.scheduled_emails: Dict[str, List[ScheduledEmail]] = {}
        
        # Register with knowledge store
        self._register()
        
        agent_logger.log_system_info("AGENT_INIT", "Email Scheduler Agent initialized")
    
    def _register(self):
        """Register agent with knowledge store"""
        capability = AgentCapability(
            agent_id=self.agent_id,
            name="Email Scheduler",
            description="Schedules emails based on date, time, and timezone",
            triggers=[EventType.EMAIL_GENERATED, EventType.CAMPAIGN_LAUNCHED],
            outputs=[EventType.FOLLOWUP_SCHEDULED]
        )
        self.knowledge_store.register_agent(self.agent_id, capability)
        self.knowledge_store.register_agent_handler(self.agent_id, self._handle_event)
    
    async def _handle_event(self, agent_id: str, event: SwarmEvent):
        """Handle incoming events"""
        if event.event_type == EventType.EMAIL_GENERATED:
            # Schedule the generated emails
            schedule_data = event.data.get("schedule", {})
            if schedule_data:
                await self.schedule_email_sequence(
                    lead_id=event.data.get("lead_id"),
                    campaign_id=event.data.get("campaign_id"),
                    sequence=event.data.get("sequence"),
                    send_date=schedule_data.get("send_date"),
                    send_time=schedule_data.get("send_time"),
                    timezone=schedule_data.get("timezone"),
                    use_recipient_timezone=schedule_data.get("use_recipient_timezone", False),
                    recipient_location=event.data.get("lead", {}).get("location")
                )
    
    async def schedule_email_sequence(
        self,
        lead_id: str,
        campaign_id: str,
        sequence: Dict[str, Any],
        send_date: str,
        send_time: str,
        timezone: str,
        use_recipient_timezone: bool = False,
        recipient_location: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Schedule an email sequence for a lead.
        
        Args:
            lead_id: Lead identifier
            campaign_id: Campaign identifier
            sequence: Email sequence data
            send_date: Date to send (YYYY-MM-DD)
            send_time: Time to send (HH:MM)
            timezone: Selected timezone
            use_recipient_timezone: If True, infer timezone from recipient location
            recipient_location: Lead's location for timezone inference
        
        Returns:
            Scheduling result with scheduled times
        """
        agent_logger.log_agent_action(
            self.agent_id, "SCHEDULE_SEQUENCE",
            f"Lead: {lead_id}, Date: {send_date}, Time: {send_time}"
        )
        
        try:
            # Determine timezone to use
            if use_recipient_timezone and recipient_location:
                effective_timezone = self._infer_timezone_from_location(recipient_location)
                agent_logger.log_agent_action(
                    self.agent_id, "TIMEZONE_INFERRED",
                    f"Location: {recipient_location} → Timezone: {effective_timezone}"
                )
            else:
                effective_timezone = timezone or "America/New_York"
            
            # Parse base send datetime
            base_datetime = self._parse_send_datetime(send_date, send_time, effective_timezone)
            
            # Schedule each email in the sequence
            emails = sequence.get("emails", [])
            scheduled = []
            
            for email in emails:
                step = email.get("step", 1)
                delay_days = email.get("delay_days", 0)
                
                # Calculate scheduled time for this email
                scheduled_time = base_datetime + timedelta(days=delay_days)
                
                scheduled_email = ScheduledEmail(
                    lead_id=lead_id,
                    campaign_id=campaign_id,
                    email_step=step,
                    scheduled_time=scheduled_time,
                    timezone=effective_timezone
                )
                
                scheduled.append({
                    "step": step,
                    "scheduled_time": scheduled_time.isoformat(),
                    "timezone": effective_timezone,
                    "status": "scheduled"
                })
                
                # Store in memory
                key = f"{campaign_id}:{lead_id}"
                if key not in self.scheduled_emails:
                    self.scheduled_emails[key] = []
                self.scheduled_emails[key].append(scheduled_email)
            
            # Publish event
            self.knowledge_store.publish_event(SwarmEvent(
                event_type=EventType.FOLLOWUP_SCHEDULED,
                session_id=f"schedule_{campaign_id}",
                agent_id=self.agent_id,
                data={
                    "lead_id": lead_id,
                    "campaign_id": campaign_id,
                    "scheduled_emails": scheduled,
                    "timezone_used": effective_timezone
                }
            ))
            
            agent_logger.log_agent_action(
                self.agent_id, "SEQUENCE_SCHEDULED",
                f"Scheduled {len(scheduled)} emails for lead {lead_id}"
            )
            
            return {
                "success": True,
                "lead_id": lead_id,
                "campaign_id": campaign_id,
                "scheduled_count": len(scheduled),
                "scheduled_emails": scheduled,
                "timezone_used": effective_timezone
            }
            
        except Exception as e:
            agent_logger.log_error(f"Scheduling error: {e}", self.agent_id)
            return {
                "success": False,
                "error": str(e)
            }
    
    def _parse_send_datetime(self, date_str: str, time_str: str, timezone_str: str) -> datetime:
        """Parse date and time into timezone-aware datetime"""
        try:
            tz = pytz.timezone(timezone_str)
        except pytz.exceptions.UnknownTimeZoneError:
            tz = pytz.timezone("America/New_York")
        
        # Parse date (YYYY-MM-DD) and time (HH:MM)
        date_parts = date_str.split("-")
        time_parts = time_str.split(":")
        
        dt = datetime(
            year=int(date_parts[0]),
            month=int(date_parts[1]),
            day=int(date_parts[2]),
            hour=int(time_parts[0]),
            minute=int(time_parts[1]) if len(time_parts) > 1 else 0
        )
        
        return tz.localize(dt)
    
    def _infer_timezone_from_location(self, location: str) -> str:
        """Infer timezone from location string"""
        location_lower = location.lower()
        
        # US locations
        us_timezones = {
            "new york": "America/New_York",
            "ny": "America/New_York",
            "boston": "America/New_York",
            "miami": "America/New_York",
            "chicago": "America/Chicago",
            "dallas": "America/Chicago",
            "houston": "America/Chicago",
            "denver": "America/Denver",
            "phoenix": "America/Phoenix",
            "los angeles": "America/Los_Angeles",
            "san francisco": "America/Los_Angeles",
            "seattle": "America/Los_Angeles",
            "california": "America/Los_Angeles",
            "texas": "America/Chicago",
            "austin": "America/Chicago",
        }
        
        # International locations
        intl_timezones = {
            "london": "Europe/London",
            "uk": "Europe/London",
            "paris": "Europe/Paris",
            "berlin": "Europe/Berlin",
            "germany": "Europe/Berlin",
            "amsterdam": "Europe/Amsterdam",
            "mumbai": "Asia/Kolkata",
            "india": "Asia/Kolkata",
            "bangalore": "Asia/Kolkata",
            "singapore": "Asia/Singapore",
            "tokyo": "Asia/Tokyo",
            "japan": "Asia/Tokyo",
            "sydney": "Australia/Sydney",
            "australia": "Australia/Sydney",
            "toronto": "America/Toronto",
            "canada": "America/Toronto",
            "dubai": "Asia/Dubai",
            "uae": "Asia/Dubai",
        }
        
        # Check US locations first
        for city, tz in us_timezones.items():
            if city in location_lower:
                return tz
        
        # Check international locations
        for city, tz in intl_timezones.items():
            if city in location_lower:
                return tz
        
        # Default to US Eastern if unknown
        return "America/New_York"
    
    def get_scheduled_emails(
        self,
        campaign_id: Optional[str] = None,
        lead_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get scheduled emails filtered by campaign or lead"""
        results = []
        
        for key, emails in self.scheduled_emails.items():
            for email in emails:
                # Filter by campaign
                if campaign_id and email.campaign_id != campaign_id:
                    continue
                # Filter by lead
                if lead_id and email.lead_id != lead_id:
                    continue
                
                results.append({
                    "lead_id": email.lead_id,
                    "campaign_id": email.campaign_id,
                    "step": email.email_step,
                    "scheduled_time": email.scheduled_time.isoformat(),
                    "timezone": email.timezone,
                    "status": email.status
                })
        
        return sorted(results, key=lambda x: x["scheduled_time"])
    
    def get_due_emails(self) -> List[Dict[str, Any]]:
        """Get emails that are due to be sent now"""
        now = datetime.now(pytz.UTC)
        due = []
        
        for key, emails in self.scheduled_emails.items():
            for email in emails:
                if email.status == "scheduled":
                    # Convert scheduled time to UTC for comparison
                    scheduled_utc = email.scheduled_time.astimezone(pytz.UTC)
                    if scheduled_utc <= now:
                        due.append({
                            "lead_id": email.lead_id,
                            "campaign_id": email.campaign_id,
                            "step": email.email_step,
                            "scheduled_time": email.scheduled_time.isoformat(),
                            "timezone": email.timezone
                        })
        
        return due
    
    def cancel_scheduled_email(self, campaign_id: str, lead_id: str, step: Optional[int] = None) -> bool:
        """Cancel scheduled emails for a lead"""
        key = f"{campaign_id}:{lead_id}"
        
        if key not in self.scheduled_emails:
            return False
        
        cancelled = 0
        for email in self.scheduled_emails[key]:
            if step is None or email.email_step == step:
                if email.status == "scheduled":
                    email.status = "cancelled"
                    cancelled += 1
        
        agent_logger.log_agent_action(
            self.agent_id, "EMAILS_CANCELLED",
            f"Cancelled {cancelled} emails for lead {lead_id}"
        )
        
        return cancelled > 0


# Global instance
_scheduler_instance = None


def get_email_scheduler() -> EmailSchedulerAgent:
    """Get global email scheduler instance"""
    global _scheduler_instance
    if _scheduler_instance is None:
        _scheduler_instance = EmailSchedulerAgent()
    return _scheduler_instance
