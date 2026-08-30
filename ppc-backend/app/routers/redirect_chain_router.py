"""
Router for Redirect Chain Management - Sequential Domain Routing System.

This router provides endpoints for:
1. Creating and managing redirection chains (Anchor Domain A → Inter-Domain B → Pre-Lander C → Target Offer)
2. Executing redirection chains with prelander spinning/rotation integration
3. Tracking chain performance and debugging failed redirections
"""
from fastapi import APIRouter, Depends, Query, HTTPException, Request
from fastapi.responses import RedirectResponse
from typing import Optional, List
from datetime import datetime, timedelta
from app.models.redirect_chain import (
    RedirectChain, RedirectChainCreate, RedirectChainUpdate,
    RedirectChainExecution, RedirectStep
)
from app.dependencies import get_db, get_current_admin
from app.core.exceptions import NotFoundError
from bson import ObjectId
import logging
import uuid
import asyncio
import time

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/redirect-chains", tags=["Redirect Chains"])


@router.get("/")
async def get_redirect_chains(
    status: Optional[str] = Query(None, description="Filter by status"),
    entry_domain: Optional[str] = Query(None, description="Filter by entry domain"),
    current_user: dict = Depends(get_current_admin),
    db = Depends(get_db),
):
    """Get all redirect chains with optional filtering."""
    try:
        query = {}
        if status:
            query["status"] = status
        if entry_domain:
            query["entry_domain"] = {"$regex": entry_domain, "$options": "i"}
        
        cursor = db.redirect_chains.find(query).sort("created_at", -1)
        chains = await cursor.to_list(length=None)
        
        for chain in chains:
            chain["id"] = str(chain.pop("_id", ""))
            if chain.get("created_at"):
                chain["created_at"] = chain["created_at"].isoformat()
            if chain.get("updated_at"):
                chain["updated_at"] = chain["updated_at"].isoformat()
        
        return {"success": True, "chains": chains}
    
    except Exception as e:
        logger.error(f"Error fetching redirect chains: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch redirect chains")
            if chain.get("updated_at"):
                chain["updated_at"] = chain["updated_at"].isoformat()
        
        return chains
    
    except Exception as e:
        logger.error(f"Error fetching redirect chains: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch redirect chains")


@router.post("/", response_model=RedirectChain)
async def create_redirect_chain(
    data: RedirectChainCreate,
    current_user: dict = Depends(get_current_admin),
    db = Depends(get_db),
):
    """Create a new redirect chain."""
    try:
        # Check if entry domain already has a chain
        existing = await db.redirect_chains.find_one({
            "entry_domain": data.entry_domain.lower(),
            "status": {"$ne": "archived"}
        })
        
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Active redirect chain already exists for domain {data.entry_domain}"
            )
        
        # Validate steps
        if data.steps:
            for i, step in enumerate(data.steps, 1):
                if step.step_order != i:
                    step.step_order = i
                
                # Validate step configuration
                if step.step_type == "domain" and not step.domain:
                    raise HTTPException(status_code=400, detail=f"Step {i}: domain required for domain step")
                elif step.step_type == "prelander" and not step.prelander_template_id:
                    raise HTTPException(status_code=400, detail=f"Step {i}: prelander_template_id required for prelander step")
                elif step.step_type == "offer" and not step.offer_url:
                    raise HTTPException(status_code=400, detail=f"Step {i}: offer_url required for offer step")
        
        # Create chain
        chain_data = data.model_dump()
        chain_data.update({
            "created_by": current_user.get("id"),
            "total_hits": 0,
            "successful_completions": 0,
            "error_count": 0,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        })
        
        result = await db.redirect_chains.insert_one(chain_data)
        chain_data["id"] = str(result.inserted_id)
        chain_data["created_at"] = chain_data["created_at"].isoformat()
        chain_data["updated_at"] = chain_data["updated_at"].isoformat()
        
        return chain_data
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating redirect chain: {e}")
        raise HTTPException(status_code=500, detail="Failed to create redirect chain")


@router.get("/{chain_id}", response_model=RedirectChain)
async def get_redirect_chain(
    chain_id: str,
    current_user: dict = Depends(get_current_admin),
    db = Depends(get_db),
):
    """Get a specific redirect chain."""
    try:
        chain = await db.redirect_chains.find_one({"_id": ObjectId(chain_id)})
        if not chain:
            raise NotFoundError("Redirect Chain")
        
        chain["id"] = str(chain.pop("_id"))
        if chain.get("created_at"):
            chain["created_at"] = chain["created_at"].isoformat()
        if chain.get("updated_at"):
            chain["updated_at"] = chain["updated_at"].isoformat()
        
        return chain
    
    except Exception as e:
        logger.error(f"Error fetching redirect chain: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch redirect chain")


