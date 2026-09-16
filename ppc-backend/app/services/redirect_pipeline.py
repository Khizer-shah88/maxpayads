"""
Redirect resolution pipeline — the backbone of the redirect service.

One visitor click travels through a fixed sequence of stages. Every stage reads
from and writes to a single `RedirectResolutionContext`, and every stage records
what it decided and why. The context that comes out the far end is a complete,
replayable account of how this visitor reached this URL:

    identify_publisher   Smartlink params → Publisher (+ Website)
    detect_visitor       IP/User-Agent    → OS, country, device
    screen_traffic       existing fraud/tracking logic → valid | flagged | blocked
    record_click         click row written, publisher attribution fixed
    resolve_chain        Anchor → Inter → Prelander Pool  (which domains apply)
    resolve_campaign     which Campaign this click belongs to
    evaluate_offer       Offer eligibility → destination URL
    decide_prelander     Skip Prelander? is a Prelander actually available?
    resolve_cpc          deferred to the background click task
    deliver              final URL handed to the visitor

Two rules this module exists to enforce:

1. The visitor always leaves with a URL. Every stage is wrapped; a stage that
   raises records the failure and the pipeline carries on with the last good
   value, worst case the global fallback.

2. Publisher attribution is fixed once, at `identify_publisher`, and every later
   stage reads it from the context. Nothing re-derives it from the request, so
   it cannot be lost between hops.

The stages delegate to the existing services — this module orchestrates and
traces, it does not re-implement routing, fraud or CPC.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

FALLBACK_URL = "https://example.com"

# Stage names, in the order traffic travels through them.
STAGE_IDENTIFY = "identify_publisher"
STAGE_DETECT = "detect_visitor"
STAGE_SCREEN = "screen_traffic"
STAGE_RECORD = "record_click"
STAGE_CHAIN = "resolve_chain"
STAGE_CAMPAIGN = "resolve_campaign"
STAGE_OFFER = "evaluate_offer"
STAGE_PRELANDER = "decide_prelander"
STAGE_CPC = "resolve_cpc"
STAGE_DELIVER = "deliver"

# A trace is stored on the click document, so it stays small on purpose.
MAX_TRACE_ENTRIES = 40
MAX_DETAIL_CHARS = 300


def _bson_safe(value: Any) -> Any:
    """Reduce a detail value to something safe to store on the click document."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:MAX_DETAIL_CHARS]
    if isinstance(value, (list, tuple)):
        return [_bson_safe(v) for v in list(value)[:10]]
    if isinstance(value, dict):
        return {str(k)[:60]: _bson_safe(v) for k, v in list(value.items())[:10]}
    return str(value)[:MAX_DETAIL_CHARS]


@dataclass
class StageDecision:
    """What one stage decided, and how long it took."""

    stage: str
    outcome: str
    detail: Dict[str, Any] = field(default_factory=dict)
    elapsed_ms: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "stage": self.stage,
            "outcome": self.outcome,
            "detail": self.detail,
            "elapsed_ms": round(self.elapsed_ms, 2),
        }


