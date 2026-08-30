from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from enum import Enum


class RedirectChainStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class RedirectChain(BaseModel):
    """Redirect Chain Model for 3-tier routing flow"""
    
    id: Optional[str] = Field(None, alias="_id")
    name: str = Field(..., description="Chain name for identification")
    anchor_domain: str = Field(..., description="Entry point domain that generates session cookies")
    intermediate_domain: str = Field(..., description="Middle hop domain that validates cookies")
    pre_lander_pool: List[str] = Field(default_factory=list, description="Pool of pre-lander domains for rotation")
    session_validation: bool = Field(True, description="Whether to enforce session cookie validation")
    cookie_lifetime: int = Field(60, description="Cookie lifetime in minutes")
    status: RedirectChainStatus = Field(RedirectChainStatus.ACTIVE)
    
    # Statistics
    total_sessions: int = Field(0, description="Total sessions initiated")
    valid_sessions: int = Field(0, description="Sessions that passed validation")
    blocked_sessions: int = Field(0, description="Sessions blocked due to validation failure")
    conversion_rate: float = Field(0.0, description="Conversion rate percentage")
    
    # Metadata
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None
    
    class Config:
        allow_population_by_field_name = True
        use_enum_values = True


class CreateRedirectChainRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    anchor_domain: str = Field(..., min_length=3, max_length=255)
    intermediate_domain: str = Field(..., min_length=3, max_length=255)
    pre_lander_pool: List[str] = Field(..., min_items=1, max_items=50)
    session_validation: bool = Field(True)
    cookie_lifetime: int = Field(60, ge=5, le=1440)  # 5 minutes to 24 hours
    status: RedirectChainStatus = Field(RedirectChainStatus.ACTIVE)


class UpdateRedirectChainRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    anchor_domain: Optional[str] = Field(None, min_length=3, max_length=255)
    intermediate_domain: Optional[str] = Field(None, min_length=3, max_length=255)
    pre_lander_pool: Optional[List[str]] = Field(None, min_items=1, max_items=50)
    session_validation: Optional[bool] = None
    cookie_lifetime: Optional[int] = Field(None, ge=5, le=1440)
    status: Optional[RedirectChainStatus] = None


class RedirectChainSession(BaseModel):
    """Model for tracking redirect chain sessions"""
    
    id: Optional[str] = Field(None, alias="_id")
    chain_id: str = Field(..., description="Associated redirect chain ID")
    session_token: str = Field(..., description="Unique session identifier")
    visitor_ip: str = Field(..., description="Visitor IP address")
    user_agent: str = Field(..., description="Visitor user agent")
    
    # Flow tracking
    anchor_timestamp: Optional[datetime] = None
    intermediate_timestamp: Optional[datetime] = None
    prelander_timestamp: Optional[datetime] = None
    selected_prelander: Optional[str] = None
    
    # Session status
    is_valid: bool = Field(True)
    blocked_reason: Optional[str] = None
    conversion_timestamp: Optional[datetime] = None
    
    # Metadata
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    
    class Config:
        allow_population_by_field_name = True