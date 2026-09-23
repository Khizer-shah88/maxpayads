from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from app.dependencies import get_db, get_current_admin
from app.schemas.redirection_domain_schema import (
    RedirectionDomainCreate,
    RedirectionDomainUpdate,
    RedirectionDomainStatusToggle,
)
from app.services import domain_service
from app.core.exceptions import NotFoundError

router = APIRouter(prefix="/admin/redirection-domains", tags=["Redirection Domains"])


@router.get("")
async def list_redirection_domains(
    domain_type: Optional[str] = Query(None, description="anchor | inter | prelander"),
    status: Optional[str] = Query(None),
    publisher_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    domains = await domain_service.list_domains(db, domain_type, status, publisher_id)
    instructions = await domain_service.get_dns_instructions(db)
    return {
        "success": True,
        "domains": domains,
        "total": len(domains),
        "dns_instructions": instructions,
    }


@router.get("/dns-instructions")
async def dns_instructions(
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    return {"success": True, **await domain_service.get_dns_instructions(db)}


@router.get("/{domain_id}")
async def get_redirection_domain(
    domain_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    doc = await domain_service.get_domain(db, domain_id)
    if not doc:
        raise NotFoundError("Redirection Domain")
    return {"success": True, "domain": doc}


@router.post("", status_code=201)
async def create_redirection_domain(
    data: RedirectionDomainCreate,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    try:
        doc = await domain_service.create_domain(db, data.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True, "domain": doc, "message": "Domain added"}


@router.put("/{domain_id}")
async def update_redirection_domain(
    domain_id: str,
    data: RedirectionDomainUpdate,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    try:
        doc = await domain_service.update_domain(db, domain_id, data.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not doc:
        raise NotFoundError("Redirection Domain")
    return {"success": True, "domain": doc, "message": "Domain updated"}


@router.patch("/{domain_id}/status")
async def toggle_redirection_domain_status(
    domain_id: str,
    data: RedirectionDomainStatusToggle,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """
    Toggle a redirection domain between active and paused.

    For Prelander domains this is the POOL INCLUDE/EXCLUDE switch: only
    active domains participate in the weighted prelander pool (see
    domain_service.select_active_prelander); a paused domain is fully
    configured but receives no traffic. Toggling never touches any other
    field of the domain document.
    """
    status_value = data.status
    if status_value not in ("active", "paused"):
        raise HTTPException(status_code=400, detail="status must be 'active' or 'paused'")
    try:
        doc = await domain_service.update_domain(db, domain_id, {"status": status_value})
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not doc:
        raise NotFoundError("Redirection Domain")
    return {
        "success": True,
        "domain": doc,
        "message": (
            "Domain active — included in the traffic pool"
            if status_value == "active"
            else "Domain paused — excluded from the traffic pool"
        ),
    }


@router.delete("/{domain_id}")
async def delete_redirection_domain(
    domain_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """
    Delete a redirection domain.

    Delete requires confirmation (handled in the admin UI). Historical
    statistics remain after deletion. If the deleted domain was part of a
    redirect chain, the affected chains are reported back so the Admin can
    manually reconfigure them — the system never silently invents a
    replacement domain.
    """
    doc = await domain_service.get_domain(db, domain_id)
    if not doc:
        raise NotFoundError("Redirection Domain")

    deleted = await domain_service.delete_domain(db, domain_id)
    if not deleted:
        raise NotFoundError("Redirection Domain")

    # Report chains that referenced the deleted domain (canonical + legacy keys).
    from app.models.redirect_chain import (
        LEGACY_INTER_DOMAIN_KEY,
        LEGACY_PRELANDER_POOL_KEY,
    )
    host = doc.get("domain", "")
    affected = []
    async for chain in db.redirect_chains.find({
        "$or": [
            {"anchor_domain": host},
            {"inter_domain": host},
            {LEGACY_INTER_DOMAIN_KEY: host},
            {"prelander_pool": host},
            {LEGACY_PRELANDER_POOL_KEY: host},
        ]
    }):
        affected.append({"id": str(chain["_id"]), "name": chain.get("name", "")})

    message = "Domain removed"
    if affected:
        message = (
            "Domain removed. Manually reconfigure the listed redirect chains — "
            "no replacement was assigned automatically."
        )

    return {
        "success": True,
        "message": message,
        "affected_chains": affected,
    }


@router.post("/{domain_id}/verify-dns")
async def verify_redirection_domain_dns(
    domain_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    doc = await domain_service.verify_domain_dns(db, domain_id)
    if not doc:
        raise NotFoundError("Redirection Domain")
    return {
        "success": True,
        "domain": doc,
        "message": "DNS verified" if doc["dns_status"] == "verified" else "DNS verification failed — check your A record",
    }