@dataclass
class RedirectResolutionContext:
    """
    Everything known about one click, accumulated stage by stage.

    Created by `resolve_redirect` from the incoming request and passed through
    each stage. Stages only ever add to it.
    """

    # ── request as received ───────────────────────────────────────────────────
    raw_pub: str = ""
    raw_site: Optional[str] = None
    ip: str = ""
    user_agent: str = ""
    referrer: str = ""
    headers: Dict[str, str] = field(default_factory=dict)
    request_host: Optional[str] = None
    started_at: datetime = field(default_factory=datetime.utcnow)

    # ── identify_publisher ────────────────────────────────────────────────────
    publisher_id: Optional[str] = None
    website_id: Optional[str] = None

    # ── detect_visitor ────────────────────────────────────────────────────────
    os_name: Optional[str] = None
    os_enum: Optional[str] = None
    device_type: Optional[str] = None
    browser: Optional[str] = None
    country_code: Optional[str] = None
    country_name: Optional[str] = None

    # ── screen_traffic ────────────────────────────────────────────────────────
    is_blocked: bool = False
    is_flagged: bool = False
    fraud_reason: Optional[str] = None
    fraud_score: float = 0.0
    traffic_classification: Optional[str] = None

    # ── record_click ──────────────────────────────────────────────────────────
    click_id: Optional[str] = None
    click_status: str = "pending"

    # ── resolve_chain ─────────────────────────────────────────────────────────
    anchor_domain: Optional[str] = None
    inter_url: Optional[str] = None
    prelander_url: Optional[str] = None

    # ── stage_authorize_prelander ─────────────────────────────────────────────
    # High-entropy authorization token for this click's prelander session.
    # Server-side secret — only its signed reference may reach the visitor's
    # cookie (click_router); the raw token never appears in any URL.
    prelander_auth_token: Optional[str] = None

    # ── resolve_campaign / evaluate_offer ─────────────────────────────────────
    campaign_id: Optional[str] = None
    offer_id: Optional[str] = None
    offer_url: Optional[str] = None
    referrer_suppression: bool = False
    targeting_rule_type: Optional[str] = None

    # ── decide_prelander ──────────────────────────────────────────────────────
    skip_prelander: bool = False

    # ── resolve_cpc ───────────────────────────────────────────────────────────
    cpc: Optional[float] = None

    # ── deliver ───────────────────────────────────────────────────────────────
    destination_url: str = FALLBACK_URL

    # The click document as written, kept so later stages and the background
    # task see exactly what was recorded.
    click_document: Dict[str, Any] = field(default_factory=dict)

    # ── trace ─────────────────────────────────────────────────────────────────
    trace: List[StageDecision] = field(default_factory=list)

    def record(self, stage: str, outcome: str, **detail: Any) -> None:
        """Record one stage's decision. `outcome` is a short machine-readable verdict."""
        # The delivery verdict always lands — it is the one entry worth keeping
        # if something upstream ever floods the trace.
        if len(self.trace) >= MAX_TRACE_ENTRIES and stage != STAGE_DELIVER:
            return
        elapsed = (datetime.utcnow() - self.started_at).total_seconds() * 1000
        prior = sum(d.elapsed_ms for d in self.trace)
        self.trace.append(StageDecision(
            stage=stage,
            outcome=outcome,
            detail={k: _bson_safe(v) for k, v in detail.items()},
            elapsed_ms=max(0.0, elapsed - prior),
        ))

    def trace_as_list(self) -> List[Dict[str, Any]]:
        """The trace in a form safe to store on the click document."""
        return [d.as_dict() for d in self.trace]

    def summary(self) -> str:
        """One-line, greppable account of the whole journey."""
        path = " → ".join(f"{d.stage}:{d.outcome}" for d in self.trace)
        return (
            f"[PIPELINE] click={self.click_id or '-'} pub={self.publisher_id or '-'} "
            f"site={self.website_id or '-'} os={self.os_enum or self.os_name or '-'} "
            f"cc={self.country_code or '-'} campaign={self.campaign_id or '-'} "
            f"offer={self.offer_id or '-'} dest={self.destination_url} | {path}"
        )

    def to_click_fields(self) -> Dict[str, Any]:
        """The context fields that belong on the click document."""
        # Duplicate-detection fingerprint — same recipe as
        # fraud_detection_service.check_duplicate_click, so the DB duplicate
        # check can find this click again within its window.
        fingerprint = hashlib.sha256(
            f"{self.ip}:{self.publisher_id}:{self.campaign_id or 'none'}".encode()
        ).hexdigest()
        return {
            "publisher_id": self.publisher_id,
            "website_id": self.website_id,
            "ip_address": self.ip,
            "country_code": self.country_code,
            "country_name": self.country_name,
            "device_type": self.device_type,
            "os": self.os_name,
            "browser": self.browser,
            "user_agent": (self.user_agent or "")[:500],
            "referrer": (self.referrer or "")[:500] or None,
            "fingerprint": fingerprint,
        }


# ══════════════════════════════════════════════════════════════════════════════
# Stages
# ══════════════════════════════════════════════════════════════════════════════

