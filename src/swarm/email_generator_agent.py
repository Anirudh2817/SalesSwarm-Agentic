"""
Email Generator Agent - Creates personalized email sequences for campaigns
"""
import json
import re
from typing import Dict, Any, List, Optional
from datetime import datetime

import openai

from ..core.knowledge_store import get_knowledge_store, SwarmEvent, EventType, AgentCapability
from ..utils.config import get_config
from ..utils.logger import agent_logger
from ..utils.models import (
    LeadProfile, EmailContent, EmailSequence, EmailType,
    EmailGenerationRequest, EmailGenerationResponse
)


class EmailGeneratorAgent:
    """
    Generates personalized email sequences for sales campaigns.
    Uses LLM to create compelling, tailored outreach emails.
    """
    
    def __init__(self):
        self.agent_id = "email_generator"
        self.config = get_config()
        self.knowledge_store = get_knowledge_store()
        
        # OpenAI client
        self.client = openai.AsyncOpenAI(api_key=self.config.openai_api_key)
        self.model = self.config.llm_model
        
        # Register with knowledge store
        self._register()
        
        agent_logger.log_system_info("AGENT_INIT", f"Email Generator Agent initialized with model {self.model}")
    
    def _register(self):
        """Register agent with knowledge store"""
        capability = AgentCapability(
            agent_id=self.agent_id,
            name="Email Generator",
            description="Generates personalized email sequences for campaigns",
            triggers=[EventType.EMAIL_GENERATION_REQUESTED, EventType.LEAD_ENRICHED],
            outputs=[EventType.EMAIL_GENERATED]
        )
        self.knowledge_store.register_agent(self.agent_id, capability)
        self.knowledge_store.register_agent_handler(self.agent_id, self._handle_event)
    
    async def _handle_event(self, agent_id: str, event: SwarmEvent):
        """Handle incoming events"""
        if event.event_type == EventType.EMAIL_GENERATION_REQUESTED:
            await self._handle_generation_request(event)
        elif event.event_type == EventType.LEAD_ENRICHED:
            # Auto-generate emails when leads are enriched (if campaign context exists)
            campaign_id = event.data.get("campaign_id")
            if campaign_id:
                await self._handle_generation_request(event)
    
    async def _handle_generation_request(self, event: SwarmEvent):
        """Handle email generation request event"""
        try:
            lead_data = event.data.get("lead", {})
            campaign_goal = event.data.get("campaign_goal", "")
            company_insights = event.data.get("company_insights", "")
            
            lead = LeadProfile(**lead_data) if lead_data else None
            if not lead:
                agent_logger.log_error("No lead data in generation request", self.agent_id)
                return
            
            sequence = await self.generate_sequence(
                campaign_goal=campaign_goal,
                lead=lead,
                company_insights=company_insights
            )
            
            if sequence:
                # Store and publish event
                self.knowledge_store.store_email_sequence(
                    lead.id or lead.email or "unknown",
                    event.data.get("campaign_id", "default"),
                    sequence.model_dump()
                )
                
                self.knowledge_store.publish_event(SwarmEvent(
                    event_type=EventType.EMAIL_GENERATED,
                    session_id=event.session_id,
                    agent_id=self.agent_id,
                    data={
                        "lead_id": lead.id or lead.email,
                        "sequence": sequence.model_dump(),
                        "email_count": len(sequence.emails)
                    }
                ))
        except Exception as e:
            agent_logger.log_error(f"Error handling generation request: {e}", self.agent_id)
    
    async def generate_sequence(
        self,
        campaign_goal: str,
        lead: LeadProfile,
        company_insights: Optional[str] = None,
        tone: str = "professional",
        num_followups: int = 2
    ) -> Optional[EmailSequence]:
        """
        Generate a complete email sequence for a lead.
        
        Args:
            campaign_goal: The objective of the campaign
            lead: Lead profile data
            company_insights: Optional company intelligence
            tone: Email tone (professional, casual, formal)
            num_followups: Number of follow-up emails (1-5)
        
        Returns:
            EmailSequence with introduction and follow-up emails
        """
        agent_logger.log_agent_action(self.agent_id, "GENERATE_SEQUENCE", f"For: {lead.name}")
        
        emails: List[EmailContent] = []
        
        try:
            # Generate introduction email
            intro_email = await self._generate_introduction(
                campaign_goal, lead, company_insights, tone
            )
            if intro_email:
                emails.append(intro_email)
            
            # Generate follow-up emails
            for i in range(1, num_followups + 1):
                previous_email = emails[-1] if emails else None
                followup = await self._generate_followup(
                    campaign_goal, lead, previous_email, i, tone
                )
                if followup:
                    emails.append(followup)
            
            if not emails:
                agent_logger.log_error("Failed to generate any emails", self.agent_id)
                return None
            
            sequence = EmailSequence(
                campaign_id="pending",
                lead_id=lead.id or lead.email or "unknown",
                emails=emails,
                lead_name=lead.name,
                company_name=lead.company,
                lead_insights=lead.headline,
                company_insights=company_insights
            )
            
            agent_logger.log_agent_action(
                self.agent_id, "SEQUENCE_GENERATED",
                f"{len(emails)} emails for {lead.name}"
            )
            
            return sequence
            
        except Exception as e:
            agent_logger.log_error(f"Error generating sequence: {e}", self.agent_id)
            return None
    
    async def _generate_introduction(
        self,
        campaign_goal: str,
        lead: LeadProfile,
        company_insights: Optional[str],
        tone: str
    ) -> Optional[EmailContent]:
        """Generate introduction email"""
        try:
            prompt = f"""Write a cold outreach email for a sales campaign.

CAMPAIGN GOAL: {campaign_goal}

LEAD INFORMATION:
- Name: {lead.name}
- Title: {lead.title or 'Unknown'}
- Company: {lead.company or 'Unknown'}
- Industry: {lead.industry or 'Unknown'}

COMPANY INSIGHTS:
{company_insights or 'No specific insights available'}

REQUIREMENTS:
- Subject line must be compelling and under 50 characters
- Email body should be {tone} and under 150 words
- Include personalization based on the lead's role/company
- End with a soft call-to-action (question, not demand)
- Use {{lead_name}} for the recipient's first name
- Use {{company_name}} for the company name

Return ONLY valid JSON (no markdown):
{{"subject": "Subject line", "body": "Email body with personalization"}}"""

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert B2B sales email copywriter. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )
            
            content = response.choices[0].message.content.strip()
            email_data = self._parse_json_response(content)
            
            if email_data and "subject" in email_data and "body" in email_data:
                return EmailContent(
                    step=1,
                    type=EmailType.INTRODUCTION,
                    subject=email_data["subject"],
                    body=email_data["body"],
                    personalization_tokens=self._extract_tokens(email_data["body"]),
                    delay_days=0
                )
            
            return None
            
        except Exception as e:
            agent_logger.log_error(f"Error generating introduction: {e}", self.agent_id)
            return None
    
    async def _generate_followup(
        self,
        campaign_goal: str,
        lead: LeadProfile,
        previous_email: Optional[EmailContent],
        followup_number: int,
        tone: str
    ) -> Optional[EmailContent]:
        """Generate follow-up email"""
        try:
            prev_subject = previous_email.subject if previous_email else "Previous outreach"
            prev_body = previous_email.body[:200] if previous_email else "Initial contact"
            
            prompt = f"""Write follow-up email #{followup_number} for a sales campaign.

CAMPAIGN GOAL: {campaign_goal}

LEAD: {lead.name}, {lead.title or 'Unknown'} at {lead.company or 'Unknown'}

PREVIOUS EMAIL SUBJECT: {prev_subject}
PREVIOUS EMAIL EXCERPT: {prev_body}...

REQUIREMENTS:
- Shorter than introduction (under 100 words)
- Reference the previous email naturally
- Provide a NEW value angle or insight
- Follow-up #{followup_number}: {'More direct, last attempt feel' if followup_number >= 2 else 'Gentle reminder'}
- Delay: {3 * followup_number} days after previous email

Return ONLY valid JSON:
{{"subject": "Subject line", "body": "Email body"}}"""

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert B2B sales email copywriter. Return only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=400
            )
            
            content = response.choices[0].message.content.strip()
            email_data = self._parse_json_response(content)
            
            if email_data and "subject" in email_data and "body" in email_data:
                return EmailContent(
                    step=followup_number + 1,
                    type=EmailType.FOLLOW_UP if followup_number < 3 else EmailType.FINAL,
                    subject=email_data["subject"],
                    body=email_data["body"],
                    personalization_tokens=self._extract_tokens(email_data["body"]),
                    delay_days=3 * followup_number
                )
            
            return None
            
        except Exception as e:
            agent_logger.log_error(f"Error generating follow-up: {e}", self.agent_id)
            return None
    
    def _parse_json_response(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse JSON from LLM response, handling markdown code blocks"""
        try:
            # Remove markdown code blocks if present
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
    
    def _extract_tokens(self, text: str) -> List[str]:
        """Extract personalization tokens from email text"""
        # Find {{token}} patterns
        tokens = re.findall(r'\{\{(\w+)\}\}', text)
        return list(set(tokens))


# Global instance
_email_generator_instance = None


def get_email_generator() -> EmailGeneratorAgent:
    """Get global email generator instance"""
    global _email_generator_instance
    if _email_generator_instance is None:
        _email_generator_instance = EmailGeneratorAgent()
    return _email_generator_instance
