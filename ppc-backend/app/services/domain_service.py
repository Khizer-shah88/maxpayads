"""
Redirection domain management — CRUD, DNS verification, and publisher-aware resolution.
"""
from __future__ import annotations

import logging
import re
import socket
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from bson import ObjectId

from app.config import settings
from app.core.constants import (
    DOMAIN_TYPE_ANCHOR,
    DOMAIN_TYPE_INTER,
    DOMAIN_TYPE_PRELANDER,
)
from app.core.glossary import (
    DOMAIN_TYPE_ORDER,
    domain_type_filter,
    normalize_domain_type,
)

logger = logging.getLogger(__name__)

DOMAIN_TYPES = DOMAIN_TYPE_ORDER

# system_settings keys that predate the redirection_domains collection. These are
# stored keys, not glossary terms — renaming them would break the last-resort
# fallback in resolve_domain_url() for every install that still relies on them.
_SETTINGS_KEYS = {
    DOMAIN_TYPE_ANCHOR: "platform_domain",
    DOMAIN_TYPE_INTER: "intermediate_domain",
    DOMAIN_TYPE_PRELANDER: "last_domain",
}


def normalize_domain(raw: str) -> str:
    """Strip protocol/path and return lowercase hostname."""
    value = (raw or "").strip().lower()
    if not value:
        return ""
    if "://" in value:
        parsed = urlparse(value)
        value = parsed.netloc or parsed.path
    value = value.split("/")[0].split(":")[0]
    return value.rstrip(".")


def domain_to_url(domain: str) -> str:
    host = normalize_domain(domain)
    if not host:
        return ""
    return f"https://{host}"


def _serialize(doc: dict, publisher_map: Optional[Dict[str, str]] = None) -> dict:
    publisher_ids = doc.get("publisher_ids") or []
    names = []
    if publisher_map:
        names = [publisher_map.get(pid, pid) for pid in publisher_ids]
    return {
        "id": str(doc["_id"]),
        "domain": doc.get("domain", ""),
        "domain_type": normalize_domain_type(doc.get("domain_type"), default=DOMAIN_TYPE_ANCHOR),
        "publisher_ids": publisher_ids,
        "publisher_names": names,
        "is_default": bool(doc.get("is_default")),
        "status": doc.get("status", "active"),
        "template": doc.get("template", "default"),
        "template_id": doc.get("template_id"),
        "weight": int(doc.get("weight", 100) or 0),
        "dns_status": doc.get("dns_status", "pending"),
        "dns_checked_at": doc.get("dns_checked_at").isoformat() if doc.get("dns_checked_at") else None,
        "resolved_ips": doc.get("resolved_ips") or [],
        "notes": doc.get("notes"),
        "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
        "updated_at": doc.get("updated_at").isoformat() if doc.get("updated_at") else None,
    }


async def _publisher_name_map(db, publisher_ids: List[str]) -> Dict[str, str]:
    if not publisher_ids:
        return {}
    obj_ids = []
    for pid in publisher_ids:
        try:
            obj_ids.append(ObjectId(pid))
        except Exception:
            pass
    query = {"_id": {"$in": obj_ids}} if obj_ids else {"_id": {"$in": publisher_ids}}
    cursor = db.publishers.find(query, {"name": 1, "email": 1})
    result = {}
    async for p in cursor:
        result[str(p["_id"])] = p.get("name") or p.get("email") or str(p["_id"])
    return result


async def _clear_default_flag(db, domain_type: str, exclude_id: Optional[ObjectId] = None):
    query: dict = {"domain_type": domain_type_filter(domain_type), "is_default": True}
    if exclude_id:
        query["_id"] = {"$ne": exclude_id}
    await db.redirection_domains.update_many(query, {"$set": {"is_default": False}})


async def _sync_legacy_setting(db, domain_type: str, url: str):
    """Keep legacy system_settings keys in sync for backward compatibility."""
    key = _SETTINGS_KEYS.get(normalize_domain_type(domain_type))
    if not key or not url:
        return
    await db.system_settings.update_one(
        {"key": key},
        {"$set": {"key": key, "value": url, "updated_at": datetime.utcnow()}},
        upsert=True,
    )
    if normalize_domain_type(domain_type) == DOMAIN_TYPE_ANCHOR:
        await db.system_settings.update_one(
            {"key": "platform_domain"},
            {"$set": {"key": "platform_domain", "value": url, "updated_at": datetime.utcnow()}},
            upsert=True,
        )


