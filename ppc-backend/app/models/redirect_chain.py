"""
Redirect Chain — the Admin-configured pairing of Anchor + Inter + Prelander Pool
+ status, per the Domain Glossary.

Field names follow the glossary: `anchor_domain`, `inter_domain`,
`prelander_pool`. Documents written before migration 005 still carry the older
`intermediate_domain` / `pre_lander_pool` keys, so read stored chains through
`chain_inter_domain()` and `chain_prelander_pool()` rather than indexing them
directly. Request bodies accept either spelling.
"""
from pydantic import AliasChoices, BaseModel, ConfigDict, Field
from typing import Any, Dict, List, Optional
from datetime import datetime
from enum import Enum

# Legacy document/payload keys, kept only so pre-migration data still reads.
LEGACY_INTER_DOMAIN_KEY = "intermediate_domain"
LEGACY_PRELANDER_POOL_KEY = "pre_lander_pool"


def chain_inter_domain(chain: Dict[str, Any]) -> Optional[str]:
    """Read a chain's Inter domain from either the canonical or legacy key."""
    if not chain:
        return None
    return chain.get("inter_domain") or chain.get(LEGACY_INTER_DOMAIN_KEY)


def chain_prelander_pool(chain: Dict[str, Any]) -> List[str]:
    """Read a chain's Prelander Pool from either the canonical or legacy key."""
    if not chain:
        return []
    pool = chain.get("prelander_pool")
    if pool is None:
        pool = chain.get(LEGACY_PRELANDER_POOL_KEY)
    return list(pool or [])


class RedirectChainStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class RedirectChain(BaseModel):
    """Redirect Chain Model for 3-tier routing flow"""
    
    id: Optional[str] = Field(None, alias="_id")
    name: str = Field(..., description="Chain name for identification")
    anchor_domain: str = Field(..., description="Anchor: entry domain that generates session cookies")
    inter_domain: str = Field(
        ...,
        description="Inter: middle hop domain that validates cookies",
        validation_alias=AliasChoices("inter_domain", LEGACY_INTER_DOMAIN_KEY),
    )
    prelander_pool: List[str] = Field(
        default_factory=list,
        description="Prelander Pool: prelander domains this chain distributes across",
        validation_alias=AliasChoices("prelander_pool", LEGACY_PRELANDER_POOL_KEY),
    )
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
    
    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)


class CreateRedirectChainRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=100)
    anchor_domain: str = Field(..., min_length=3, max_length=255)
    inter_domain: str = Field(
        ..., min_length=3, max_length=255,
        validation_alias=AliasChoices("inter_domain", LEGACY_INTER_DOMAIN_KEY),
    )
    prelander_pool: List[str] = Field(
        ..., min_length=1, max_length=50,
        validation_alias=AliasChoices("prelander_pool", LEGACY_PRELANDER_POOL_KEY),
    )
    session_validation: bool = Field(True)
    cookie_lifetime: int = Field(60, ge=5, le=1440)  # 5 minutes to 24 hours
    status: RedirectChainStatus = Field(RedirectChainStatus.ACTIVE)


class UpdateRedirectChainRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    anchor_domain: Optional[str] = Field(None, min_length=3, max_length=255)
    inter_domain: Optional[str] = Field(
        None, min_length=3, max_length=255,
        validation_alias=AliasChoices("inter_domain", LEGACY_INTER_DOMAIN_KEY),
    )
    prelander_pool: Optional[List[str]] = Field(
        None, min_length=1, max_length=50,
        validation_alias=AliasChoices("prelander_pool", LEGACY_PRELANDER_POOL_KEY),
    )
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
    inter_timestamp: Optional[datetime] = None
    prelander_timestamp: Optional[datetime] = None
    selected_prelander: Optional[str] = None
    
    # Session status
    is_valid: bool = Field(True)
    blocked_reason: Optional[str] = None
    conversion_timestamp: Optional[datetime] = None
    
    # Metadata
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    
    model_config = ConfigDict(populate_by_name=True)