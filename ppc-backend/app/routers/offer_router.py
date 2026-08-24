from fastapi import APIRouter, Depends
from bson import ObjectId
from bson.errors import InvalidId
from datetime import datetime
from app.schemas.offer_schema import OfferCreate, OfferUpdate
from app.dependencies import get_db, get_current_admin
from app.core.exceptions import NotFoundError

router = APIRouter(prefix="/offers", tags=["Offers"])


def _offer_oid(offer_id: str) -> ObjectId:
    """Parse an offer id into an ObjectId, raising a clean 404 on malformed ids."""
    try:
        return ObjectId(offer_id)
    except (InvalidId, TypeError):
        raise NotFoundError("Offer")


def serialize_offer(offer: dict) -> dict:
    offer["id"] = str(offer.pop("_id"))
    if offer.get("created_at"):
        offer["created_at"] = offer["created_at"].isoformat() if hasattr(offer["created_at"], "isoformat") else str(offer["created_at"])
    if offer.get("updated_at"):
        offer["updated_at"] = offer["updated_at"].isoformat() if hasattr(offer["updated_at"], "isoformat") else str(offer["updated_at"])
    # Ensure targeting arrays are always present
    offer.setdefault("publisher_ids", [])
    offer.setdefault("website_ids", [])
    offer.setdefault("os_types", [])
    offer.setdefault("country_codes", [])
    offer.setdefault("password", "")
    offer.setdefault("direct_redirect_mode", False)
    # Display-critical scalar fields — coerce to safe defaults so the UI never
    # crashes on a document that predates a field or has a null value.
    offer["payout"] = offer.get("payout") or 0.0
    offer.setdefault("name", "")
    offer.setdefault("offer_url", "")
    offer.setdefault("status", "active")
    offer.setdefault("campaign_id", None)
    if offer.get("campaign_id") is not None:
        offer["campaign_id"] = str(offer["campaign_id"])
    offer["publisher_ids"] = [str(x) for x in offer.get("publisher_ids", [])]
    offer["website_ids"] = [str(x) for x in offer.get("website_ids", [])]
    return offer


@router.get("")
async def list_offers(
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    cursor = db.offers.find().sort("created_at", -1)
    offers = [serialize_offer(o) async for o in cursor]
    return {"success": True, "offers": offers, "total": len(offers)}


@router.get("/{offer_id}")
async def get_offer(
    offer_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    offer = await db.offers.find_one({"_id": _offer_oid(offer_id)})
    if not offer:
        raise NotFoundError("Offer")
    return {"success": True, "offer": serialize_offer(offer)}


@router.post("", status_code=201)
async def create_offer(
    data: OfferCreate,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    doc = data.model_dump()
    doc["created_at"] = datetime.utcnow()
    doc["updated_at"] = datetime.utcnow()
    result = await db.offers.insert_one(doc)
    return {"success": True, "offer_id": str(result.inserted_id), "message": "Offer created"}


@router.put("/{offer_id}")
async def update_offer(
    offer_id: str,
    data: OfferUpdate,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    update_data = data.model_dump(exclude_unset=True)
    update_data["updated_at"] = datetime.utcnow()
    result = await db.offers.update_one(
        {"_id": _offer_oid(offer_id)},
        {"$set": update_data}
    )
    if result.matched_count == 0:
        raise NotFoundError("Offer")
    return {"success": True, "message": "Offer updated"}


@router.delete("/{offer_id}")
async def delete_offer(
    offer_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    result = await db.offers.delete_one({"_id": _offer_oid(offer_id)})
    if result.deleted_count == 0:
        raise NotFoundError("Offer")
    return {"success": True, "message": "Offer deleted"}
