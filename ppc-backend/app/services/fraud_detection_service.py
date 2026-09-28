"""
Fraud Detection Service
=======================

Comprehensive fraud detection and traffic classification system.

Traffic Classifications:
- Valid: Legitimate user traffic
- Duplicate: Repeated clicks from same source
- Bot: Automated bot/crawler traffic
- Suspicious: Potentially fraudulent but not confirmed
- Invalid: Confirmed fraudulent/invalid traffic

Detection Signals:
- User-Agent analysis (not sole factor)
- Request headers analysis
- Timing patterns
- IP behavior
- Browser automation signals
- Rate limiting violations
"""

import re
import hashlib
import time
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from user_agents import parse as parse_user_agent
import logging

logger = logging.getLogger(__name__)

# Traffic classification constants
TRAFFIC_VALID = "valid"
TRAFFIC_DUPLICATE = "duplicate"
TRAFFIC_BOT = "bot"
TRAFFIC_SUSPICIOUS = "suspicious"
TRAFFIC_INVALID = "invalid"

# Known bot patterns (not exhaustive - used as one signal among many)
BOT_PATTERNS = [
    r'bot', r'crawler', r'spider', r'scraper',
    r'curl', r'wget', r'python-requests', r'java',
    r'go-http-client', r'axios', r'fetch',
]

# Headless/automation signals
AUTOMATION_SIGNALS = [
    r'headless', r'phantom', r'selenium', r'puppeteer',
    r'playwright', r'webdriver', r'automation',
]

# Known crawler user agents
KNOWN_CRAWLERS = [
    'googlebot', 'bingbot', 'yandex', 'baiduspider',
    'slurp', 'duckduckbot', 'facebookexternalhit',
]


class FraudScore:
    """Fraud score calculator with reasoning."""
    
    def __init__(self):
        self.score = 0  # 0-100 scale (0=legitimate, 100=definitely fraud)
        self.reasons = []
        self.signals = {}
    
    def add_signal(self, name: str, weight: int, reason: str):
        """Add a fraud signal."""
        self.score += weight
        self.reasons.append(reason)
        self.signals[name] = weight
    
    def get_classification(self) -> str:
        """Get traffic classification based on score."""
        if self.score >= 80:
            return TRAFFIC_INVALID
        elif self.score >= 60:
            return TRAFFIC_BOT
        elif self.score >= 40:
            return TRAFFIC_SUSPICIOUS
        elif self.score >= 20:
            return TRAFFIC_DUPLICATE
        else:
            return TRAFFIC_VALID
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "score": min(self.score, 100),
            "classification": self.get_classification(),
            "reasons": self.reasons,
            "signals": self.signals,
        }


def detect_bot_user_agent(user_agent: str) -> Tuple[bool, Optional[str]]:
    """
    Detect if user agent matches known bot patterns.
    Returns (is_bot, reason).
    
    Note: This is ONE signal among many - not used alone for rejection.
    """
    if not user_agent:
        return False, None
    
    user_agent_lower = user_agent.lower()
    
    # Check known crawlers (legitimate)
    for crawler in KNOWN_CRAWLERS:
        if crawler in user_agent_lower:
            return True, f"Known crawler: {crawler}"
    
    # Check bot patterns
    for pattern in BOT_PATTERNS:
        if re.search(pattern, user_agent_lower):
            return True, f"Bot pattern: {pattern}"
    
    # Check automation signals
    for signal in AUTOMATION_SIGNALS:
        if re.search(signal, user_agent_lower):
            return True, f"Automation signal: {signal}"
    
    return False, None