@router.put("/{chain_id}", response_model=RedirectChain)
async def update_redirect_chain(
    chain_id: str,
    data: RedirectChainUpdate,
    current_user: dict = Depends(get_current_admin),
    db = Depends(get_db),
):
    """Update a redirect chain."""
    try:
        update_data = {k: v for k, v in data.model_dump().items() if v is not None}
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        update_data["updated_at"] = datetime.utcnow()
        
        result = await db.redirect_chains.update_one(
            {"_id": ObjectId(chain_id)},
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            raise NotFoundError("Redirect Chain")
        
        # Return updated chain
        return await get_redirect_chain(chain_id, current_user, db)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating redirect chain: {e}")
        raise HTTPException(status_code=500, detail="Failed to update redirect chain")


@router.delete("/{chain_id}")
async def delete_redirect_chain(
    chain_id: str,
    current_user: dict = Depends(get_current_admin),
    db = Depends(get_db),
):
    """Archive a redirect chain (soft delete)."""
    try:
        result = await db.redirect_chains.update_one(
            {"_id": ObjectId(chain_id)},
            {"$set": {"status": "archived", "updated_at": datetime.utcnow()}}
        )
        
        if result.matched_count == 0:
            raise NotFoundError("Redirect Chain")
        
        return {"success": True, "message": "Redirect chain archived"}
    
    except Exception as e:
        logger.error(f"Error archiving redirect chain: {e}")
        raise HTTPException(status_code=500, detail="Failed to archive redirect chain")


@router.post("/{chain_id}/execute")
async def execute_redirect_chain(
    chain_id: str,
    request: Request,
    current_user: dict = Depends(get_current_admin),
    db = Depends(get_db),
):
    """Execute a redirect chain (admin testing endpoint)."""
    try:
        chain = await db.redirect_chains.find_one({"_id": ObjectId(chain_id)})
        if not chain:
            raise NotFoundError("Redirect Chain")
        
        if chain.get("status") != "active":
            raise HTTPException(status_code=400, detail="Chain is not active")
        
        # Get client info
        client_ip = request.client.host
        user_agent = request.headers.get("User-Agent", "")
        referrer = request.headers.get("Referer", "")
        
        # Execute chain
        execution_result = await _execute_chain(chain, client_ip, user_agent, referrer, db)
        
        if execution_result.get("final_destination"):
            return RedirectResponse(url=execution_result["final_destination"])
        else:
            return {
                "success": False,
                "message": "Chain execution failed",
                "error": execution_result.get("error", "Unknown error")
            }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing redirect chain: {e}")
        raise HTTPException(status_code=500, detail="Failed to execute redirect chain")


@router.get("/{chain_id}/executions")
async def get_chain_executions(
    chain_id: str,
    limit: int = Query(50, ge=1, le=500),
    status: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_admin),
    db = Depends(get_db),
):
    """Get execution logs for a specific chain."""
    try:
        query = {"chain_id": chain_id}
        if status:
            query["status"] = status
        
        cursor = db.redirect_chain_executions.find(query).sort("started_at", -1).limit(limit)
        executions = await cursor.to_list(length=None)
        
        for execution in executions:
            execution["id"] = str(execution.pop("_id", ""))
            if execution.get("started_at"):
                execution["started_at"] = execution["started_at"].isoformat()
            if execution.get("completed_at"):
                execution["completed_at"] = execution["completed_at"].isoformat()
        
        return {
            "success": True,
            "executions": executions,
            "total": len(executions)
        }
    
    except Exception as e:
        logger.error(f"Error fetching chain executions: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch chain executions")


@router.get("/{chain_id}/analytics")
async def get_chain_analytics(
    chain_id: str,
    days: int = Query(7, ge=1, le=90),
    current_user: dict = Depends(get_current_admin),
    db = Depends(get_db),
):
    """Get analytics for a specific chain."""
    try:
        # Get chain info
        chain = await db.redirect_chains.find_one({"_id": ObjectId(chain_id)})
        if not chain:
            raise NotFoundError("Redirect Chain")
        
        # Calculate date range
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Aggregate execution data
        pipeline = [
            {
                "$match": {
                    "chain_id": chain_id,
                    "started_at": {"$gte": start_date}
                }
            },
            {
                "$group": {
                    "_id": {
                        "$dateToString": {"format": "%Y-%m-%d", "date": "$started_at"}
                    },
                    "total_executions": {"$sum": 1},
                    "successful": {
                        "$sum": {"$cond": [{"$eq": ["$status", "completed"]}, 1, 0]}
                    },
                    "failed": {
                        "$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}
                    },
                    "avg_redirect_time": {"$avg": "$total_redirect_time"}
                }
            },
            {"$sort": {"_id": 1}}
        ]
        
        daily_stats = await db.redirect_chain_executions.aggregate(pipeline).to_list(length=None)
        
        # Overall stats
        total_executions = sum(day["total_executions"] for day in daily_stats)
        total_successful = sum(day["successful"] for day in daily_stats)
        success_rate = (total_successful / total_executions * 100) if total_executions > 0 else 0
        
        return {
            "success": True,
            "chain_name": chain.get("name", ""),
            "analytics": {
                "total_executions": total_executions,
                "successful_completions": total_successful,
                "success_rate": round(success_rate, 2),
                "daily_breakdown": daily_stats,
                "date_range": {
                    "from": start_date.strftime("%Y-%m-%d"),
                    "to": datetime.utcnow().strftime("%Y-%m-%d"),
                }
            }
        }
    
    except Exception as e:
        logger.error(f"Error getting chain analytics: {e}")
        raise HTTPException(status_code=500, detail="Failed to get chain analytics")