async def stage_identify_publisher(ctx: RedirectResolutionContext, db) -> bool:
    """
    Smartlink params → permanent Publisher ID (+ Website when a site param is present).

    Accepts either a public id (PUB_XXXXXXXX / SITE_XXXXXXXX) or a raw ObjectId.
    This is the only stage that derives publisher attribution; every later stage
    reads `ctx.publisher_id`, so the attribution cannot drift mid-chain.

    Banned/removed publishers are deliberately NOT rejected here — per the
    publisher status rules their existing Smartlinks must keep redirecting and
    their clicks must keep appearing in Admin Statistics.

    Returns False only when the publisher cannot be identified at all — there is
    nothing to attribute the click to, and the visitor gets the fallback.
    """
    from app.utils.public_id_utils import resolve_publisher_id, resolve_website_id

    ctx.publisher_id = await resolve_publisher_id(db, (ctx.raw_pub or "").strip())
    if not ctx.publisher_id:
        logger.warning(f"Invalid publisher identifier: {ctx.raw_pub}")
        ctx.record(STAGE_IDENTIFY, "unknown_publisher", pub=ctx.raw_pub)
        return False

    if ctx.raw_site:
        # Manual publishers never carry a site param — a stray one is dropped,
        # not fatal, so a mis-copied link still routes for the publisher.
        publisher = await db.publishers.find_one(
            {"_id": ctx.publisher_id}, {"publisher_type": 1}
        )
        if publisher and publisher.get("publisher_type") == "manual":
            logger.warning(
                f"site param ignored for manual publisher {ctx.publisher_id}"
            )
            ctx.record(
                STAGE_IDENTIFY, "publisher_only_manual",
                publisher_id=ctx.publisher_id, site_ignored=ctx.raw_site,
            )
            return True

        site = ctx.raw_site.strip().rstrip("/")
        ctx.website_id = await resolve_website_id(db, site)
        if not ctx.website_id:
            # Unknown site is not fatal — the click still belongs to the publisher.
            logger.warning(f"Website not found: {site}, continuing without website binding")
            ctx.record(
                STAGE_IDENTIFY, "publisher_only",
                publisher_id=ctx.publisher_id, site_not_found=site,
            )
            return True

    ctx.record(
        STAGE_IDENTIFY,
        "publisher_and_website" if ctx.website_id else "publisher_only",
        publisher_id=ctx.publisher_id, website_id=ctx.website_id,
    )
    return True


async def stage_detect_visitor(ctx: RedirectResolutionContext) -> None:
    """IP + User-Agent → OS, device, browser, country. Existing detection logic."""
    from app.utils.ua_parser import parse_user_agent
    from app.utils.geo_utils import lookup_ip
    from app.core.glossary import normalize_os

    device_info = parse_user_agent(ctx.user_agent)
    ctx.device_type = device_info["device_type"]
    ctx.os_name = device_info["os"]
    ctx.browser = device_info["browser"]
    # `os_name` stays exactly as detected — it is what gets stored on the click.
    # `os_enum` is the same value resolved onto the fixed OS enum, for targeting
    # and for reading the trace.
    ctx.os_enum = normalize_os(ctx.os_name)
    ctx.country_code, ctx.country_name = lookup_ip(ctx.ip)

    ctx.record(
        STAGE_DETECT, "detected",
        os=ctx.os_name, os_enum=ctx.os_enum,
        device=ctx.device_type, country=ctx.country_code,
    )


