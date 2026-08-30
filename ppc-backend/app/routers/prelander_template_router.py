"""
Prelander Template CRUD — admin-only.

A template defines the visual/UX design served at /d/{slug}.
It is distinct from:
  - Landing Pages  (campaign ↔ domain binding)
  - Redirection Domains (infrastructure routing)

Collection: ``prelander_templates``
"""
from datetime import datetime

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, Query
from typing import Optional

from app.dependencies import get_db, get_current_admin
from app.core.exceptions import NotFoundError
from app.schemas.prelander_template_schema import (
    PrlanderTemplateCreate,
    PrlanderTemplateUpdate,
)

router = APIRouter(prefix="/prelander-templates", tags=["Prelander Templates"])


# ─── helpers ──────────────────────────────────────────────────────────────────

def _oid(template_id: str) -> ObjectId:
    try:
        return ObjectId(template_id)
    except (InvalidId, TypeError):
        raise NotFoundError("Prelander Template")


def _serialize(doc: dict, usage_count: int = 0) -> dict:
    out = {
        "id": str(doc["_id"]),
        "name": doc.get("name", ""),
        "description": doc.get("description"),
        "os_type": doc.get("os_type", "both"),
        "status": doc.get("status", "active"),
        "title": doc.get("title", "Your file is ready to download"),
        "subtitle": doc.get("subtitle", ""),
        "button_text": doc.get("button_text", "Copy"),
        "show_password_field": bool(doc.get("show_password_field", True)),
        "show_video": bool(doc.get("show_video", False)),
        "video_url": doc.get("video_url"),
        "tags": doc.get("tags") or [],
        "notes": doc.get("notes"),
        "usage_count": usage_count,
        "created_at": doc["created_at"].isoformat() if doc.get("created_at") else None,
        "updated_at": doc["updated_at"].isoformat() if doc.get("updated_at") else None,
    }
    return out


async def _usage_count(template_id: str, db) -> int:
    """Count landing pages that reference this template."""
    return await db.landing_pages.count_documents({"prelander_template_id": template_id})


# ─── routes ───────────────────────────────────────────────────────────────────

@router.get("")
async def list_templates(
    status: Optional[str] = Query(None, description="active | paused | archived"),
    os_type: Optional[str] = Query(None, description="windows | mac | both"),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """List all prelander templates with optional filters."""
    query: dict = {}
    if status:
        query["status"] = status
    if os_type:
        query["os_type"] = os_type

    cursor = db.prelander_templates.find(query).sort("created_at", -1)
    docs = await cursor.to_list(length=500)

    # Batch-count usage so the list view can show "used by N pages"
    template_ids = [str(d["_id"]) for d in docs]
    usage_map: dict = {}
    if template_ids:
        pipeline = [
            {"$match": {"prelander_template_id": {"$in": template_ids}}},
            {"$group": {"_id": "$prelander_template_id", "count": {"$sum": 1}}},
        ]
        async for row in db.landing_pages.aggregate(pipeline):
            usage_map[row["_id"]] = row["count"]

    templates = [_serialize(d, usage_map.get(str(d["_id"]), 0)) for d in docs]
    return {"success": True, "templates": templates, "total": len(templates)}


@router.get("/{template_id}")
async def get_template(
    template_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Get a single prelander template with usage details."""
    doc = await db.prelander_templates.find_one({"_id": _oid(template_id)})
    if not doc:
        raise NotFoundError("Prelander Template")

    # Fetch landing pages that use this template
    lp_cursor = db.landing_pages.find(
        {"prelander_template_id": template_id},
        {"name": 1, "lander_url": 1, "status": 1, "campaign_id": 1},
    )
    used_by = []
    async for lp in lp_cursor:
        used_by.append({
            "id": str(lp["_id"]),
            "name": lp.get("name", ""),
            "lander_url": lp.get("lander_url", ""),
            "status": lp.get("status", "active"),
        })

    out = _serialize(doc, len(used_by))
    out["used_by"] = used_by
    return {"success": True, "template": out}


@router.post("", status_code=201)
async def create_template(
    data: PrlanderTemplateCreate,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Create a new prelander template."""
    now = datetime.utcnow()
    doc = {
        **data.model_dump(),
        "created_at": now,
        "updated_at": now,
    }
    result = await db.prelander_templates.insert_one(doc)
    doc["_id"] = result.inserted_id
    return {
        "success": True,
        "template_id": str(result.inserted_id),
        "template": _serialize(doc),
        "message": "Prelander template created",
    }


@router.put("/{template_id}")
async def update_template(
    template_id: str,
    data: PrlanderTemplateUpdate,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Update an existing prelander template."""
    update_data = data.model_dump(exclude_unset=True)
    update_data["updated_at"] = datetime.utcnow()
    result = await db.prelander_templates.update_one(
        {"_id": _oid(template_id)},
        {"$set": update_data},
    )
    if result.matched_count == 0:
        raise NotFoundError("Prelander Template")
    doc = await db.prelander_templates.find_one({"_id": _oid(template_id)})
    usage = await _usage_count(template_id, db)
    return {"success": True, "template": _serialize(doc, usage), "message": "Template updated"}


@router.patch("/{template_id}/status")
async def set_template_status(
    template_id: str,
    data: dict,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Activate, pause, or archive a template."""
    new_status = data.get("status", "")
    if new_status not in ("active", "paused", "archived"):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="status must be active | paused | archived")
    result = await db.prelander_templates.update_one(
        {"_id": _oid(template_id)},
        {"$set": {"status": new_status, "updated_at": datetime.utcnow()}},
    )
    if result.matched_count == 0:
        raise NotFoundError("Prelander Template")
    return {"success": True, "message": f"Template {new_status}"}


@router.delete("/{template_id}")
async def delete_template(
    template_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """
    Delete a prelander template.
    If it is still referenced by landing pages, those references are cleared
    (not cascaded) so existing landing pages keep working without the template.
    """
    doc = await db.prelander_templates.find_one({"_id": _oid(template_id)})
    if not doc:
        raise NotFoundError("Prelander Template")

    # Clear references in landing_pages
    await db.landing_pages.update_many(
        {"prelander_template_id": template_id},
        {"$unset": {"prelander_template_id": ""}, "$set": {"updated_at": datetime.utcnow()}},
    )

    await db.prelander_templates.delete_one({"_id": _oid(template_id)})
    return {"success": True, "message": "Prelander template deleted"}
