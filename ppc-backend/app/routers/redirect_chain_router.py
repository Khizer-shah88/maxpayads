from fastapi import APIRouter, HTTPException, Depends, Query, status
from typing import List, Optional
from datetime import datetime, timedelta
import secrets
import random

from app.database import get_database
from app.dependencies import get_db, get_current_admin
from app.models.redirect_chain import (
    RedirectChain, CreateRedirectChainRequest, UpdateRedirectChainRequest,
    RedirectChainSession, RedirectChainStatus
)

try:
    from app.models.user import User
except ImportError:
    # Fallback if User model has different path
    User = dict


router = APIRouter(prefix="/admin/redirect-chains", tags=["Redirect Chains"])


@router.get("/", response_model=dict)
async def get_redirect_chains(
    status: Optional[RedirectChainStatus] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db = Depends(get_db),
    current_user = Depends(get_current_admin)
):
    """Get all redirect chains with optional filtering"""
    
    # Build query filter
    query_filter = {}
    if status:
        query_filter["status"] = status.value
    
    # Get total count
    total = await db.redirect_chains.count_documents(query_filter)
    
    # Get paginated results
    skip = (page - 1) * limit
    cursor = db.redirect_chains.find(query_filter).skip(skip).limit(limit).sort("created_at", -1)
    chains = await cursor.to_list(length=limit)
    
    # Convert ObjectId to string for response
    for chain in chains:
        chain["id"] = str(chain["_id"])
        del chain["_id"]
    
    return {
        "chains": chains,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "pages": (total + limit - 1) // limit
        }
    }


@router.post("/", response_model=dict)
async def create_redirect_chain(
    request: CreateRedirectChainRequest,
    db = Depends(get_db),
    current_user = Depends(get_current_admin)
):
    """Create a new redirect chain"""
    
    # Check if chain name already exists
    existing = await db.redirect_chains.find_one({"name": request.name})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A redirect chain with this name already exists"
        )
    
    # Validate that domains exist in redirection_domains collection
    anchor_domain = await db.redirection_domains.find_one({
        "domain": request.anchor_domain,
        "domain_type": "link",
        "status": "active"
    })
    if not anchor_domain:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Anchor domain '{request.anchor_domain}' not found or not active"
        )
    
    intermediate_domain = await db.redirection_domains.find_one({
        "domain": request.intermediate_domain,
        "domain_type": "intermediate", 
        "status": "active"
    })
    if not intermediate_domain:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Intermediate domain '{request.intermediate_domain}' not found or not active"
        )
    
    # Validate pre-lander domains
    for domain in request.pre_lander_pool:
        prelander_domain = await db.redirection_domains.find_one({
            "domain": domain,
            "domain_type": "last",
            "status": "active"
        })
        if not prelander_domain:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Pre-lander domain '{domain}' not found or not active"
            )
    
    # Create new chain
    now = datetime.utcnow()
    chain_data = {
        "name": request.name,
        "anchor_domain": request.anchor_domain,
        "intermediate_domain": request.intermediate_domain,
        "pre_lander_pool": request.pre_lander_pool,
        "session_validation": request.session_validation,
        "cookie_lifetime": request.cookie_lifetime,
        "status": request.status.value,
        "total_sessions": 0,
        "valid_sessions": 0,
        "blocked_sessions": 0,
        "conversion_rate": 0.0,
        "created_at": now,
        "updated_at": now,
        "created_by": str(current_user.get("id", current_user.get("_id", "")))
    }
    
    result = await db.redirect_chains.insert_one(chain_data)
    chain_data["id"] = str(result.inserted_id)
    if "_id" in chain_data:
        del chain_data["_id"]
    
    return {
        "success": True,
        "message": "Redirect chain created successfully",
        "chain": chain_data
    }