async def stage_screen_traffic(ctx: RedirectResolutionContext, db, redis) -> None:
    """
    Run the existing fraud/tracking logic and record the verdict.

      blocked  → bot / datacenter / rate limit: click is invalid, visitor gets
                 the fallback and never reaches an offer.
      flagged  → suspicious / duplicate: click is recorded invalid but the
                 visitor is still routed to the real offer.
      valid    → click goes to the background task for final validation.

    This stage only orchestrates; the detection itself stays in
    `fraud_detection_service`.
    """
    from app.services import fraud_detection_service as fds
    from app.utils.ip_utils import is_datacenter_ip
    from app.utils.ua_parser import is_bot_user_agent
    from app.core.constants import (
        MAX_CLICKS_PER_IP_PER_MINUTE,
        REDIS_CLICK_RATE_PREFIX,
        REDIS_DUPLICATE_CLICK_PREFIX,
        DUPLICATE_CLICK_WINDOW_SECONDS,
    )

    def _verdict(blocked, flagged, reason, score, classification, outcome):
        ctx.is_blocked = blocked
        ctx.is_flagged = flagged
        ctx.fraud_reason = reason
        ctx.fraud_score = score
        ctx.traffic_classification = classification
        ctx.click_status = "pending" if outcome == "valid" else "invalid"
        ctx.record(
            STAGE_SCREEN, outcome,
            reason=reason, score=score, classification=classification,
        )

    # Legacy checks, kept in order — each is a hard block.
    if is_bot_user_agent(ctx.user_agent):
        return _verdict(True, False, "bot_user_agent", 1.0, fds.TRAFFIC_BOT, "blocked")

    if is_datacenter_ip(ctx.ip):
        return _verdict(True, False, "datacenter_ip", 0.95, fds.TRAFFIC_INVALID, "blocked")

    try:
        key = f"{REDIS_CLICK_RATE_PREFIX}{ctx.ip}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 60)
        if count > MAX_CLICKS_PER_IP_PER_MINUTE:
            return _verdict(True, False, "rate_limit_exceeded", 0.90, fds.TRAFFIC_INVALID, "blocked")
    except Exception as e:
        logger.warning(f"Redis rate limit check failed: {e}")

    # Duplicate IP + website — soft flag, still routed.
    try:
        site_suffix = f":{ctx.website_id}" if ctx.website_id else ""
        dup_key = f"{REDIS_DUPLICATE_CLICK_PREFIX}{ctx.ip}{site_suffix}"
        if await redis.exists(dup_key):
            return _verdict(False, True, "duplicate_ip", 0.85, fds.TRAFFIC_DUPLICATE, "flagged")
        await redis.setex(dup_key, DUPLICATE_CLICK_WINDOW_SECONDS, "1")
    except Exception as e:
        logger.warning(f"Redis duplicate check failed: {e}")

    # Comprehensive fraud detection.
    try:
        result = await fds.classify_traffic(db, redis, {
            "ip_address": ctx.ip,
            "user_agent": ctx.user_agent,
            "headers": ctx.headers,
            "publisher_id": ctx.publisher_id,
            "campaign_id": None,
            "referer": ctx.referrer,
        })
        reasons = result["reasons"]
        reason = "; ".join(reasons[:3]) if reasons else None
        score = result["score"] / 100.0
        classification = result["classification"]

        if result["should_reject"]:
            return _verdict(True, False, reason, score, classification, "blocked")
        if result["should_flag"]:
            return _verdict(False, True, reason, score, classification, "flagged")
        return _verdict(False, False, None, score, classification, "valid")
    except Exception as e:
        logger.error(f"Fraud detection service error: {e}")
        # Never block a visitor because screening itself failed.
        return _verdict(False, False, None, 0.0, fds.TRAFFIC_VALID, "valid")


async def stage_record_click(ctx: RedirectResolutionContext, db) -> bool:
    """
    Write the click, fixing publisher attribution before any routing happens.

    Recorded first on purpose: a click whose routing later fails is still a click
    that happened, and must still appear in Statistics.
    """
    click_data = ctx.to_click_fields()
    click_data.update({
        "status": ctx.click_status,
        "is_valid": False,
        "fraud_reason": ctx.fraud_reason,
        "fraud_score": ctx.fraud_score,
        "traffic_classification": ctx.traffic_classification,
        "cpc": 0.0,
        "earnings": 0.0,
        "processed": ctx.is_blocked or ctx.is_flagged,
        "timestamp": ctx.started_at,
    })
    ctx.click_document = click_data

    try:
        result = await db.clicks.insert_one(click_data.copy())
        ctx.click_id = str(result.inserted_id)
    except Exception as e:
        logger.error(f"Failed to insert click: {e}")
        ctx.record(STAGE_RECORD, "write_failed", error=str(e))
        return False

    ctx.record(
        STAGE_RECORD, "recorded",
        click_id=ctx.click_id, status=ctx.click_status, publisher_id=ctx.publisher_id,
    )
    return True


async def _log_screening_outcome(ctx: RedirectResolutionContext, db) -> None:
    """Record a blocked or flagged click against the publisher and the fraud log."""
    from app.services.fraud_service import log_fraud
    from app.services.earnings_service import (
        update_publisher_invalid_click,
        update_website_stats,
    )
    from app.services import fraud_detection_service as fds

    blocked = ctx.is_blocked
    try:
        await fds.log_security_event(
            db,
            event_type="fraud_detected" if blocked else "suspicious_traffic",
            severity="warning" if blocked else "info",
            description=f"{'Blocked' if blocked else 'Flagged'} traffic: {ctx.fraud_reason}",
            metadata={
                "click_id": ctx.click_id,
                "ip": ctx.ip,
                "classification": ctx.traffic_classification,
                "fraud_score": ctx.fraud_score,
            },
        )
        await log_fraud(ctx.click_id, ctx.click_document, ctx.fraud_reason, ctx.fraud_score, db)
        await update_publisher_invalid_click(ctx.publisher_id, db)
        if ctx.website_id:
            await update_website_stats(ctx.website_id, 0.0, False, db)
    except Exception as e:
        logger.warning(f"Failed to log {'blocked' if blocked else 'flagged'} click: {e}")


