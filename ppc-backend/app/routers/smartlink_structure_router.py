"""
Smartlink Structures — admin-managed parameter schemes for Smartlinks.

A structure defines WHICH query-parameter names carry the publisher and
website identifiers, e.g.:

    Standard      → https://{DOMAIN}/?pub={PUBLISHER_ID}&site={SITE_ID}
    Tag + SID     → https://{DOMAIN}/?tag={PUBLISHER_ID}&sid={SITE_ID}
    Tag Only      → https://{DOMAIN}/?tag={PUBLISHER_ID}

Parameter names are NOT hardcoded — admins create/edit structures from the
panel, and the final Smartlink is generated automatically from the selected
structure + supplied identifiers.

Collection: ``smartlink_structures``
"""
import re
from datetime import datetime
from typing import List, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from app.dependencies import get_db, get_current_admin
from app.core.exceptions import NotFoundError

router = APIRouter(prefix="/admin/smartlink-structures", tags=["Smartlink Structures"])

_PARAM_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,31}$")


# ─── schemas ──────────────────────────────────────────────────────────────────

class SmartlinkStructureBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    # Query-parameter names — fully admin-manageable, never hardcoded.
    publisher_param: str = Field(..., min_length=1, max_length=32)
    website_param: Optional[str] = Field(
        None, max_length=32,
        description="None when the structure carries no website identifier (Tag Only)",
    )
    # When False the website parameter is omitted even if named.
    include_website: bool = True
    # Optional extra static params appended verbatim, e.g. [{"key":"utm_source","value":"push"}]
    extra_params: List[dict] = Field(default_factory=list, max_length=10)
    is_default: bool = False
    status: str = Field("active", description="active | paused")

    @field_validator("publisher_param", "website_param")
    @classmethod
    def _param_names(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not _PARAM_RE.match(v):
            raise ValueError(
                "parameter names must start with a letter and contain only "
                "letters, digits, underscore and hyphen"
            )
        return v

    @field_validator("status")
    @classmethod
    def _status(cls, v: str) -> str:
        v = (v or "active").strip().lower()
        if v not in ("active", "paused"):
            raise ValueError("status must be 'active' or 'paused'")
        return v


class SmartlinkStructureCreate(SmartlinkStructureBase):
    pass


class SmartlinkStructureUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    publisher_param: Optional[str] = Field(None, min_length=1, max_length=32)
    website_param: Optional[str] = Field(None, max_length=32)
    include_website: Optional[bool] = None
    extra_params: Optional[List[dict]] = Field(None, max_length=10)
    is_default: Optional[bool] = None
    status: Optional[str] = None


# ─── helpers ──────────────────────────────────────────────────────────────────

def _serialize(doc: dict) -> dict:
    out = {
        "id": str(doc["_id"]),
        "name": doc.get("name", ""),
        "publisher_param": doc.get("publisher_param", "pub"),
        "website_param": doc.get("website_param"),
        "include_website": bool(doc.get("include_website", True)),
        "extra_params": doc.get("extra_params") or [],
        "is_default": bool(doc.get("is_default", False)),
        "status": doc.get("status", "active"),
        "created_at": doc["created_at"].isoformat() if doc.get("created_at") else None,
        "updated_at": doc["updated_at"].isoformat() if doc.get("updated_at") else None,
    }
    # The generated pattern, shown in the admin UI.
    example = f"?{out['publisher_param']}={{PUBLISHER_ID}}"
    if out["include_website"] and out["website_param"]:
        example += f"&{out['website_param']}={{SITE_ID}}"
    for extra in out["extra_params"]:
        if isinstance(extra, dict) and extra.get("key"):
            example += f"&{extra['key']}={extra.get('value', '')}"
    out["pattern"] = f"https://{{DOMAIN}}/{example}"
    return out


def _oid(structure_id: str) -> ObjectId:
    try:
        return ObjectId(structure_id)
    except (InvalidId, TypeError):
        raise NotFoundError("Smartlink Structure")


async def _clear_default_flag(db, exclude_id: Optional[ObjectId] = None):
    query: dict = {"is_default": True}
    if exclude_id:
        query["_id"] = {"$ne": exclude_id}
    await db.smartlink_structures.update_many(query, {"$set": {"is_default": False}})


# ─── CRUD ─────────────────────────────────────────────────────────────────────

@router.get("")
async def list_structures(
    status: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    query: dict = {}
    if status:
        query["status"] = status
    cursor = db.smartlink_structures.find(query).sort([("is_default", -1), ("created_at", -1)])
    docs = await cursor.to_list(length=500)
    return {"success": True, "structures": [_serialize(d) for d in docs], "total": len(docs)}


@router.post("", status_code=201)
async def create_structure(
    data: SmartlinkStructureCreate,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    now = datetime.utcnow()
    doc = data.model_dump()
    doc["created_at"] = now
    doc["updated_at"] = now
    if doc["is_default"]:
        await _clear_default_flag(db)
    result = await db.smartlink_structures.insert_one(doc)
    doc["_id"] = result.inserted_id
    return {
        "success": True,
        "structure": _serialize(doc),
        "message": "Smartlink structure created",
    }


@router.get("/{structure_id}")
async def get_structure(
    structure_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    doc = await db.smartlink_structures.find_one({"_id": _oid(structure_id)})
    if not doc:
        raise NotFoundError("Smartlink Structure")
    return {"success": True, "structure": _serialize(doc)}


@router.put("/{structure_id}")
async def update_structure(
    structure_id: str,
    data: SmartlinkStructureUpdate,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    oid = _oid(structure_id)
    update = data.model_dump(exclude_unset=True)
    if update.get("status") is not None:
        s = update["status"]
        if s not in ("active", "paused"):
            raise HTTPException(status_code=400, detail="status must be 'active' or 'paused'")
    if update.get("publisher_param") is not None:
        if not _PARAM_RE.match(update["publisher_param"]):
            raise HTTPException(status_code=400, detail="Invalid publisher parameter name")
    if "website_param" in update and update["website_param"]:
        if not _PARAM_RE.match(update["website_param"]):
            raise HTTPException(status_code=400, detail="Invalid website parameter name")
    if update.get("is_default"):
        await _clear_default_flag(db, exclude_id=oid)
    update["updated_at"] = datetime.utcnow()
    result = await db.smartlink_structures.update_one({"_id": oid}, {"$set": update})
    if result.matched_count == 0:
        raise NotFoundError("Smartlink Structure")
    doc = await db.smartlink_structures.find_one({"_id": oid})
    return {"success": True, "structure": _serialize(doc), "message": "Smartlink structure updated"}


@router.delete("/{structure_id}")
async def delete_structure(
    structure_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    oid = _oid(structure_id)
    result = await db.smartlink_structures.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise NotFoundError("Smartlink Structure")
    return {"success": True, "message": "Smartlink structure deleted"}


# ─── Smartlink generation ─────────────────────────────────────────────────────

@router.post("/generate")
async def generate_smartlink(
    data: dict,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """
    Generate the final Smartlink from a structure + identifiers.

    Body:
      structure_id: str  (or omit → default structure)
      domain:      str   (anchor domain URL; optional → resolved)
      publisher_id: str  (public ID, e.g. PUB_XXXXXXXX)
      site_id:     str   (optional public ID, e.g. SITE_XXXXXXXX)
    """
    from urllib.parse import quote

    structure_id = (data.get("structure_id") or "").strip()
    if structure_id:
        doc = await db.smartlink_structures.find_one({"_id": _oid(structure_id)})
    else:
        doc = await db.smartlink_structures.find_one({"is_default": True})
    if not doc:
        raise HTTPException(status_code=400, detail="No smartlink structure found — create one first")

    publisher_id = (data.get("publisher_id") or "").strip()
    if not publisher_id:
        raise HTTPException(status_code=400, detail="publisher_id is required")
    site_id = (data.get("site_id") or "").strip()
    domain = (data.get("domain") or "").strip().rstrip("/")

    if not domain:
        # Resolve the Anchor domain as the smartlink base.
        from app.core.constants import DOMAIN_TYPE_ANCHOR
        from app.services.domain_service import resolve_domain_url
        domain = await resolve_domain_url(db, DOMAIN_TYPE_ANCHOR, None) or ""

    pub_param = doc.get("publisher_param", "pub")
    site_param = doc.get("website_param", "site")
    include_site = bool(doc.get("include_website", True)) and bool(site_id) and bool(site_param)

    params = [f"{quote(pub_param)}={quote(publisher_id)}"]
    if include_site and site_param:
        params.append(f"{quote(site_param)}={quote(site_id)}")
    for extra in doc.get("extra_params") or []:
        if isinstance(extra, dict) and extra.get("key"):
            params.append(f"{quote(str(extra['key']))}={quote(str(extra.get('value', '')))}")

    smartlink = f"{domain}?{'&'.join(params)}" if domain else f"?{'&'.join(params)}"
    return {
        "success": True,
        "smartlink": smartlink,
        "structure": _serialize(doc),
        "publisher_id": publisher_id,
        "site_id": site_id if include_site else None,
    }