async def list_domains(
    db,
    domain_type: Optional[str] = None,
    status: Optional[str] = None,
    publisher_id: Optional[str] = None,
) -> List[dict]:
    query: dict = {}
    if domain_type:
        type_filter = domain_type_filter(domain_type)
        if type_filter is None:
            return []
        query["domain_type"] = type_filter
    if status:
        query["status"] = status
    if publisher_id:
        query["$or"] = [
            {"publisher_ids": publisher_id},
            {"publisher_ids": {"$size": 0}},
            {"is_default": True},
        ]
    cursor = db.redirection_domains.find(query).sort([("domain_type", 1), ("is_default", -1), ("created_at", -1)])
    docs = await cursor.to_list(length=500)
    all_pub_ids = []
    for d in docs:
        all_pub_ids.extend(d.get("publisher_ids") or [])
    pub_map = await _publisher_name_map(db, list(set(all_pub_ids)))
    return [_serialize(d, pub_map) for d in docs]


async def get_domain(db, domain_id: str) -> Optional[dict]:
    try:
        oid = ObjectId(domain_id)
    except Exception:
        return None
    doc = await db.redirection_domains.find_one({"_id": oid})
    if not doc:
        return None
    pub_map = await _publisher_name_map(db, doc.get("publisher_ids") or [])
    return _serialize(doc, pub_map)


async def create_domain(db, data: dict) -> dict:
    domain = normalize_domain(data.get("domain", ""))
    domain_type = normalize_domain_type(data.get("domain_type"), default=DOMAIN_TYPE_ANCHOR)
    if not domain or domain_type not in DOMAIN_TYPES:
        raise ValueError("Valid domain and domain_type are required")
    from app.services.domain_access_service import domain_role
    if await domain_role(db, domain) in ("portal", "stats"):
        raise ValueError("This hostname already has a portal or stats role")
    if not re.match(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$", domain):
        raise ValueError("Invalid domain format")

    # Domain validation: reject exact duplicate hostnames regardless of type.
    # normalize_domain() lowercases and strips protocol/path/port, so
    # example.com / EXAMPLE.COM / https://example.com all collide here while
    # example.com / www.example.com / a.example.com stay distinct records.
    existing = await db.redirection_domains.find_one({"domain": domain})
    if existing:
        existing_type = normalize_domain_type(existing.get("domain_type"), default="anchor")
        raise ValueError(
            f"Domain '{domain}' is already registered as an {existing_type} domain"
        )

    is_default = bool(data.get("is_default"))
    if is_default:
        await _clear_default_flag(db, domain_type)

    now = datetime.utcnow()
    doc = {
        "domain": domain,
        "domain_type": domain_type,
        "publisher_ids": data.get("publisher_ids") or [],
        "is_default": is_default,
        "status": data.get("status", "active"),
        "template": data.get("template", "default") if domain_type == DOMAIN_TYPE_PRELANDER else "default",
        "template_id": data.get("template_id"),
        # Weight — relative distribution number for prelander domains.
        "weight": int(data.get("weight", 100) or 0),
        "dns_status": "pending",
        "dns_checked_at": None,
        "resolved_ips": [],
        "notes": data.get("notes"),
        "created_at": now,
        "updated_at": now,
    }
    result = await db.redirection_domains.insert_one(doc)
    doc["_id"] = result.inserted_id

    if is_default:
        await _sync_legacy_setting(db, domain_type, domain_to_url(domain))

    pub_map = await _publisher_name_map(db, doc.get("publisher_ids") or [])
    return _serialize(doc, pub_map)


async def update_domain(db, domain_id: str, data: dict) -> Optional[dict]:
    try:
        oid = ObjectId(domain_id)
    except Exception:
        return None
    doc = await db.redirection_domains.find_one({"_id": oid})
    if not doc:
        return None

    update: dict = {"updated_at": datetime.utcnow()}
    if "domain" in data and data["domain"] is not None:
        domain = normalize_domain(data["domain"])
        if not domain:
            raise ValueError("Domain cannot be empty")
        from app.services.domain_access_service import domain_role
        if await domain_role(db, domain) in ("portal", "stats"):
            raise ValueError("This hostname already has a portal or stats role")
        # Global duplicate check — any hostname may exist only once, whatever
        # its type (example.com as Anchor blocks example.com as Inter too).
        dup = await db.redirection_domains.find_one({
            "domain": domain,
            "_id": {"$ne": oid},
        })
        if dup:
            dup_type = normalize_domain_type(dup.get("domain_type"), default="anchor")
            raise ValueError(f"Domain '{domain}' is already registered as a {dup_type} domain")
        update["domain"] = domain

    if "publisher_ids" in data and data["publisher_ids"] is not None:
        update["publisher_ids"] = data["publisher_ids"]
    if "status" in data and data["status"] is not None:
        update["status"] = data["status"]
    if "notes" in data:
        update["notes"] = data["notes"]
    if "weight" in data and data["weight"] is not None:
        update["weight"] = int(data["weight"])
    doc_type = normalize_domain_type(doc.get("domain_type"))
    if doc_type == DOMAIN_TYPE_PRELANDER and data.get("template") is not None:
        update["template"] = data["template"]
    if doc_type == DOMAIN_TYPE_PRELANDER and "template_id" in data:
        update["template_id"] = data["template_id"]

    if data.get("is_default") is not None:
        is_default = bool(data["is_default"])
        update["is_default"] = is_default
        if is_default:
            await _clear_default_flag(db, doc_type, exclude_id=oid)

    await db.redirection_domains.update_one({"_id": oid}, {"$set": update})
    updated = await db.redirection_domains.find_one({"_id": oid})

    if updated.get("is_default"):
        await _sync_legacy_setting(db, updated["domain_type"], domain_to_url(updated["domain"]))

    pub_map = await _publisher_name_map(db, updated.get("publisher_ids") or [])
    return _serialize(updated, pub_map)


async def delete_domain(db, domain_id: str) -> bool:
    try:
        oid = ObjectId(domain_id)
    except Exception:
        return False
    result = await db.redirection_domains.delete_one({"_id": oid})
    return result.deleted_count > 0


def resolve_domain_ips(hostname: str) -> List[str]:
    ips: set = set()
    try:
        for info in socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM):
            ips.add(info[4][0])
    except Exception as e:
        logger.debug("DNS lookup failed for %s: %s", hostname, e)
    return sorted(ips)