@router.get("/{chain_id}", response_model=dict)
async def get_redirect_chain(
    chain_id: str,
    db = Depends(get_db),
    current_user = Depends(get_current_admin)
):
    """Get a specific redirect chain by ID"""
    
    from bson import ObjectId
    try:
        object_id = ObjectId(chain_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid chain ID format")
    
    chain = await db.redirect_chains.find_one({"_id": object_id})
    if not chain:
        raise HTTPException(status_code=404, detail="Redirect chain not found")
    
    chain["id"] = str(chain["_id"])
    del chain["_id"]
    
    return {"chain": chain}


@router.put("/{chain_id}", response_model=dict)
async def update_redirect_chain(
    chain_id: str,
    request: UpdateRedirectChainRequest,
    db = Depends(get_db),
    current_user = Depends(get_current_admin)
):
    """Update an existing redirect chain"""
    
    from bson import ObjectId
    try:
        object_id = ObjectId(chain_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid chain ID format")
    
    # Check if chain exists
    existing_chain = await db.redirect_chains.find_one({"_id": object_id})
    if not existing_chain:
        raise HTTPException(status_code=404, detail="Redirect chain not found")
    
    # Build update data
    update_data = {"updated_at": datetime.utcnow()}
    
    if request.name is not None:
        # Check name uniqueness (excluding current chain)
        name_exists = await db.redirect_chains.find_one({
            "name": request.name,
            "_id": {"$ne": object_id}
        })
        if name_exists:
            raise HTTPException(
                status_code=400,
                detail="A redirect chain with this name already exists"
            )
        update_data["name"] = request.name
    
    if request.anchor_domain is not None:
        anchor_domain = await db.redirection_domains.find_one({
            "domain": request.anchor_domain,
            "domain_type": "link",
            "status": "active"
        })
        if not anchor_domain:
            raise HTTPException(
                status_code=400,
                detail=f"Anchor domain '{request.anchor_domain}' not found or not active"
            )
        update_data["anchor_domain"] = request.anchor_domain
    
    if request.intermediate_domain is not None:
        intermediate_domain = await db.redirection_domains.find_one({
            "domain": request.intermediate_domain,
            "domain_type": "intermediate",
            "status": "active"
        })
        if not intermediate_domain:
            raise HTTPException(
                status_code=400,
                detail=f"Intermediate domain '{request.intermediate_domain}' not found or not active"
            )
        update_data["intermediate_domain"] = request.intermediate_domain
    
    if request.pre_lander_pool is not None:
        for domain in request.pre_lander_pool:
            prelander_domain = await db.redirection_domains.find_one({
                "domain": domain,
                "domain_type": "last",
                "status": "active"
            })
            if not prelander_domain:
                raise HTTPException(
                    status_code=400,
                    detail=f"Pre-lander domain '{domain}' not found or not active"
                )
        update_data["pre_lander_pool"] = request.pre_lander_pool
    
    if request.session_validation is not None:
        update_data["session_validation"] = request.session_validation
    
    if request.cookie_lifetime is not None:
        update_data["cookie_lifetime"] = request.cookie_lifetime
    
    if request.status is not None:
        update_data["status"] = request.status.value
    
    # Update the chain
    await db.redirect_chains.update_one(
        {"_id": object_id},
        {"$set": update_data}
    )
    
    # Return updated chain
    updated_chain = await db.redirect_chains.find_one({"_id": object_id})
    updated_chain["id"] = str(updated_chain["_id"])
    del updated_chain["_id"]
    
    return {
        "success": True,
        "message": "Redirect chain updated successfully",
        "chain": updated_chain
    }


@router.delete("/{chain_id}", response_model=dict)
async def delete_redirect_chain(
    chain_id: str,
    db = Depends(get_db),
    current_user = Depends(get_current_admin)
):
    """Delete a redirect chain"""
    
    from bson import ObjectId
    try:
        object_id = ObjectId(chain_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid chain ID format")
    
    # Check if chain exists
    existing_chain = await db.redirect_chains.find_one({"_id": object_id})
    if not existing_chain:
        raise HTTPException(status_code=404, detail="Redirect chain not found")
    
    # Delete the chain
    await db.redirect_chains.delete_one({"_id": object_id})
    
    # Clean up associated sessions
    await db.redirect_chain_sessions.delete_many({"chain_id": chain_id})
    
    return {
        "success": True,
        "message": "Redirect chain deleted successfully"
    }


@router.post("/{chain_id}/sessions", response_model=dict)
async def create_chain_session(
    chain_id: str,
    visitor_ip: str,
    user_agent: str,
    db = Depends(get_db)
):
    """Create a new session for a redirect chain (called from anchor domain)"""
    
    from bson import ObjectId
    try:
        object_id = ObjectId(chain_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid chain ID format")
    
    # Get chain
    chain = await db.redirect_chains.find_one({"_id": object_id})
    if not chain or chain.get("status") != "active":
        raise HTTPException(status_code=404, detail="Redirect chain not found or inactive")
    
    # Generate session token
    session_token = secrets.token_urlsafe(32)
    
    # Calculate expiration
    now = datetime.utcnow()
    expires_at = now + timedelta(minutes=chain["cookie_lifetime"])
    
    # Select random pre-lander domain
    selected_prelander = random.choice(chain["pre_lander_pool"])
    
    # Create session
    session_data = {
        "chain_id": chain_id,
        "session_token": session_token,
        "visitor_ip": visitor_ip,
        "user_agent": user_agent,
        "anchor_timestamp": now,
        "selected_prelander": selected_prelander,
        "is_valid": True,
        "created_at": now,
        "expires_at": expires_at
    }
    
    await db.redirect_chain_sessions.insert_one(session_data)
    
    # Update chain stats
    await db.redirect_chains.update_one(
        {"_id": object_id},
        {"$inc": {"total_sessions": 1}}
    )
    
    return {
        "success": True,
        "session_token": session_token,
        "intermediate_domain": chain["intermediate_domain"],
        "expires_at": expires_at.isoformat()
    }


@router.post("/{chain_id}/validate", response_model=dict)
async def validate_chain_session(
    chain_id: str,
    session_token: str,
    step: str,  # "intermediate" or "prelander"
    visitor_ip: str,
    user_agent: str,
    db = Depends(get_db)
):
    """Validate session token and return next step (called from intermediate/prelander domains)"""
    
    # Find session
    session = await db.redirect_chain_sessions.find_one({
        "chain_id": chain_id,
        "session_token": session_token,
        "is_valid": True
    })
    
    if not session:
        await db.redirect_chains.update_one(
            {"_id": ObjectId(chain_id)},
            {"$inc": {"blocked_sessions": 1}}
        )
        raise HTTPException(status_code=403, detail="Invalid or expired session")
    
    # Check expiration
    if datetime.utcnow() > session["expires_at"]:
        await db.redirect_chain_sessions.update_one(
            {"_id": session["_id"]},
            {"$set": {"is_valid": False, "blocked_reason": "expired"}}
        )
        await db.redirect_chains.update_one(
            {"_id": ObjectId(chain_id)},
            {"$inc": {"blocked_sessions": 1}}
        )
        raise HTTPException(status_code=403, detail="Session expired")
    
    # Validate IP and User-Agent (basic fingerprinting)
    if session["visitor_ip"] != visitor_ip or session["user_agent"] != user_agent:
        await db.redirect_chain_sessions.update_one(
            {"_id": session["_id"]},
            {"$set": {"is_valid": False, "blocked_reason": "fingerprint_mismatch"}}
        )
        await db.redirect_chains.update_one(
            {"_id": ObjectId(chain_id)},
            {"$inc": {"blocked_sessions": 1}}
        )
        raise HTTPException(status_code=403, detail="Session validation failed")
    
    # Update session step
    now = datetime.utcnow()
    update_data = {}
    
    if step == "intermediate" and not session.get("intermediate_timestamp"):
        update_data["intermediate_timestamp"] = now
    elif step == "prelander" and not session.get("prelander_timestamp"):
        update_data["prelander_timestamp"] = now
        # Update valid sessions count
        await db.redirect_chains.update_one(
            {"_id": ObjectId(chain_id)},
            {"$inc": {"valid_sessions": 1}}
        )
    
    if update_data:
        await db.redirect_chain_sessions.update_one(
            {"_id": session["_id"]},
            {"$set": update_data}
        )
    
    return {
        "success": True,
        "valid": True,
        "selected_prelander": session["selected_prelander"],
        "next_step": "prelander" if step == "intermediate" else "complete"
    }


@router.get("/{chain_id}/stats", response_model=dict)
async def get_chain_stats(
    chain_id: str,
    days: int = Query(30, ge=1, le=365),
    db = Depends(get_db),
    current_user = Depends(get_current_admin)
):
    """Get detailed statistics for a redirect chain"""
    
    from bson import ObjectId
    try:
        object_id = ObjectId(chain_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid chain ID format")
    
    chain = await db.redirect_chains.find_one({"_id": object_id})
    if not chain:
        raise HTTPException(status_code=404, detail="Redirect chain not found")
    
    # Date range for stats
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    # Aggregate session statistics
    pipeline = [
        {
            "$match": {
                "chain_id": chain_id,
                "created_at": {"$gte": start_date, "$lte": end_date}
            }
        },
        {
            "$group": {
                "_id": {
                    "$dateToString": {
                        "format": "%Y-%m-%d",
                        "date": "$created_at"
                    }
                },
                "total": {"$sum": 1},
                "valid": {
                    "$sum": {
                        "$cond": [{"$eq": ["$is_valid", True]}, 1, 0]
                    }
                },
                "blocked": {
                    "$sum": {
                        "$cond": [{"$eq": ["$is_valid", False]}, 1, 0]
                    }
                },
                "completed": {
                    "$sum": {
                        "$cond": [{"$ne": ["$prelander_timestamp", None]}, 1, 0]
                    }
                }
            }
        },
        {"$sort": {"_id": 1}}
    ]
    
    daily_stats = await db.redirect_chain_sessions.aggregate(pipeline).to_list(length=None)
    
    return {
        "chain": {
            "id": str(chain["_id"]),
            "name": chain["name"],
            "status": chain["status"]
        },
        "summary": {
            "total_sessions": chain["total_sessions"],
            "valid_sessions": chain["valid_sessions"],
            "blocked_sessions": chain["blocked_sessions"],
            "conversion_rate": chain["conversion_rate"]
        },
        "daily_breakdown": daily_stats,
        "date_range": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "days": days
        }
    }