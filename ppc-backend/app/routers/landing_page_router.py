from fastapi import APIRouter, Depends
from bson import ObjectId
from bson.errors import InvalidId
from datetime import datetime
from app.schemas.landing_page_schema import LandingPageCreate, LandingPageUpdate
from app.dependencies import get_db, get_current_admin
from app.core.exceptions import NotFoundError

router = APIRouter(prefix="/landing-pages", tags=["Landing Pages"])


def _lp_oid(page_id: str) -> ObjectId:
    """Parse a landing-page id, raising a clean 404 on malformed ids."""
    try:
        return ObjectId(page_id)
    except (InvalidId, TypeError):
        raise NotFoundError("Landing Page")


def serialize_landing_page(lp: dict) -> dict:
    lp["id"] = str(lp.pop("_id"))
    lp.setdefault("name", "")
    lp.setdefault("lander_url", "")
    lp.setdefault("campaign_id", None)
    lp.setdefault("status", "active")
    lp["weight"] = max(1, int(lp.get("weight") or 50))
    lp.setdefault("prelander_domain", None)
    lp.setdefault("prelander_template_id", None)
    if lp.get("campaign_id") is not None:
        lp["campaign_id"] = str(lp["campaign_id"])
    if lp.get("created_at") and hasattr(lp["created_at"], "isoformat"):
        lp["created_at"] = lp["created_at"].isoformat()
    if lp.get("updated_at") and hasattr(lp["updated_at"], "isoformat"):
        lp["updated_at"] = lp["updated_at"].isoformat()
    return lp


async def _enrich_with_prelander_info(db, pages: list) -> list:
    """
    Attach the display names for the landing page's prelander bindings:
      - prelander_domain_name: from redirection_domains (hostname it points at)
      - prelander_template_name: from prelander_templates ("OS Default Template"
        when unassigned, per the template-selection rule)
    Batch lookups keep this O(2 queries) regardless of list size.
    """
    domain_hosts = {p.get("prelander_domain") for p in pages if p.get("prelander_domain")}
    template_ids = {p.get("prelander_template_id") for p in pages if p.get("prelander_template_id")}

    domain_map: dict = {}
    if domain_hosts:
        async for d in db.redirection_domains.find({"domain": {"$in": list(domain_hosts)}}):
            domain_map[d["domain"]] = d.get("domain")

    template_map: dict = {}
    if template_ids:
        t_oids = []
        for t in template_ids:
            try:
                t_oids.append(ObjectId(t))
            except Exception:
                pass
        if t_oids:
            async for t in db.prelander_templates.find({"_id": {"$in": t_oids}}):
                template_map[str(t["_id"])] = t.get("name", "")

    for p in pages:
        host = p.get("prelander_domain")
        p["prelander_domain_name"] = domain_map.get(host) if host else None
        tpl_id = p.get("prelander_template_id")
        if tpl_id:
            p["prelander_template_name"] = template_map.get(str(tpl_id))
        elif p.get("prelander_domain_name"):
            p["prelander_template_name"] = "OS Default Template"
        else:
            p["prelander_template_name"] = None
    return pages


@router.get("")
async def list_landing_pages(
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    cursor = db.landing_pages.find().sort("created_at", -1)
    pages = [serialize_landing_page(lp) async for lp in cursor]
    pages = await _enrich_with_prelander_info(db, pages)
    return {"success": True, "landing_pages": pages, "total": len(pages)}


@router.get("/{page_id}")
async def get_landing_page(
    page_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    lp = await db.landing_pages.find_one({"_id": _lp_oid(page_id)})
    if not lp:
        raise NotFoundError("Landing Page")
    page = serialize_landing_page(lp)
    page = (await _enrich_with_prelander_info(db, [page]))[0]
    return {"success": True, "landing_page": page}


async def _validate_prelander_bindings(db, data: dict) -> None:
    """
    Soft-validate the prelander bindings. A template id must reference an
    existing prelander_templates doc; the domain must reference an active
    Prelander redirection domain. Raises ValueError so the router returns 400.
    """
    tpl_id = data.get("prelander_template_id")
    if tpl_id:
        try:
            doc = await db.prelander_templates.find_one({"_id": ObjectId(tpl_id)})
        except Exception:
            doc = None
        if not doc:
            raise ValueError("prelander_template_id does not match an existing template")

    domain = data.get("prelander_domain")
    if domain:
        from app.core.constants import DOMAIN_TYPE_PRELANDER
        from app.core.glossary import domain_type_filter
        doc = await db.redirection_domains.find_one({
            "domain": domain.strip().lower().replace("https://", "").replace("http://", "").rstrip("/"),
            "domain_type": domain_type_filter(DOMAIN_TYPE_PRELANDER),
        })
        if not doc:
            raise ValueError("prelander_domain is not a registered Prelander domain")


@router.post("", status_code=201)
async def create_landing_page(
    data: LandingPageCreate,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    doc = data.model_dump()
    if doc.get("prelander_domain"):
        doc["prelander_domain"] = (
            doc["prelander_domain"].strip().lower()
            .replace("https://", "").replace("http://", "").rstrip("/")
        )
        # The Prelander URL form field was removed — the URL is derived from
        # the bound domain so legacy lander_url reads keep working.
        if not doc.get("lander_url"):
            doc["lander_url"] = f"https://{doc['prelander_domain']}"
    await _validate_prelander_bindings(db, doc)
    doc["created_at"] = datetime.utcnow()
    doc["updated_at"] = datetime.utcnow()
    result = await db.landing_pages.insert_one(doc)
    return {"success": True, "landing_page_id": str(result.inserted_id), "message": "Landing page created"}


@router.put("/{page_id}")
async def update_landing_page(
    page_id: str,
    data: LandingPageUpdate,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    # exclude_unset: only touch fields the client actually sent, but DO honor an
    # explicit null (e.g. campaign_id: null to un-assign a campaign). The old
    # "drop all None" filter made un-assigning impossible.
    update_data = data.model_dump(exclude_unset=True)
    if update_data.get("prelander_domain"):
        update_data["prelander_domain"] = (
            update_data["prelander_domain"].strip().lower()
            .replace("https://", "").replace("http://", "").rstrip("/")
        )
        # Derive the URL from the bound domain when not explicitly supplied
        # (mirrors create — the form no longer carries a Prelander URL field).
        if not update_data.get("lander_url"):
            update_data["lander_url"] = f"https://{update_data['prelander_domain']}"
    await _validate_prelander_bindings(db, update_data)
    update_data["updated_at"] = datetime.utcnow()
    result = await db.landing_pages.update_one(
        {"_id": _lp_oid(page_id)},
        {"$set": update_data}
    )
    if result.matched_count == 0:
        raise NotFoundError("Landing Page")
    return {"success": True, "message": "Landing page updated"}


@router.delete("/{page_id}")
async def delete_landing_page(
    page_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    result = await db.landing_pages.delete_one({"_id": _lp_oid(page_id)})
    if result.deleted_count == 0:
        raise NotFoundError("Landing Page")
    return {"success": True, "message": "Landing page deleted"}