# Internal helper function
async def _execute_chain(chain: dict, client_ip: str, user_agent: str, referrer: str, db) -> dict:
    """Execute a redirect chain step by step."""
    execution_id = str(uuid.uuid4())
    start_time = time.time()
    
    # Create execution log
    execution_log = {
        "chain_id": str(chain["_id"]),
        "execution_id": execution_id,
        "entry_ip": client_ip,
        "entry_user_agent": user_agent,
        "entry_referrer": referrer,
        "steps_executed": [],
        "current_step": 0,
        "status": "in_progress",
        "started_at": datetime.utcnow(),
    }
    
    try:
        # Increment chain hit counter
        await db.redirect_chains.update_one(
            {"_id": chain["_id"]},
            {"$inc": {"total_hits": 1}}
        )
        
        steps = chain.get("steps", [])
        if not steps:
            raise Exception("No steps defined in chain")
        
        current_url = None
        
        for i, step in enumerate(steps):
            execution_log["current_step"] = i + 1
            step_start = time.time()
            
            step_result = {
                "step_order": step["step_order"],
                "step_type": step["step_type"],
                "started_at": datetime.utcnow().isoformat(),
            }
            
            try:
                # Apply delay if specified
                if step.get("delay_seconds", 0) > 0:
                    await asyncio.sleep(step["delay_seconds"])
                
                # Execute step based on type
                if step["step_type"] == "domain":
                    current_url = f"https://{step['domain']}"
                    step_result["destination"] = current_url
                
                elif step["step_type"] == "prelander":
                    # Handle prelander with template
                    template_id = step.get("prelander_template_id")
                    if template_id:
                        template = await db.prelander_templates.find_one({"_id": ObjectId(template_id)})
                        if template and template.get("status") == "active":
                            # Check for spinning/rotation if enabled
                            if chain.get("enable_spinning"):
                                # Could implement template rotation logic here
                                pass
                            current_url = f"https://{chain['entry_domain']}/d/{template_id}"
                        else:
                            raise Exception(f"Template {template_id} not found or inactive")
                    step_result["destination"] = current_url
                
                elif step["step_type"] == "offer":
                    current_url = step["offer_url"]
                    step_result["destination"] = current_url
                
                step_result["completed_at"] = datetime.utcnow().isoformat()
                step_result["execution_time"] = time.time() - step_start
                step_result["status"] = "completed"
                
            except Exception as step_error:
                step_result["error"] = str(step_error)
                step_result["status"] = "failed"
                step_result["completed_at"] = datetime.utcnow().isoformat()
                execution_log["steps_executed"].append(step_result)
                raise step_error
            
            execution_log["steps_executed"].append(step_result)
        
        # Chain completed successfully
        execution_log["status"] = "completed"
        execution_log["final_destination"] = current_url
        execution_log["total_redirect_time"] = time.time() - start_time
        execution_log["completed_at"] = datetime.utcnow()
        
        # Update chain success counter
        await db.redirect_chains.update_one(
            {"_id": chain["_id"]},
            {"$inc": {"successful_completions": 1}}
        )
        
        return {
            "success": True,
            "final_destination": current_url,
            "execution_time": execution_log["total_redirect_time"]
        }
    
    except Exception as e:
        # Chain execution failed
        execution_log["status"] = "failed"
        execution_log["error_message"] = str(e)
        execution_log["completed_at"] = datetime.utcnow()
        execution_log["total_redirect_time"] = time.time() - start_time
        
        # Update chain error counter
        await db.redirect_chains.update_one(
            {"_id": chain["_id"]},
            {"$inc": {"error_count": 1}}
        )
        
        return {
            "success": False,
            "error": str(e),
            "execution_time": execution_log["total_redirect_time"]
        }
    
    finally:
        # Save execution log
        await db.redirect_chain_executions.insert_one(execution_log)