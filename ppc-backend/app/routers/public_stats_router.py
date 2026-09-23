"""
Public Stats Router — white-label publisher statistics page.

No authentication required. Access is controlled by a secret share ID that is
stored on the publisher's direct link document:

    GET /public-stats/{share_id}

Regeneration (POST /direct-links/{link_id}/regenerate-stats-link) replaces the
share ID, so any old URL stops resolving immediately and renders only
"This statistics link has expired." — with no further information exposed.

No internal branding, publisher names, campaign names, domain names, or admin
info is exposed — only aggregated performance numbers plus any conversions the
admin entered manually.
"""
from collections import defaultdict
from datetime import datetime, timedelta

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, Depends

from app.dependencies import get_db

router = APIRouter(prefix="/public-stats", tags=["Public Stats"])

_EXPIRED_DETAIL = "This statistics link has expired."


@router.get("/{share_id}")
async def get_public_stats(
    share_id: str,
    days: int = Query(30, ge=1, le=90, description="Number of days to include"),
    db=Depends(get_db),
):
    """
    Get white-label publisher statistics by share ID.
    Called by the /public-stats/[shareId] Next.js page.

    Any unknown/expired share ID returns the same minimal 410 response —
    never revealing whether the link existed, who it belonged to, or the
    new URL after regeneration.
    """
    # ── Share ID lookup — unknown IDs are simply "expired" ────────────────────
    link = await db.direct_links.find_one({"stats_share_id": share_id})
    if not link or link.get("status") not in ("active", "paused"):
        raise HTTPException(status_code=410, detail=_EXPIRED_DETAIL)

    publisher_id = link.get("publisher_id", "")
    if not publisher_id:
        raise HTTPException(status_code=410, detail=_EXPIRED_DETAIL)

    # Banned/removed publishers lose Direct Link Stats (same rule as admin).
    from app.services.publisher_service import is_publisher_banned_or_removed
    try:
        if await is_publisher_banned_or_removed(publisher_id, db):
            raise HTTPException(status_code=410, detail=_EXPIRED_DETAIL)
    except HTTPException:
        raise
    except Exception:
        pass

    # ── Report configuration (preferences) ────────────────────────────────────
    link_preferences = link.get("preferences") or None
    profile = await db.stats_profiles.find_one({"publisher_id": publisher_id})

    default_prefs = {
        "show_os": True,
        "show_country": True,
        "show_device": True,
        "show_clicks": True,
        "show_unique_clicks": True,
        "show_valid_clicks": True,
        "show_invalid_clicks": False,
        "show_impressions": True,
        "show_conversions": True,
        "show_cr": True,
        "show_fraud_score": False,
        "show_daily_breakdown": True,
        # Default column set: ONLY Windows valid clicks. The admin opts the
        # other OS columns in per publisher via the toggles.
        "show_windows_clicks": True,
        "show_mac_clicks": False,
        "show_android_clicks": False,
    }
    # Priority: link preferences > profile preferences > defaults
    # Each per-OS toggle defaults OFF unless explicitly enabled — a profile
    # written before those keys existed must not suddenly expose Mac/Android.
    prefs = link_preferences or (profile.get("preferences") if profile else None) or default_prefs
    for os_key in ("show_windows_clicks", "show_mac_clicks", "show_android_clicks"):
        if os_key not in prefs:
            prefs[os_key] = default_prefs[os_key]

    # ── Identity mark (#L1 / Pub id) for the page header ─────────────────────
    # The share page header shows which publisher this page belongs to, e.g.
    # "#L1 · Pub bvdrt71" — a short link number + the publisher's public_id.
    # L-number = position of this link among the publisher's links, oldest
    # first (L1 = their first/primary link). Falls back to the masked slug
    # segment when the link has no slug yet.
    publisher = None
    try:
        publisher = await db.publishers.find_one({"_id": ObjectId(publisher_id)})
    except Exception:
        publisher = None
    if not publisher:
        publisher = await db.publishers.find_one({"_id": publisher_id})
    pub_identifier = ""
    if publisher:
        pub_identifier = (
            publisher.get("public_id")
            or publisher.get("name")
            or ""
        )

    link_number = 1
    if link.get("slug"):
        try:
            links_cursor = db.direct_links.find(
                {"publisher_id": publisher_id},
                {"slug": 1, "created_at": 1},
            ).sort("created_at", 1)
            slugs = [d.get("slug") async for d in links_cursor]
            if link["slug"] in slugs:
                link_number = slugs.index(link["slug"]) + 1
        except Exception:
            link_number = 1
    elif link.get("created_at"):
        link_number = 1

    # ── Date range ────────────────────────────────────────────────────────────
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    # ── Aggregate clicks ──────────────────────────────────────────────────────
    # clicks collection uses "publisher_id" as string ObjectId, "timestamp" field,
    # and "os" for operating system.
    click_match = {
        "publisher_id": publisher_id,
        "timestamp": {"$gte": start_date, "$lte": end_date},
    }

    os_pipeline = [
        {"$match": click_match},
        {"$group": {"_id": "$os", "count": {"$sum": 1}}},
    ]
    os_results = await db.clicks.aggregate(os_pipeline).to_list(length=None)

    total_clicks = 0
    windows_clicks = 0
    mac_clicks = 0
    android_clicks = 0
    for row in os_results:
        os_val = (row.get("_id") or "").lower()
        cnt = row.get("count", 0)
        total_clicks += cnt
        if any(w in os_val for w in ("windows", "win")):
            windows_clicks += cnt
        elif any(m in os_val for m in ("mac", "ios", "darwin", "macos")):
            mac_clicks += cnt
        elif "android" in os_val:
            android_clicks += cnt

    # ── Country breakdown (share page country stats) ──────────────────────────
    # Top countries by click volume. Grouped by country_code (stable key);
    # the display name rides the most frequent country_name seen for that code.
    # Clicks without a resolvable country land in "Unknown". Gated by the
    # report preferences like every other block.
    country_breakdown: list = []
    if prefs.get("show_country", True):
        country_pipeline = [
            {"$match": click_match},
            {"$group": {
                "_id": {"$ifNull": ["$country_code", ""]},
                "clicks": {"$sum": 1},
                "names": {"$push": {"$ifNull": ["$country_name", ""]}},
            }},
            {"$sort": {"clicks": -1}},
            {"$limit": 10},
        ]
        country_rows = await db.clicks.aggregate(country_pipeline).to_list(length=None)
        for row in country_rows:
            code = (row.get("_id") or "").strip().upper()
            names = [n for n in (row.get("names") or []) if n]
            # Most frequent stored name for this code (names arrive unsorted;
            # pick the first non-empty as the representative label).
            label = names[0] if names else (code or "Unknown")
            country_breakdown.append({
                "country_code": code or "UNKNOWN",
                "country": label,
                "clicks": row.get("clicks", 0),
            })
        total_for_share = sum(c["clicks"] for c in country_breakdown) or 1
        for c in country_breakdown:
            c["share_pct"] = round(c["clicks"] / total_for_share * 100, 1)

    # ── Manual conversions (entered by admin) ─────────────────────────────────
    # The Direct Link Stats page writes every admin-entered value to BOTH
    # direct_link_manual_conversions and conversion_overrides (same value, same
    # date/publisher/link). Summing both collections therefore double-counted
    # every conversion (entering 1,000,000 showed 2,000,000).
    # direct_link_manual_conversions is the canonical source; a
    # conversion_overrides row is only counted when that exact (date, link) was
    # NOT also recorded there — i.e. overrides entered from elsewhere.
    manual_by_date: dict = defaultdict(int)
    date_str_query = {
        "publisher_id": publisher_id,
        "date": {
            "$gte": start_date.strftime("%Y-%m-%d"),
            "$lte": end_date.strftime("%Y-%m-%d"),
        },
    }
    seen_manual_keys: set = set()
    manual_rows = await db.direct_link_manual_conversions.find(date_str_query).to_list(length=1000)
    for doc in manual_rows:
        seen_manual_keys.add((doc.get("date", ""), doc.get("link_id") or None))
        manual_by_date[doc.get("date", "")] += int(doc.get("conversions", 0) or 0)

    override_rows = await db.conversion_overrides.find(
        {**date_str_query, "is_manual_override": True}
    ).to_list(length=1000)
    for doc in override_rows:
        if (doc.get("date", ""), doc.get("link_id") or None) in seen_manual_keys:
            continue  # same conversion already counted from the canonical source
        manual_by_date[doc.get("date", "")] += int(doc.get("manual_conversions", 0) or 0)

    total_manual_conversions = sum(manual_by_date.values())

    # ── Tracked conversions (direct link events) ─────────────────────────────
    conv_match = {
        "publisher_id": publisher_id,
        "created_at": {"$gte": start_date, "$lte": end_date},
    }
    tracked_conversions = await db.direct_link_events.count_documents(conv_match)
    total_conversions = tracked_conversions + total_manual_conversions

    conversion_rate = (total_conversions / total_clicks * 100) if total_clicks > 0 else 0.0

    # ── Daily breakdown ───────────────────────────────────────────────────────
    daily_breakdown = []
    if prefs.get("show_daily_breakdown", True):
        daily_clicks_pipeline = [
            {"$match": click_match},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
                "clicks": {"$sum": 1},
                "windows_clicks": {"$sum": {"$cond": [
                    {"$regexMatch": {"input": {"$ifNull": ["$os", ""]}, "regex": "windows|win", "options": "i"}},
                    1, 0,
                ]}},
                "mac_clicks": {"$sum": {"$cond": [
                    {"$regexMatch": {"input": {"$ifNull": ["$os", ""]}, "regex": "mac|ios|darwin", "options": "i"}},
                    1, 0,
                ]}},
                "android_clicks": {"$sum": {"$cond": [
                    {"$regexMatch": {"input": {"$ifNull": ["$os", ""]}, "regex": "android", "options": "i"}},
                    1, 0,
                ]}},
            }},
            {"$sort": {"_id": -1}},
            {"$limit": days},
        ]
        daily_clicks_raw = await db.clicks.aggregate(daily_clicks_pipeline).to_list(length=None)

        # Tracked conversions per day
        daily_conv_pipeline = [
            {"$match": conv_match},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                "conversions": {"$sum": 1},
            }},
        ]
        daily_conv_raw = await db.direct_link_events.aggregate(daily_conv_pipeline).to_list(length=None)
        daily_conv_map = {row["_id"]: row["conversions"] for row in daily_conv_raw}

        for row in daily_clicks_raw:
            date_str = row["_id"]
            clicks = row["clicks"]
            conversions = daily_conv_map.get(date_str, 0) + manual_by_date.get(date_str, 0)
            cr = round(conversions / clicks * 100, 2) if clicks > 0 else 0.0
            daily_breakdown.append({
                "date": date_str,
                "clicks": clicks,
                "conversions": conversions,
                "cr": cr,
                "windows_clicks": (
                    row.get("windows_clicks", 0) if prefs.get("show_windows_clicks", True) else 0
                ),
                "mac_clicks": (
                    row.get("mac_clicks", 0) if prefs.get("show_mac_clicks", True) else 0
                ),
                "android_clicks": (
                    row.get("android_clicks", 0) if prefs.get("show_android_clicks", True) else 0
                ),
            })

        # Days that only have manual conversions (no clicks) still need to show
        # their admin-entered numbers.
        covered_dates = {row["_id"] for row in daily_clicks_raw}
        for date_str, conv_count in manual_by_date.items():
            if conv_count > 0 and date_str and date_str not in covered_dates:
                daily_breakdown.append({
                    "date": date_str,
                    "clicks": 0,
                    "conversions": conv_count,
                    "cr": 0.0,
                    "windows_clicks": 0,
                    "mac_clicks": 0,
                    "android_clicks": 0,
                })
        daily_breakdown.sort(key=lambda r: r["date"], reverse=True)

    # ── Insights ──────────────────────────────────────────────────────────────
    avg_daily_clicks = round(total_clicks / days) if days > 0 else 0

    trend = "stable"
    if len(daily_breakdown) >= 14:
        recent_avg = sum(d["clicks"] for d in daily_breakdown[:7]) / 7
        older_avg = sum(d["clicks"] for d in daily_breakdown[7:14]) / 7
        if recent_avg > older_avg * 1.1:
            trend = "up"
        elif recent_avg < older_avg * 0.9:
            trend = "down"

    # Build response based on preferences — NO publisher name/ID exposed.
    response_data = {
        "date_range": f"Last {days} Days",
        "preferences": prefs,
    }

    # Identity mark shown in the page header: "#L1 · Pub bvdrt71". The link
    # number identifies which of the publisher's links this page tracks; the
    # pub identifier is the publisher's public_id (PUB_…) or name. Neither
    # leaks the internal ObjectId.
    response_data["identity"] = {
        "link_number": link_number,
        "pub_id": pub_identifier,
    }

    if prefs.get("show_impressions", True):
        response_data["total_impressions"] = total_clicks

    if prefs.get("show_clicks", True):
        response_data["total_clicks"] = total_clicks

    if prefs.get("show_conversions", True):
        response_data["total_conversions"] = total_conversions
        response_data["manual_conversions"] = total_manual_conversions

    if prefs.get("show_cr", True):
        response_data["conversion_rate"] = round(conversion_rate, 2)

    # Always include these for platform breakdown/filters, but zero-out any OS
    # the admin did not opt into showing — the publisher must not see that OS's
    # clicks when its toggle is off.
    response_data["unique_windows_clicks"] = (
        windows_clicks if prefs.get("show_windows_clicks", True) else 0
    )
    response_data["unique_mac_clicks"] = (
        mac_clicks if prefs.get("show_mac_clicks", True) else 0
    )
    response_data["unique_android_clicks"] = (
        android_clicks if prefs.get("show_android_clicks", True) else 0
    )

    if prefs.get("show_daily_breakdown", True):
        response_data["daily_breakdown"] = daily_breakdown

    response_data["unique_wins"] = windows_clicks + mac_clicks
    response_data["insights"] = {
        "avg_daily_clicks": avg_daily_clicks,
        "trend_direction": trend,
    }

    if prefs.get("show_country", True):
        response_data["country_breakdown"] = country_breakdown

    return {
        "success": True,
        "data": response_data,
    }