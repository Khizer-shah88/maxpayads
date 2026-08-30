"""
Models for managing redirection chains and inter-domain routing.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Literal, Dict, Any
from datetime import datetime


class RedirectStep(BaseModel):
    """A single step in a redirection chain."""
    step_order: int = Field(..., ge=1)
    step_type: Literal["domain", "prelander", "offer"] = "domain"
    # For domain steps
    domain: Optional[str] = None
    # For prelander steps  
    prelander_template_id: Optional[str] = None
    # For offer steps
    offer_url: Optional[str] = None
    # Conditional routing rules
    geo_conditions: List[str] = Field(default_factory=list)  # ["US", "GB", "CA"]
    device_conditions: List[str] = Field(default_factory=list)  # ["desktop", "mobile"]
    # Rotation/split testing
    weight: int = Field(default=100, ge=0, le=100)  # Percentage for A/B testing
    # Step-specific options
    delay_seconds: int = Field(default=0, ge=0)  # Delay before redirect
    custom_headers: Dict[str, str] = Field(default_factory=dict)

    @field_validator("domain")
    @classmethod
    def _domain(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().lower().rstrip("/")
        # Strip protocol if supplied
        for proto in ("https://", "http://"):
            if v.startswith(proto):
                v = v[len(proto):]
        return v


class RedirectChain(BaseModel):
    """A complete redirection chain configuration."""
    id: Optional[str] = Field(default=None, alias="_id")
    name: str
    description: Optional[str] = None
    status: Literal["active", "paused", "archived"] = "active"
    # Chain configuration
    entry_domain: str  # The initial domain that starts the chain
    steps: List[RedirectStep] = Field(default_factory=list)
    # Advanced options
    enable_spinning: bool = False  # Enable prelander rotation within chain
    spinning_rules: Dict[str, Any] = Field(default_factory=dict)
    # Fallback settings
    fallback_url: Optional[str] = None
    error_redirect_url: Optional[str] = None
    # Analytics
    total_hits: int = 0
    successful_completions: int = 0
    error_count: int = 0
    # Metadata
    created_by: str  # admin user ID
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"populate_by_name": True}

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = (v or "").strip()
        if len(v) < 2:
            raise ValueError("name must be at least 2 characters")
        return v

    @field_validator("entry_domain")
    @classmethod
    def _entry_domain(cls, v: str) -> str:
        v = v.strip().lower().rstrip("/")
        for proto in ("https://", "http://"):
            if v.startswith(proto):
                v = v[len(proto):]
        return v


class RedirectChainCreate(BaseModel):
    name: str
    description: Optional[str] = None
    entry_domain: str
    steps: List[RedirectStep] = Field(default_factory=list)
    enable_spinning: bool = False
    spinning_rules: Dict[str, Any] = Field(default_factory=dict)
    fallback_url: Optional[str] = None
    error_redirect_url: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = (v or "").strip()
        if len(v) < 2:
            raise ValueError("name must be at least 2 characters")
        return v


class RedirectChainUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    entry_domain: Optional[str] = None
    steps: Optional[List[RedirectStep]] = None
    enable_spinning: Optional[bool] = None
    spinning_rules: Optional[Dict[str, Any]] = None
    fallback_url: Optional[str] = None
    error_redirect_url: Optional[str] = None
    status: Optional[Literal["active", "paused", "archived"]] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = None


class RedirectChainExecution(BaseModel):
    """Log entry for tracking chain execution."""
    id: Optional[str] = Field(default=None, alias="_id")
    chain_id: str
    execution_id: str  # Unique ID for this specific execution
    # Request context
    entry_ip: str
    entry_country: Optional[str] = None
    entry_device: Optional[str] = None
    entry_user_agent: Optional[str] = None
    entry_referrer: Optional[str] = None
    # Execution path
    steps_executed: List[Dict[str, Any]] = Field(default_factory=list)
    current_step: int = 0
    status: Literal["in_progress", "completed", "failed", "timeout"] = "in_progress"
    # Results
    final_destination: Optional[str] = None
    total_redirect_time: Optional[float] = None  # seconds
    error_message: Optional[str] = None
    # Timestamps
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    model_config = {"populate_by_name": True}