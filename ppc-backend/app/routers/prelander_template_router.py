"""
Prelander Template Management Router (Admin)
=============================================

CRUD + lifecycle endpoints for the `prelander_templates` collection — the
templates the admin designs for the `/d/{slug}` landing page.

Why this router exists: the frontend admin page (`/admin/prelander-templates`)
calls `/api/prelander-templates/...` (see `prlanderTemplateApi` in
`ppc-frontend/lib/api.ts`), but no backend route had ever been registered for
them. Every list/create/update/delete therefore 404'd with "Not Found" — the
page showed "Failed to load templates" and creating a template failed with
"Save failed". This router implements exactly the endpoints the frontend
expects:

  GET    /prelander-templates                 → {templates: [...], total}
  GET    /prelander-templates/{id}            → {template: {...}}
  POST   /prelander-templates                 → {template_id, warnings?}
  PUT    /prelander-templates/{id}            → {success, warnings?}
  PATCH  /prelander-templates/{id}/status     → {success}
  POST   /prelander-templates/{id}/set-default → {success}
  POST   /prelander-templates/{id}/preview    → {html, campaign_url, password}
  DELETE /prelander-templates/{id}            → {success}
  POST   /prelander-templates/validate-html   → validation result (docs)

Notes:
- A template may carry a complete HTML source (`full_html_template`). It is
  validated on save with the same engine used to render live traffic
  (`PrelanderTemplateEngine.validate_template`) so an admin can never store a
  template that would break the prelander at click time. Unknown shortcodes
  only produce WARNINGS (returned to the UI as toasts) — they don't block
  the save, matching the documented behaviour in PRELANDER_USAGE_EXAMPLES.md.
- "Default" semantics mirror `get_default_template` in prelander_service:
  at most one active default per os_type wins; setting a new default for an
  OS clears the flag from other templates of the SAME OS scope first
  (OS-specific default, then "both").
- Delete does NOT cascade: landing_pages referencing the template keep their
  `prelander_template_id` and the runtime falls back to the OS default —
  the documented rule (see landing_page_router._enrich_with_prelander_info).
- usage_count / used_by are computed on read from landing_pages, so they are
  always current without any counter maintenance on writes.
"""
import logging
from datetime import datetime
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.core.exceptions import NotFoundError, ValidationError
from app.core.glossary import domain_type_filter
from app.dependencies import get_db, get_current_admin
from app.schemas.prelander_template_schema import (
    PrlanderTemplateCreate,
    PrlanderTemplateUpdate,
    TEMPLATE_OS_ANY,
)
from app.services.prelander_service import PrelanderTemplateEngine, RedirectContext

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prelander-templates", tags=["Prelander Templates"])

VALID_STATUSES = ("active", "paused", "archived")


def _tpl_oid(template_id: str) -> ObjectId:
    """Parse a template id, raising a clean 404 on malformed ids."""
    try:
        return ObjectId(template_id)
    except (InvalidId, TypeError):
        raise NotFoundError("Prelander Template")


def _iso(value) -> Optional[str]:
    """Datetime → ISO string (None-safe)."""
    if value and hasattr(value, "isoformat"):
        return value.isoformat()
    return None


def serialize_template(t: dict, usage_count: int = 0, used_by: Optional[list] = None) -> dict:
    """
    Shape a stored template doc for the API: string id, always-present
    display fields, ISO dates, and the usage info the UI renders.
    """
    out = dict(t)
    out["id"] = str(out.pop("_id"))
    out.setdefault("name", "")
    out.setdefault("description", None)
    out.setdefault("os_type", TEMPLATE_OS_ANY)
    out.setdefault("status", "active")
    out["is_default"] = bool(out.get("is_default"))
    out.setdefault("title", "")
    out.setdefault("subtitle", "")
    out.setdefault("button_text", "")
    out["show_password_field"] = bool(out.get("show_password_field", True))
    out["show_video"] = bool(out.get("show_video", False))
    out.setdefault("video_url", None)
    out["tags"] = list(out.get("tags") or [])
    out.setdefault("notes", None)
    out.setdefault("full_html_template", None)
    out["usage_count"] = usage_count
    out["used_by"] = used_by or []
    out["created_at"] = _iso(out.get("created_at"))
    out["updated_at"] = _iso(out.get("updated_at"))
    return out


