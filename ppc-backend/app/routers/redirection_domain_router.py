from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from app.dependencies import get_db, get_current_admin
from app.schemas.redirection_domain_schema import RedirectionDomainCreate, RedirectionDomainUpdate
from app.services import domain_service
from app.core.exceptions import NotFoundError

router = APIRouter(prefix="/admin/redirection-domains", tags=["Redirection Domains"])


@router.get("")
async def list_redirection_domains(
    domain_type: Optional[str] = Query(None, description="link | intermediate | last"),
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


@router.delete("/{domain_id}")
async def delete_redirection_domain(
    domain_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    deleted = await domain_service.delete_domain(db, domain_id)
    if not deleted:
        raise NotFoundError("Redirection Domain")
    return {"success": True, "message": "Domain removed"}


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