async def verify_domain_dns(db, domain_id: str) -> Optional[dict]:
    try:
        oid = ObjectId(domain_id)
    except Exception:
        return None
    doc = await db.redirection_domains.find_one({"_id": oid})
    if not doc:
        return None

    hostname = doc["domain"]
    resolved = resolve_domain_ips(hostname)
    expected = getattr(settings, "SERVER_PUBLIC_IP", "") or ""

    if not resolved:
        dns_status = "failed"
    elif expected:
        dns_status = "verified" if expected in resolved else "failed"
    else:
        # No expected IP configured — any successful resolution counts as verified
        dns_status = "verified"

    now = datetime.utcnow()
    await db.redirection_domains.update_one(
        {"_id": oid},
        {"$set": {
            "dns_status": dns_status,
            "dns_checked_at": now,
            "resolved_ips": resolved,
            "updated_at": now,
        }},
    )

    updated = await db.redirection_domains.find_one({"_id": oid})
    pub_map = await _publisher_name_map(db, updated.get("publisher_ids") or [])
    out = _serialize(updated, pub_map)
    out["dns_target"] = expected or "Configure SERVER_PUBLIC_IP in .env for strict verification"
    return out


async def resolve_domain_url(
    db,
    domain_type: str,
    publisher_id: Optional[str] = None,
    *,
    require_verified: bool = False,
) -> Optional[str]:
    """
    Resolve the best active domain URL for a publisher.
    Priority: publisher-assigned → global default → legacy system_settings.
    """
    if db is None:
        return None

    canonical_type = normalize_domain_type(domain_type)
    if not canonical_type:
        return None

    base_query: dict = {"domain_type": domain_type_filter(canonical_type), "status": "active"}
    if require_verified:
        base_query["dns_status"] = "verified"

    # 1. Publisher-specific assignment
    if publisher_id:
        assigned = await db.redirection_domains.find_one({
            **base_query,
            "publisher_ids": publisher_id,
        })
        if assigned:
            return domain_to_url(assigned["domain"])

    # 2. Global default for this type
    default_doc = await db.redirection_domains.find_one({**base_query, "is_default": True})
    if default_doc:
        return domain_to_url(default_doc["domain"])

    # 3. Any active unassigned pool domain
    pool = await db.redirection_domains.find_one({
        **base_query,
        "$or": [{"publisher_ids": {"$size": 0}}, {"publisher_ids": {"$exists": False}}],
    })
    if pool:
        return domain_to_url(pool["domain"])

    # Only registered, active domains can receive public traffic.
    return None