async def _usage_info(db, templates: list) -> dict:
    """
    usage_count / used_by per template id, from landing_pages.prelander_template_id.
    One query for the whole page — computed on read so counters can never drift.
    """
    ids = [t["id"] for t in templates]
    if not ids:
        return {}

    oids = []
    for t in ids:
        try:
            oids.append(ObjectId(t))
        except Exception:
            continue
    if not oids:
        return {}

    usage: dict = {t: {"count": 0, "pages": []} for t in ids}
    cursor = db.landing_pages.find(
        {"prelander_template_id": {"$in": ids + oids}}
    )
    async for lp in cursor:
        raw = lp.get("prelander_template_id")
        # Stored values can be either the string id or an embedded ObjectId —
        # normalise both onto the string key.
        key = raw if isinstance(raw, str) else str(raw)
        if key not in usage:
            continue
        usage[key]["count"] += 1
        usage[key]["pages"].append({
            "id": str(lp.get("_id")),
            "name": lp.get("name") or "",
            "lander_url": lp.get("lander_url") or "",
            "status": lp.get("status") or "active",
        })
    return usage


async def _domain_assignments(db, template_ids: list[str]) -> dict:
    """Read the same domain.template_id binding used by the visitor renderer."""
    assignments = {template_id: [] for template_id in template_ids}
    if not template_ids:
        return assignments
    cursor = db.redirection_domains.find({
        "domain_type": domain_type_filter("prelander"),
        "template_id": {"$in": template_ids + [ObjectId(value) for value in template_ids]},
    })
    async for domain in cursor:
        assignments[str(domain["template_id"])].append({
            "id": str(domain["_id"]),
            "domain": domain.get("domain", ""),
            "status": domain.get("status", "active"),
        })
    return assignments


def _validate_html_payload(html: Optional[str]) -> dict:
    """
    Validate the full HTML template with the live rendering engine.
    Returns the validation dict (valid / message / used_placeholders /
    warnings). A syntactically broken template is REJECTED (400) — storing it
    would 500 every click routed to it.
    """
    engine = PrelanderTemplateEngine()
    result = engine.validate_template(html)
    if not result.get("valid"):
        raise ValidationError(result.get("message") or "Invalid template HTML")
    return result


async def _resolve_campaign_values(db, os_hint: Optional[str] = None) -> tuple:
    """
    Global Campaign values for the preview modal: URL + password of the
    active by-device campaign for the hinted OS, falling back to any active
    campaign. Mirrors the offer → geo-rule → campaign priority used by the
    live prelander resolve (see prelander_router._get_prelander_data).
    """
    from app.core.glossary import normalize_os

    normalized_os = normalize_os(os_hint or "", default=None)
    campaign_url = ""
    password = ""

    query: dict = {"status": "active"}
    if normalized_os and normalized_os != TEMPLATE_OS_ANY:
        campaign = await db.campaigns.find_one({"device_os": normalized_os, **query})
        if not campaign:
            campaign = await db.campaigns.find_one(query)
    else:
        campaign = await db.campaigns.find_one(query)

    if campaign:
        campaign_url = campaign.get("default_offer_url") or campaign.get("offer_url") or ""
        password = campaign.get("password") or ""
    return campaign_url, password


# ═════════════════════════════════════════════════════════════════════════════
# List / detail
# ═════════════════════════════════════════════════════════════════════════════

class _ValidateHtmlBody(BaseModel):
    html: str


@router.post("/validate-html")
async def validate_html(
    body: _ValidateHtmlBody,
    current_user: dict = Depends(get_current_admin),
):
    """Standalone validation documented in PRELANDER_USAGE_EXAMPLES.md.
    Registered BEFORE /{template_id} so the literal path always wins."""
    engine = PrelanderTemplateEngine()
    return engine.validate_template(body.html)