async def stage_resolve_route(ctx: RedirectResolutionContext, db, redis) -> None:
    """
    Chain → Campaign → Offer → Prelander decision, in one delegated call.

    `route_click` owns those four resolutions and their fallback chains; passing
    the context in makes each of its decisions land in the trace. A failure here
    leaves `destination_url` at the fallback rather than dropping the visitor.
    """
    from app.services.traffic_router import route_click

    try:
        destination, referrer_suppression = await route_click(
            ctx.click_document, db, redis, ctx=ctx,
        )
        ctx.destination_url = destination
        ctx.referrer_suppression = referrer_suppression
    except Exception as e:
        logger.error(f"Traffic routing error: {e}")
        ctx.record(STAGE_OFFER, "routing_error", error=str(e))
        ctx.destination_url = FALLBACK_URL


async def stage_resolve_cpc(ctx: RedirectResolutionContext, db) -> None:
    """
    Hand the click to the background task, which resolves CPC and credits earnings.

    CPC stays off the request path deliberately — the visitor must not wait on
    it. The task appends its own CPC decision to this click's trace, so the
    stored trace ends up covering the whole journey.

    Flagged clicks were already settled at zero by `_log_screening_outcome` and
    are not queued.
    """
    if ctx.is_flagged:
        ctx.record(STAGE_CPC, "skipped_flagged", cpc=0.0)
        return

    try:
        from app.tasks.click_tasks import process_click

        payload = {
            k: v.isoformat() if hasattr(v, "isoformat") else v
            for k, v in ctx.click_document.items()
        }
        process_click.delay(ctx.click_id, payload)
        ctx.record(STAGE_CPC, "deferred_to_task", click_id=ctx.click_id)
    except Exception as e:
        logger.warning(f"Failed to queue click task: {e}")
        ctx.record(STAGE_CPC, "queue_failed", error=str(e))


async def _finalize(ctx: RedirectResolutionContext, db, outcome: str) -> None:
    """
    Close the trace and persist what the click resolved to.

    One update covers both the destination and the trace, so tracing costs no
    extra round trip. Never fatal — a visitor is not held up by bookkeeping.
    """
    from app.config import settings

    ctx.record(STAGE_DELIVER, outcome, url=ctx.destination_url)
    logger.info(ctx.summary())

    if not ctx.click_id:
        return

    update: Dict[str, Any] = {"destination_url": ctx.destination_url}
    # Persist campaign/offer attribution alongside the destination. Without
    # these, the async click task (click_tasks) can never find the matched
    # offer, so offer-level CPC and campaign analytics silently break.
    if ctx.campaign_id:
        update["campaign_id"] = str(ctx.campaign_id)
    if ctx.offer_id:
        update["offer_id"] = str(ctx.offer_id)
    if getattr(settings, "REDIRECT_TRACE_ENABLED", True):
        update["resolution_trace"] = ctx.trace_as_list()

    try:
        from bson import ObjectId

        await db.clicks.update_one({"_id": ObjectId(ctx.click_id)}, {"$set": update})
    except Exception as e:
        logger.debug(f"Failed to persist resolution trace: {e}")