def _to_absolute_url(raw: str) -> str:
    """
    Force a stored domain value to a full https:// URL.

    Legacy system_settings values may be stored as bare hostnames
    ("clicklyspot.icu"). Returning one raw made route_click build a
    RELATIVE destination ("clicklyspot.icu/d/{slug}") which the browser
    resolved against the publisher's page — sending visitors to
    https://publisher.com/clicklyspot.icu/d/{slug} (404). Never trust the
    stored spelling: strip protocol/path and rebuild the absolute URL.
    """
    host = normalize_domain(raw)
    if not host:
        return (raw or "").rstrip("/")
    return f"https://{host}"


async def get_dns_instructions(db) -> dict:
    expected = getattr(settings, "SERVER_PUBLIC_IP", "") or ""
    return {
        "server_ip": expected,
        "instructions": (
            "Point your domain A record to the server IP below. "
            "Once DNS propagates, click Verify DNS — the system will detect the domain automatically."
        ),
        "record_type": "A",
    }


async def select_active_prelander(db, pool: List[str]) -> Optional[str]:
    """
    Pick one Prelander domain from a chain's pool, honoring weights.

    Domain status rule: an inactive Prelander gets no traffic — eligible traffic
    redistributes to the remaining active prelanders by weight. A pool with no
    active domains returns None (the caller decides the fallback; the system
    never silently invents a replacement).
    """
    import random as _random

    # Pool entries are plain hostnames — fetch their status/weight docs.
    hostnames = [normalize_domain(d) for d in (pool or []) if d]
    if not hostnames:
        return None

    docs = await db.redirection_domains.find({
        "domain": {"$in": hostnames},
        "domain_type": domain_type_filter(DOMAIN_TYPE_PRELANDER),
    }).to_list(length=None)

    by_host = {normalize_domain(d.get("domain")): d for d in docs}
    active: List[tuple] = []
    for host in hostnames:
        doc = by_host.get(host)
        if not doc:
            continue
        if doc.get("status", "active") != "active":
            continue  # inactive prelander: gets no traffic
        weight = max(0, int(doc.get("weight", 100) or 0))
        if weight <= 0:
            continue  # weight 0 pauses the domain while keeping it configured
        active.append((host, weight))

    if not active:
        return None

    total = sum(w for _, w in active)
    if total <= 0:
        return active[0][0]

    rand = _random.uniform(0, total)
    cumulative = 0
    for host, weight in active:
        cumulative += weight
        if rand <= cumulative:
            return host
    return active[-1][0]


async def migrate_legacy_domains(db):
    """One-time style migration: seed redirection_domains from system_settings if empty."""
    count = await db.redirection_domains.count_documents({})
    if count > 0:
        return

    now = datetime.utcnow()
    platform = await db.system_settings.find_one({"key": "platform_domain"})
    if platform and platform.get("value"):
        host = normalize_domain(platform["value"])
        if host:
            await db.redirection_domains.insert_one({
                "domain": host,
                "domain_type": DOMAIN_TYPE_ANCHOR,
                "publisher_ids": [],
                "is_default": True,
                "status": "active",
                "template": "default",
                "dns_status": "pending",
                "dns_checked_at": None,
                "resolved_ips": [],
                "notes": "Migrated from platform_domain setting",
                "created_at": now,
                "updated_at": now,
            })

    tracking = await db.system_settings.find_one({"key": "click_tracking_domain"})
    if tracking and tracking.get("value"):
        host = normalize_domain(tracking["value"])
        if host:
            existing = await db.redirection_domains.find_one({
                "domain": host,
                "domain_type": domain_type_filter(DOMAIN_TYPE_ANCHOR),
            })
            if not existing:
                await db.redirection_domains.insert_one({
                    "domain": host,
                    "domain_type": DOMAIN_TYPE_ANCHOR,
                    "publisher_ids": [],
                    "is_default": False,
                    "status": "active",
                    "template": "default",
                    "dns_status": "pending",
                    "dns_checked_at": None,
                    "resolved_ips": [],
                    "notes": "Migrated from click_tracking_domain setting",
                    "created_at": now,
                    "updated_at": now,
                })