def detect_headless_signals(headers: Dict[str, str], user_agent: str) -> Tuple[bool, List[str]]:
    """
    Detect HEADLESS/automation signals from headers.

    Only affirmative automation evidence counts here (headless UA strings,
    Lighthouse, WebDriver). Missing soft headers (Accept-Language,
    Accept-Encoding, Referer) are NOT automation evidence: in-app browsers
    and Android WebViews routinely omit Accept-Language, and our own redirect
    chain strips the Referer BY DESIGN (Referrer-Policy: no-referrer). They
    were previously scored as headless signals (weight 25), which pushed a
    completely legitimate visitor to score 30 → classified "duplicate" → the
    click was marked invalid for EVERY publisher the visitor went on to
    click (the reported "once they visit one publisher they are invalid for
    all others" behaviour — the classification never varied by publisher).
    Returns (has_signals, list of signals found).
    """
    signals = []

    # Check user agent for automation
    if user_agent:
        ua_lower = user_agent.lower()
        if 'headless' in ua_lower:
            signals.append("Headless in user agent")
        if 'chrome-lighthouse' in ua_lower:
            signals.append("Lighthouse audit")

    # webdriver affirmative signal
    if 'webdriver' in str(headers.get('user-agent', '')).lower():
        signals.append("WebDriver detected")

    return len(signals) > 0, signals


def analyze_user_agent_structure(user_agent: str) -> Tuple[bool, Optional[str]]:
    """
    Analyze user agent structure for anomalies.
    Returns (is_suspicious, reason).
    """
    if not user_agent:
        return True, "Empty user agent"
    
    # Check length
    if len(user_agent) < 20:
        return True, "User agent too short"
    
    if len(user_agent) > 500:
        return True, "User agent too long"
    
    # Parse user agent
    try:
        ua = parse_user_agent(user_agent)
        
        # Check for completely unknown browser
        if ua.browser.family == 'Other' and ua.os.family == 'Other':
            return True, "Unknown browser and OS"
        
        # Check for very old browsers (potential spoofing)
        if ua.browser.version and len(ua.browser.version) > 0:
            major_version = ua.browser.version[0]
            if major_version and int(major_version) < 50 and ua.browser.family in ['Chrome', 'Firefox']:
                return True, f"Very old browser version: {ua.browser.family} {major_version}"
        
    except Exception as e:
        logger.debug(f"UA parsing error: {e}")
        return True, "Failed to parse user agent"
    
    return False, None


async def check_rate_limit(
    db,
    redis,
    key_prefix: str,
    identifier: str,
    limit: int,
    window_seconds: int,
) -> Tuple[bool, int]:
    """
    Check rate limit for an identifier.
    Returns (is_limited, current_count).
    
    Uses Redis for fast rate limiting.
    """
    if not redis:
        return False, 0
    
    try:
        key = f"{key_prefix}:{identifier}"
        
        # Increment counter
        count = await redis.incr(key)
        
        # Set expiry on first request
        if count == 1:
            await redis.expire(key, window_seconds)
        
        return count > limit, count
        
    except Exception as e:
        logger.error(f"Rate limit check error: {e}")
        return False, 0


async def check_duplicate_click(
    db,
    ip_address: str,
    publisher_id: str,
    campaign_id: Optional[str],
    window_minutes: int = 60,
) -> Tuple[bool, Optional[str]]:
    """
    Check if this is a duplicate click from same IP within time window.
    Returns (is_duplicate, click_id of original).
    """
    # Generate fingerprint
    fingerprint_data = f"{ip_address}:{publisher_id}:{campaign_id or 'none'}"
    fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()
    
    # Check for recent click with same fingerprint.
    # The redirect pipeline writes clicks with `timestamp` (not `created_at`);
    # match either field so legacy documents and new inserts both count, and
    # hit the (fingerprint, timestamp) compound index — a mismatched field here
    # used to full-scan the clicks collection on EVERY request.
    since = datetime.utcnow() - timedelta(minutes=window_minutes)
    
    existing = await db.clicks.find_one(
        {
            "fingerprint": fingerprint,
            "$or": [
                {"timestamp": {"$gte": since}},
                {"created_at": {"$gte": since}},
            ],
        },
        {"_id": 1},
    )
    
    if existing:
        return True, str(existing.get("_id"))
    
    return False, None