@router.get("")
async def list_templates(
    status_filter: Optional[str] = Query(None, alias="status"),
    os_type: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """List prelander templates, newest first, with optional filters."""
    query: dict = {}
    if status_filter:
        if status_filter not in VALID_STATUSES:
            raise ValidationError("Invalid status filter")
        query["status"] = status_filter
    if os_type:
        query["os_type"] = os_type

    cursor = db.prelander_templates.find(query).sort("created_at", -1)
    templates = [serialize_template(t) async for t in cursor]
    usage = await _usage_info(db, templates)
    assignments = await _domain_assignments(db, [t["id"] for t in templates])
    for t in templates:
        info = usage.get(t["id"], {})
        t["usage_count"] = info.get("count", 0)
        t["used_by"] = info.get("pages", [])
        t["assigned_domains"] = assignments[t["id"]]
    return {"success": True, "templates": templates, "total": len(templates)}


@router.get("/{template_id}")
async def get_template(
    template_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Fetch a single template with its usage info."""
    t = await db.prelander_templates.find_one({"_id": _tpl_oid(template_id)})
    if not t:
        raise NotFoundError("Prelander Template")
    tpl = serialize_template(t)
    usage = await _usage_info(db, [tpl])
    info = usage.get(tpl["id"], {})
    tpl["usage_count"] = info.get("count", 0)
    tpl["used_by"] = info.get("pages", [])
    tpl["assigned_domains"] = (await _domain_assignments(db, [tpl["id"]]))[tpl["id"]]
    return {"success": True, "template": tpl}


class TemplateDomainAssignment(BaseModel):
    domain_ids: list[str] = Field(max_length=1000)


@router.put("/{template_id}/domains")
async def assign_template_domains(
    template_id: str,
    data: TemplateDomainAssignment,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Assign this template to selected prelander domains without changing defaults."""
    oid = _tpl_oid(template_id)
    if not await db.prelander_templates.find_one({"_id": oid}):
        raise NotFoundError("Prelander Template")
    try:
        domain_ids = list({ObjectId(value) for value in data.domain_ids})
    except (InvalidId, TypeError):
        raise ValidationError("Invalid prelander domain ID")
    domain_filter = {"domain_type": domain_type_filter("prelander")}
    # Validate the entire selection before changing any assignment.
    found = [d async for d in db.redirection_domains.find({
        **domain_filter, "_id": {"$in": domain_ids},
    })]
    if len(found) != len(domain_ids):
        raise ValidationError("Select existing prelander domains only")
    now = datetime.utcnow()
    if domain_ids:
        await db.redirection_domains.update_many(
            {**domain_filter, "_id": {"$in": domain_ids}},
            {"$set": {"template_id": str(oid), "updated_at": now}},
        )
    # Only clear bindings belonging to THIS template; others remain untouched.
    await db.redirection_domains.update_many(
        {**domain_filter, "template_id": {"$in": [str(oid), oid]}, "_id": {"$nin": domain_ids}},
        {"$set": {"template_id": None, "updated_at": now}},
    )
    return {
        "success": True,
        "assigned_domains": (await _domain_assignments(db, [str(oid)]))[str(oid)],
    }


# ═════════════════════════════════════════════════════════════════════════════
# Create / update / delete
# ═════════════════════════════════════════════════════════════════════════════

@router.post("", status_code=201)
async def create_template(
    data: PrlanderTemplateCreate,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """
    Create a template. The full HTML source is validated with the live
    rendering engine; unknown shortcodes become warnings (shown as toasts
    by the UI) without blocking the save.
    """
    doc = data.model_dump()

    warnings: list = []
    if doc.get("full_html_template"):
        result = _validate_html_payload(doc["full_html_template"])
        warnings = list(result.get("warnings") or [])

    # Enforce single default per OS scope when requested
    if doc.get("is_default"):
        await _clear_other_defaults(db, doc.get("os_type") or TEMPLATE_OS_ANY)

    doc["created_at"] = datetime.utcnow()
    doc["updated_at"] = datetime.utcnow()
    res = await db.prelander_templates.insert_one(doc)

    out = {"success": True, "template_id": str(res.inserted_id), "message": "Template created"}
    if warnings:
        out["warnings"] = warnings
    return out


@router.put("/{template_id}")
async def update_template(
    template_id: str,
    data: PrlanderTemplateUpdate,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """
    Partial update. Only the fields the client sent are written
    (exclude_unset) — the admin form sends name/status/notes/full_html_template
    and every other field stays untouched.
    """
    oid = _tpl_oid(template_id)
    existing = await db.prelander_templates.find_one({"_id": oid})
    if not existing:
        raise NotFoundError("Prelander Template")

    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        return {"success": True, "message": "Nothing to update"}

    warnings: list = []
    if "full_html_template" in update_data and update_data.get("full_html_template"):
        result = _validate_html_payload(update_data["full_html_template"])
        warnings = list(result.get("warnings") or [])

    # Keep single-default invariant when the flag / os_type changes
    if update_data.get("is_default"):
        os_scope = update_data.get("os_type") or existing.get("os_type") or TEMPLATE_OS_ANY
        await _clear_other_defaults(db, os_scope, keep_id=str(oid))

    update_data["updated_at"] = datetime.utcnow()
    await db.prelander_templates.update_one({"_id": oid}, {"$set": update_data})

    out = {"success": True, "message": "Template updated"}
    if warnings:
        out["warnings"] = warnings
    return out


@router.delete("/{template_id}")
async def delete_template(
    template_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """
    Delete a template. Landing pages keep their reference — the runtime falls
    back to the OS Default Template (documented behaviour), so no cascade.
    """
    res = await db.prelander_templates.delete_one({"_id": _tpl_oid(template_id)})
    if res.deleted_count == 0:
        raise NotFoundError("Prelander Template")
    return {"success": True, "message": "Template deleted"}


# ═════════════════════════════════════════════════════════════════════════════
# Lifecycle
# ═════════════════════════════════════════════════════════════════════════════

class _StatusBody(BaseModel):
    status: str


@router.patch("/{template_id}/status")
async def set_template_status(
    template_id: str,
    body: _StatusBody,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """Set status (active / paused / archived)."""
    if body.status not in VALID_STATUSES:
        raise ValidationError("Invalid status")
    oid = _tpl_oid(template_id)
    res = await db.prelander_templates.update_one(
        {"_id": oid}, {"$set": {"status": body.status, "updated_at": datetime.utcnow()}}
    )
    if res.matched_count == 0:
        raise NotFoundError("Prelander Template")
    return {"success": True, "message": f"Template {body.status}"}


async def _clear_other_defaults(db, os_scope: str, keep_id: Optional[str] = None) -> None:
    """
    Keep at most one active default per OS scope. Mirrors the priority in
    prelander_service.get_default_template: an OS-specific default, then the
    "both" default. Setting a new default clears the previous holder(s).
    """
    filters: list = []
    if os_scope and os_scope != TEMPLATE_OS_ANY:
        filters.append({"os_type": os_scope})
    filters.append({"os_type": TEMPLATE_OS_ANY})

    for f in filters:
        query = {"is_default": True, "status": "active", **f}
        if keep_id:
            query["_id"] = {"$ne": ObjectId(keep_id)}
        await db.prelander_templates.update_many(query, {"$set": {"is_default": False}})


@router.post("/{template_id}/set-default")
async def set_default_template(
    template_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """
    Make this template the default for its OS. Clears the previous default
    in the same OS scope (OS-specific, then "both").
    """
    oid = _tpl_oid(template_id)
    t = await db.prelander_templates.find_one({"_id": oid})
    if not t:
        raise NotFoundError("Prelander Template")

    os_scope = t.get("os_type") or TEMPLATE_OS_ANY
    await _clear_other_defaults(db, os_scope, keep_id=str(oid))

    await db.prelander_templates.update_one(
        {"_id": oid},
        {"$set": {"is_default": True, "status": "active", "updated_at": datetime.utcnow()}},
    )
    return {"success": True, "message": f'Default template set for OS: {os_scope}'}


# ═════════════════════════════════════════════════════════════════════════════
# Preview & validation
# ═════════════════════════════════════════════════════════════════════════════

class _PreviewBody(BaseModel):
    os: Optional[str] = None


@router.post("/{template_id}/preview")
async def preview_template(
    template_id: str,
    body: _PreviewBody,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
):
    """
    Render the stored full HTML template with Global Campaign values
    substituted, for the admin preview iframe. Uses the exact engine + context
    the live prelander flow uses, so what the admin sees is what renders.
    """
    t = await db.prelander_templates.find_one({"_id": _tpl_oid(template_id)})
    if not t:
        raise NotFoundError("Prelander Template")

    html = t.get("full_html_template")
    if not html:
        raise ValidationError("This template has no full HTML source to preview")

    campaign_url, password = await _resolve_campaign_values(db, body.os)

    try:
        ctx = RedirectContext(
            click_id="preview",
            campaign_url=campaign_url,
            os=body.os or t.get("os_type") or "",
            password=password or "",
        )
        rendered = PrelanderTemplateEngine().render(html, ctx)
    except ValueError as e:
        raise ValidationError(str(e))
    except Exception as e:
        logger.error("Template preview render failed: %s", e)
        raise ValidationError("Template rendering failed")

    return {
        "success": True,
        "html": rendered,
        "campaign_url": campaign_url,
        "password": password,
    }