async def stage_authorize_prelander(ctx: RedirectResolutionContext, db, redis) -> None:
    """
    Create the prelander authorization session for this click, if the routed
    destination is a managed prelander hop (/d/{slug} on an Inter/Prelander
    domain).

    Reuses the existing Redis and the click already recorded by
    stage_record_click. The session carries the full internal context —
    publisher, site, campaign, offer, prelander host, chain, OS/device,
    country, referrer — all server-side; only the high-entropy token ever
    leaves the server (as the optional cookie reference). Bound to
    (client IP, User-Agent) and to the slug hash so the authorization only
    ever covers THIS click's prelander route.

    Fail-open by design at creation time: if the session cannot be written the
    click still redirects normally (the prelander side then shows its neutral
    page). Authorization must never break the "visitor always leaves with a
    URL" rule.
    """
    dest = ctx.destination_url or ""
    if "/d/" not in dest:
        return  # direct campaign URL (bypass) or fallback — nothing to authorize

    try:
        slug = dest.rstrip("/").rsplit("/d/", 1)[-1]
    except Exception:
        return
    if not slug:
        return

    from app.services import prelander_auth_service as pas
    from app.utils.ip_utils import get_client_ip

    ip = get_client_ip(ctx.headers, ctx.ip or "0.0.0.0")

    # STEP 9 — the SELECTED prelander host, not the entry (Inter) host. The
    # session's prelander binding must name the landing-page domain the
    # visitor is actually heading to, so the access middleware's domain check
    # (STEP 5) pins authorization to the right prelander. route_click already
    # resolved the exact selected prelander onto ctx.prelander_url — reuse it
    # verbatim so the authorization and the routing can never disagree.
    prelander_host = ""
    try:
        from urllib.parse import urlparse
        from app.services.domain_service import normalize_domain

        selected = getattr(ctx, "prelander_url", None) or ""
        if selected:
            prelander_host = normalize_domain(selected)
        if not prelander_host:
            # No managed prelander (legacy lander hop) — bind to the
            # destination host as the best available statement of where the
            # visitor is heading.
            prelander_host = (urlparse(dest).hostname or "").lower()
    except Exception:
        try:
            from urllib.parse import urlparse
            prelander_host = (urlparse(dest).hostname or "").lower()
        except Exception:
            prelander_host = ""

    # Chain context — the id of the admin-built chain that drove this click,
    # when one matched (resolved by route_click via resolve_active_chain).
    chain_id = ""
    try:
        from app.services.traffic_router import resolve_active_chain
        chain = await resolve_active_chain(
            db, ctx.publisher_id, getattr(ctx, "request_host", None),
        )
        if chain and chain.get("_id") is not None:
            chain_id = str(chain["_id"])
    except Exception:
        chain_id = ""

    session = await pas.create_authorization(
        click_id=ctx.click_id or "",
        slug=slug,
        ip=ip,
        user_agent=ctx.user_agent or "",
        redis=redis,
        prelander_host=prelander_host,
        # ── full internal context (server-side only) ──
        publisher_id=ctx.publisher_id or "",
        website_id=ctx.website_id or "",
        campaign_id=str(ctx.campaign_id or ""),
        offer_id=str(ctx.offer_id or ""),
        chain_id=chain_id,
        os=ctx.os_name or "",
        device_type=ctx.device_type or "",
        country_code=ctx.country_code or "",
        referrer=ctx.referrer or "",
    )
    # Keep the token on the context so the /click handler can mint the signed
    # cookie reference from it (click_router).
    ctx.prelander_auth_token = session.token if session else ""
    ctx.record(
        STAGE_PRELANDER, "authorized" if session else "authorization_skipped",
        click_id=ctx.click_id or None, host=prelander_host or None,
    )


async def resolve_redirect(ctx: RedirectResolutionContext, db, redis) -> RedirectResolutionContext:
    """
    Run one click through every stage and return the completed context.

    The caller turns `ctx.destination_url` and `ctx.referrer_suppression` into a
    response. There is no path out of here without a destination.
    """
    if not await stage_identify_publisher(ctx, db):
        ctx.destination_url = FALLBACK_URL
        await _finalize(ctx, db, "fallback_unknown_publisher")
        return ctx

    await stage_detect_visitor(ctx)
    await stage_screen_traffic(ctx, db, redis)

    if not await stage_record_click(ctx, db):
        ctx.destination_url = FALLBACK_URL
        await _finalize(ctx, db, "fallback_click_not_recorded")
        return ctx

    # Blocked traffic never reaches an offer.
    if ctx.is_blocked:
        await _log_screening_outcome(ctx, db)
        ctx.destination_url = FALLBACK_URL
        await _finalize(ctx, db, "fallback_blocked")
        return ctx

    # Flagged traffic is settled at zero, then routed to the real offer anyway.
    if ctx.is_flagged:
        await _log_screening_outcome(ctx, db)

    await stage_resolve_route(ctx, db, redis)
    await stage_authorize_prelander(ctx, db, redis)
    await stage_resolve_cpc(ctx, db)
    await _finalize(ctx, db, "routed")
    return ctx


def context_from_request(request, pub: str, site: Optional[str]) -> RedirectResolutionContext:
    """Build a pipeline context from an incoming Smartlink request."""
    from app.utils.ip_utils import get_client_ip

    headers = dict(request.headers)
    return RedirectResolutionContext(
        raw_pub=pub,
        raw_site=site,
        ip=get_client_ip(headers, request.client.host if request.client else "0.0.0.0"),
        user_agent=headers.get("user-agent", ""),
        # Referrer: header first, then ?ref= passed along by the Anchor domain.
        referrer=headers.get("referer", "") or request.query_params.get("ref", ""),
        headers=headers,
        request_host=(headers.get("host", "") or "").split(":")[0].lower() or None,
    )