async def check_ip_abuse(
    db,
    redis,
    ip_address: str,
    hourly_limit: int = 100,
    daily_limit: int = 1000,
) -> Tuple[bool, List[str]]:
    """
    Check if IP is abusing the system with excessive requests.
    Returns (is_abuse, list of reasons).
    """
    reasons = []
    
    # Check hourly limit
    is_limited_hourly, hourly_count = await check_rate_limit(
        db, redis, "ip_hourly", ip_address, hourly_limit, 3600
    )
    
    if is_limited_hourly:
        reasons.append(f"Exceeded hourly limit: {hourly_count} requests")
    
    # Check daily limit
    is_limited_daily, daily_count = await check_rate_limit(
        db, redis, "ip_daily", ip_address, daily_limit, 86400
    )
    
    if is_limited_daily:
        reasons.append(f"Exceeded daily limit: {daily_count} requests")
    
    # Check if IP is on blacklist (if you maintain one)
    try:
        blacklisted = await db.ip_blacklist.find_one({"ip_address": ip_address})
        if blacklisted:
            reasons.append(f"IP blacklisted: {blacklisted.get('reason', 'No reason')}")
    except Exception:
        pass
    
    return len(reasons) > 0, reasons


def analyze_timing_pattern(
    request_times: List[datetime],
    min_interval_seconds: float = 0.5,
) -> Tuple[bool, Optional[str]]:
    """
    Analyze timing patterns for bot-like behavior.
    Too fast or too regular = suspicious.
    """
    if len(request_times) < 2:
        return False, None
    
    # Calculate intervals
    intervals = []
    for i in range(1, len(request_times)):
        delta = (request_times[i] - request_times[i-1]).total_seconds()
        intervals.append(delta)
    
    # Check if requests are too fast
    if any(interval < min_interval_seconds for interval in intervals):
        return True, f"Requests too fast (< {min_interval_seconds}s)"
    
    # Check if intervals are suspiciously regular (bot behavior)
    if len(intervals) >= 3:
        avg_interval = sum(intervals) / len(intervals)
        variance = sum((x - avg_interval) ** 2 for x in intervals) / len(intervals)
        
        # Very low variance = regular pattern = bot
        if variance < 0.1 and avg_interval < 5:
            return True, "Suspiciously regular timing pattern"
    
    return False, None


