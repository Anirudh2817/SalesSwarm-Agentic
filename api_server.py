"""
SalesSwarm-Agentic API Server
FastAPI server exposing swarm agent capabilities
"""
import os
import uuid
from typing import List, Optional
from datetime import datetime
from contextlib import asynccontextmanager

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Import swarm manager and models
from src.swarm.sales_swarm_manager import get_swarm_manager, SalesSwarmManager
from src.utils.models import LeadProfile, CampaignData
from src.utils.logger import agent_logger


# Request/Response Models
class HealthResponse(BaseModel):
    status: str
    timestamp: str
    agents: List[str]
    version: str = "1.0.0"


class EnrichLeadsRequest(BaseModel):
    linkedin_urls: List[str] = Field(..., min_length=1)


class FindLookalikeRequest(BaseModel):
    profile_urls: List[str] = Field(..., min_length=1, max_length=5)
    max_leads: int = Field(default=100, ge=25, le=1000)


class GenerateEmailsRequest(BaseModel):
    campaign_goal: str
    lead: dict
    company_insights: Optional[str] = None
    num_followups: int = Field(default=2, ge=1, le=5)


class ScheduleEmailsRequest(BaseModel):
    lead_id: str
    campaign_id: str
    sequence: dict
    send_date: str = Field(..., description="Date in YYYY-MM-DD format")
    send_time: str = Field(..., description="Time in HH:MM format")
    timezone: str = Field(default="America/New_York")
    use_recipient_timezone: bool = Field(default=False)
    recipient_location: Optional[str] = None


class CompanyIntelRequest(BaseModel):
    company_url: str
    company_name: Optional[str] = None


class ProcessCampaignRequest(BaseModel):
    campaign: dict
    leads: List[dict]


# Lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize swarm on startup"""
    agent_logger.log_system_info("SERVER_STARTUP", "Initializing SalesSwarm-Agentic...")
    
    # Initialize swarm manager (this initializes all agents)
    swarm = get_swarm_manager()
    
    agent_logger.log_system_info("SERVER_READY", f"Server ready with {len(swarm.knowledge_store.get_registered_agents())} agents")
    
    yield
    
    agent_logger.log_system_info("SERVER_SHUTDOWN", "Shutting down SalesSwarm-Agentic...")


# Create FastAPI app
app = FastAPI(
    title="SalesSwarm-Agentic API",
    description="Multi-agent sales automation system",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# === HEALTH & STATUS ===

@app.get("/", tags=["Health"])
async def root():
    """Root endpoint"""
    return {
        "service": "SalesSwarm-Agentic",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs"
    }


@app.get("/api/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint"""
    swarm = get_swarm_manager()
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now().isoformat(),
        agents=swarm.knowledge_store.get_registered_agents()
    )


@app.get("/api/status", tags=["Health"])
async def get_status():
    """Get detailed system status"""
    swarm = get_swarm_manager()
    return swarm.get_agent_status()


# === LEAD ENRICHMENT ===

@app.post("/api/leads/enrich", tags=["Leads"])
async def enrich_leads(request: EnrichLeadsRequest):
    """
    Enrich leads from LinkedIn URLs.
    Extracts name, title, company, and other profile data.
    """
    swarm = get_swarm_manager()
    session_id = f"enrich_{uuid.uuid4().hex[:8]}"
    
    try:
        result = await swarm.enrich_leads(
            linkedin_urls=request.linkedin_urls,
            session_id=session_id
        )
        return result
    except Exception as e:
        agent_logger.log_error(f"Enrichment error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === LOOKALIKE FINDER ===

@app.post("/api/leads/lookalike", tags=["Leads"])
async def find_lookalike_leads(request: FindLookalikeRequest):
    """
    Find lookalike leads based on sample profiles.
    Analyzes ICP from samples and generates matching leads.
    """
    swarm = get_swarm_manager()
    session_id = f"lookalike_{uuid.uuid4().hex[:8]}"
    
    try:
        result = await swarm.find_lookalikes(
            profile_urls=request.profile_urls,
            max_leads=request.max_leads,
            session_id=session_id
        )
        return result
    except Exception as e:
        agent_logger.log_error(f"Lookalike finder error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === EMAIL GENERATION ===

@app.post("/api/emails/generate", tags=["Emails"])
async def generate_emails(request: GenerateEmailsRequest):
    """
    Generate personalized email sequence for a lead.
    Creates introduction and follow-up emails.
    """
    swarm = get_swarm_manager()
    session_id = f"email_{uuid.uuid4().hex[:8]}"
    
    try:
        lead = LeadProfile(**request.lead)
        result = await swarm.generate_emails(
            campaign_goal=request.campaign_goal,
            lead=lead,
            company_insights=request.company_insights,
            num_followups=request.num_followups,
            session_id=session_id
        )
        return result
    except Exception as e:
        agent_logger.log_error(f"Email generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === EMAIL SCHEDULING ===

@app.post("/api/emails/schedule", tags=["Emails"])
async def schedule_emails(request: ScheduleEmailsRequest):
    """
    Schedule email sequence for a lead.
    Handles date, time, and timezone (including recipient timezone inference).
    """
    swarm = get_swarm_manager()
    
    try:
        result = await swarm.email_scheduler.schedule_email_sequence(
            lead_id=request.lead_id,
            campaign_id=request.campaign_id,
            sequence=request.sequence,
            send_date=request.send_date,
            send_time=request.send_time,
            timezone=request.timezone,
            use_recipient_timezone=request.use_recipient_timezone,
            recipient_location=request.recipient_location
        )
        return result
    except Exception as e:
        agent_logger.log_error(f"Email scheduling error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === COMPANY INTELLIGENCE ===

@app.post("/api/company/intel", tags=["Company"])
async def get_company_intel(request: CompanyIntelRequest):
    """
    Get intelligence about a company.
    Scrapes website and extracts sales-relevant insights.
    """
    swarm = get_swarm_manager()
    session_id = f"intel_{uuid.uuid4().hex[:8]}"
    
    try:
        result = await swarm.get_company_intel(
            company_url=request.company_url,
            company_name=request.company_name,
            session_id=session_id
        )
        return result
    except Exception as e:
        agent_logger.log_error(f"Company intel error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === CAMPAIGN PROCESSING ===

@app.post("/api/campaigns/process", tags=["Campaigns"])
async def process_campaign(request: ProcessCampaignRequest, background_tasks: BackgroundTasks):
    """
    Process a new campaign with leads.
    Generates personalized email sequences for all leads.
    """
    swarm = get_swarm_manager()
    session_id = f"campaign_{uuid.uuid4().hex[:8]}"
    
    try:
        campaign = CampaignData(**request.campaign)
        leads = [LeadProfile(**l) for l in request.leads]
        
        result = await swarm.process_campaign_creation(
            campaign=campaign,
            leads=leads,
            session_id=session_id
        )
        return result
    except Exception as e:
        agent_logger.log_error(f"Campaign processing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === SESSION STATUS ===

@app.get("/api/sessions/{session_id}", tags=["Sessions"])
async def get_session_status(session_id: str):
    """Get status of a processing session"""
    swarm = get_swarm_manager()
    result = swarm.get_session_status(session_id)
    
    if not result or not result.get("session"):
        raise HTTPException(status_code=404, detail="Session not found")
    
    return result


# Main entry point
if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    debug = os.getenv("DEBUG", "false").lower() == "true"
    
    uvicorn.run(
        "api_server:app",
        host=host,
        port=port,
        reload=debug
    )
