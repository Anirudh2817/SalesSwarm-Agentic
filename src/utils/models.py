"""
Pydantic models for SalesSwarm-Agentic
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


# Enums
class LeadStatus(str, Enum):
    NEW = "new"
    ENRICHED = "enriched"
    QUALIFIED = "qualified"
    CONTACTED = "contacted"
    RESPONDED = "responded"
    CONVERTED = "converted"
    UNRESPONSIVE = "unresponsive"


class CampaignStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class EmailType(str, Enum):
    INTRODUCTION = "introduction"
    FOLLOW_UP = "follow_up"
    FINAL = "final"


# Lead Models
class LeadProfile(BaseModel):
    """Lead/prospect profile data"""
    id: Optional[str] = None
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    title: Optional[str] = None
    company: Optional[str] = None
    company_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    location: Optional[str] = None
    industry: Optional[str] = None
    company_size: Optional[str] = None
    status: LeadStatus = LeadStatus.NEW
    
    # Enriched data
    headline: Optional[str] = None
    summary: Optional[str] = None
    experience: Optional[List[Dict[str, Any]]] = None
    skills: Optional[List[str]] = None
    
    # Metadata
    enriched_at: Optional[datetime] = None
    source: Optional[str] = None
    
    class Config:
        use_enum_values = True


class LeadEnrichmentRequest(BaseModel):
    """Request to enrich lead data"""
    linkedin_urls: List[str] = Field(..., min_length=1)
    session_id: Optional[str] = None


class LeadEnrichmentResponse(BaseModel):
    """Response with enriched lead data"""
    leads: List[LeadProfile]
    success: bool
    errors: Optional[List[str]] = None


# Lookalike Models
class LookalikeRequest(BaseModel):
    """Request to find lookalike leads"""
    profile_urls: List[str] = Field(..., min_length=1, max_length=5)
    max_leads: int = Field(default=100, ge=25, le=1000)
    job_titles: Optional[List[str]] = None
    locations: Optional[List[str]] = None
    industries: Optional[List[str]] = None
    company_sizes: Optional[List[str]] = None


class LookalikeResponse(BaseModel):
    """Response with lookalike leads"""
    leads: List[LeadProfile]
    icp_summary: str  # Ideal Customer Profile summary
    match_criteria: Dict[str, Any]
    total_found: int


# Campaign Models
class CampaignData(BaseModel):
    """Campaign data model"""
    id: Optional[str] = None
    name: str
    goal: str
    status: CampaignStatus = CampaignStatus.DRAFT
    channel: str = "email"
    
    # Targeting
    target_industry: Optional[str] = None
    target_location: Optional[str] = None
    target_titles: Optional[List[str]] = None
    
    # Scheduling
    timezone: str = "America/New_York"
    send_date: Optional[str] = None
    send_time: str = "09:00"
    use_recipient_timezone: bool = False
    
    # Content
    attachments: Optional[List[str]] = None
    
    # Metadata
    created_at: Optional[datetime] = None
    author_id: Optional[str] = None
    
    class Config:
        use_enum_values = True


# Email Models
class EmailContent(BaseModel):
    """Individual email content"""
    step: int
    type: EmailType
    subject: str
    body: str
    personalization_tokens: Optional[List[str]] = None
    delay_days: int = 0  # Days after previous email


class EmailSequence(BaseModel):
    """Complete email sequence for a campaign"""
    campaign_id: str
    lead_id: str
    emails: List[EmailContent]
    
    # Personalization context
    lead_name: str
    company_name: Optional[str] = None
    lead_insights: Optional[str] = None
    company_insights: Optional[str] = None


class EmailGenerationRequest(BaseModel):
    """Request to generate email sequence"""
    campaign_goal: str
    lead: LeadProfile
    company_insights: Optional[str] = None
    tone: str = "professional"
    num_followups: int = Field(default=2, ge=1, le=5)
    include_personalization: bool = True


class EmailGenerationResponse(BaseModel):
    """Response with generated emails"""
    sequence: EmailSequence
    success: bool
    generation_metadata: Optional[Dict[str, Any]] = None


# Qualification Models
class QualificationCriteria(BaseModel):
    """Criteria for lead qualification"""
    target_titles: Optional[List[str]] = None
    target_industries: Optional[List[str]] = None
    target_locations: Optional[List[str]] = None
    min_company_size: Optional[int] = None
    max_company_size: Optional[int] = None
    required_keywords: Optional[List[str]] = None


class QualificationResult(BaseModel):
    """Result of lead qualification"""
    lead_id: str
    score: int = Field(..., ge=0, le=100)
    qualified: bool
    reasoning: str
    
    # Score breakdown
    title_match_score: int = 0
    industry_match_score: int = 0
    location_match_score: int = 0
    company_size_score: int = 0
    
    # Recommendations
    recommended_approach: Optional[str] = None
    priority_level: str = "medium"  # low, medium, high


class QualificationRequest(BaseModel):
    """Request to qualify leads"""
    leads: List[LeadProfile]
    criteria: QualificationCriteria
    campaign_id: Optional[str] = None


class QualificationResponse(BaseModel):
    """Response with qualification results"""
    results: List[QualificationResult]
    summary: Dict[str, int]  # e.g., {"qualified": 5, "not_qualified": 3}


# Company Intelligence Models
class CompanyIntelligence(BaseModel):
    """Company intelligence data"""
    company_name: str
    website: Optional[str] = None
    industry: Optional[str] = None
    description: Optional[str] = None
    products_services: Optional[List[str]] = None
    recent_news: Optional[List[str]] = None
    challenges: Optional[List[str]] = None
    opportunities: Optional[List[str]] = None
    competitors: Optional[List[str]] = None
    
    # Scraped metadata
    scraped_at: Optional[datetime] = None
    source_url: Optional[str] = None


class CompanyIntelRequest(BaseModel):
    """Request for company intelligence"""
    company_url: str
    company_name: Optional[str] = None
    include_news: bool = True
    include_competitors: bool = False


class CompanyIntelResponse(BaseModel):
    """Response with company intelligence"""
    intelligence: CompanyIntelligence
    success: bool
    errors: Optional[List[str]] = None