async def classify_traffic(
    db,
    redis,
    request_data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Comprehensive traffic classification.

    Kept lean for the /click hot path — only checks that need to run
    synchronously are here. IP abuse rate-limits and duplicate DB lookups are
    intentionally skipped: they were causing 2-3 extra Redis/DB round-trips on
    every single click, which saturated the connection pools and caused crashes.
    The stage_screen_traffic pipeline stage already handles rate-limiting and
    per-publisher duplicate detection via Redis before this runs.
    """
    score = FraudScore()

    ip_address   = request_data.get("ip_address", "")
    user_agent   = request_data.get("user_agent", "")
    headers      = request_data.get("headers", {})

    # 1. User agent analysis (weight: 15)
    is_bot_ua, bot_reason = detect_bot_user_agent(user_agent)
    if is_bot_ua:
        if any(crawler in user_agent.lower() for crawler in KNOWN_CRAWLERS):
            score.add_signal("known_crawler", 10, bot_reason)
        else:
            score.add_signal("bot_ua", 15, bot_reason)

    # 2. User agent structure analysis (weight: 10)
    is_suspicious_ua, ua_reason = analyze_user_agent_structure(user_agent)
    if is_suspicious_ua:
        score.add_signal("suspicious_ua", 10, ua_reason)

    # 3. Headless/automation signals (weight: 25)
    has_headless, headless_signals = detect_headless_signals(headers, user_agent)
    if has_headless:
        score.add_signal("headless", 25, f"Headless signals: {', '.join(headless_signals)}")

    # 4. Empty user agent (weight: 15)
    if not user_agent:
        score.add_signal("no_ua", 15, "Empty user agent")

    result = score.to_dict()
    classification = result["classification"]
    result["should_reject"] = classification in [TRAFFIC_INVALID, TRAFFIC_BOT]
    result["should_flag"]   = classification in [TRAFFIC_SUSPICIOUS, TRAFFIC_DUPLICATE]
    return result


async def log_security_event(
    db,
    event_type: str,
    severity: str,
    description: str,
    metadata: Optional[Dict[str, Any]] = None,
):
    """
    Log security event for audit trail — fire-and-forget, never blocks the
    /click response. Errors are swallowed so a logging failure cannot slow
    or crash the hot path.
    """
    import asyncio

    async def _write():
        try:
            await db.security_audit_log.insert_one({
                "event_type": event_type,
                "severity": severity,
                "description": description,
                "metadata": metadata or {},
                "created_at": datetime.utcnow(),
            })
        except Exception:
            pass  # audit log failure must never surface to the visitor

    # Schedule the write as a background task — do not await it.
    asyncio.ensure_future(_write())


def validate_redirect_url(url: str, allowed_domains: Optional[List[str]] = None) -> Tuple[bool, Optional[str]]:
    """
    Validate redirect URL to prevent open redirect vulnerabilities.
    
    Returns (is_valid, reason).
    """
    if not url:
        return False, "Empty URL"
    
    # Check for javascript: or data: schemes
    if re.match(r'^(javascript|data):', url, re.IGNORECASE):
        return False, "Invalid URL scheme"
    
    # Must be HTTP or HTTPS
    if not re.match(r'^https?://', url, re.IGNORECASE):
        return False, "URL must be HTTP or HTTPS"
    
    # Check allowed domains if provided
    if allowed_domains:
        from urllib.parse import urlparse
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # Remove port if present
            if ':' in domain:
                domain = domain.split(':')[0]
            
            # Check if domain matches allowed list
            is_allowed = False
            for allowed in allowed_domains:
                if domain == allowed or domain.endswith('.' + allowed):
                    is_allowed = True
                    break
            
            if not is_allowed:
                return False, f"Domain not in allowed list: {domain}"
                
        except Exception:
            return False, "Failed to parse URL"
    
    return True, None


def sanitize_input(input_string: str, max_length: int = 500) -> str:
    """
    Sanitize user input to prevent XSS and injection attacks.
    """
    if not input_string:
        return ""
    
    # Truncate to max length
    sanitized = input_string[:max_length]
    
    # Remove null bytes
    sanitized = sanitized.replace('\x00', '')
    
    # Remove control characters except newlines and tabs
    sanitized = ''.join(char for char in sanitized if char.isprintable() or char in '\n\t')
    
    # Basic XSS prevention (for display purposes - still use proper escaping in templates)
    sanitized = sanitized.replace('<', '&lt;').replace('>', '&gt;')
    
    return sanitized.strip()


async def check_ssrf_attempt(url: str) -> Tuple[bool, Optional[str]]:
    """
    Check if URL is a potential SSRF (Server-Side Request Forgery) attempt.
    """
    if not url:
        return False, None
    
    url_lower = url.lower()
    
    # Check for localhost/internal IPs
    internal_patterns = [
        r'localhost', r'127\.0\.0\.', r'0\.0\.0\.0',
        r'192\.168\.', r'10\.', r'172\.(1[6-9]|2[0-9]|3[0-1])\.',
        r'\[::1\]', r'\[::ffff:127\.0\.0\.1\]',
    ]
    
    for pattern in internal_patterns:
        if re.search(pattern, url_lower):
            return True, f"Internal IP/hostname detected: {pattern}"
    
    # Check for cloud metadata endpoints
    cloud_metadata = [
        '169.254.169.254',  # AWS, Azure, GCP metadata
        'metadata.google.internal',
    ]
    
    for metadata in cloud_metadata:
        if metadata in url_lower:
            return True, f"Cloud metadata endpoint detected: {metadata}"
    
    return False, None
