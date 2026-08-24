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
    if lp.get("campaign_id") is not None:
        lp["campaign_id"] = str(lp["campaign_id"])
    if lp.get("created_at") and hasattr(lp["created_at"], "isoformat"):
        lp["created_at"] = lp["created_at"].isoformat()
    if lp.get("updated_at") and hasattr(lp["updated_at"], "isoformat"):
        lp["updated_at"] = lp["updated_at"].isoformat()
    return lp


@router.get("")
async def list_landing_pages(
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    cursor = db.landing_pages.find().sort("created_at", -1)
    pages = [serialize_landing_page(lp) async for lp in cursor]
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
    return {"success": True, "landing_page": serialize_landing_page(lp)}


@router.post("", status_code=201)
async def create_landing_page(
    data: LandingPageCreate,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    doc = data.model_dump()
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
