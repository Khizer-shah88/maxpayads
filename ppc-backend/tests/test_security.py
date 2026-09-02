"""
Security and Fraud Detection Tests
===================================

Comprehensive security testing for:
- Bot detection
- Fraud classification
- Rate limiting
- Input validation
- IDOR protection
- Open redirect protection
- SSRF protection
- XSS protection
"""

import pytest
from datetime import datetime, timedelta

from app.services import fraud_detection_service as fds
from app.middleware.security_middleware import (
    validate_object_id,
    check_resource_ownership,
    sanitize_error_message,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Bot Detection Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestBotDetection:
    """Test bot detection functionality."""
    
    def test_detect_known_crawler(self):
        """Test detection of known crawlers."""
        user_agent = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
        
        is_bot, reason = fds.detect_bot_user_agent(user_agent)
        
        assert is_bot is True
        assert "googlebot" in reason.lower()
    
    def test_detect_bot_pattern(self):
        """Test detection of generic bot patterns."""
        user_agents = [
            "python-requests/2.28.0",
            "curl/7.68.0",
            "bot/1.0",
            "scraper-tool",
        ]
        
        for ua in user_agents:
            is_bot, reason = fds.detect_bot_user_agent(ua)
            assert is_bot is True, f"Failed to detect bot: {ua}"
    
    def test_detect_automation(self):
        """Test detection of automation tools."""
        user_agents = [
            "HeadlessChrome/91.0",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/91.0.4472.114 Safari/537.36",
            "Selenium WebDriver",
            "Puppeteer/1.0",
        ]
        
        for ua in user_agents:
            is_bot, reason = fds.detect_bot_user_agent(ua)
            assert is_bot is True, f"Failed to detect automation: {ua}"
    
    def test_legitimate_browser_not_detected(self):
        """Test that legitimate browsers are not flagged."""
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0",
        ]
        
        for ua in user_agents:
            is_bot, reason = fds.detect_bot_user_agent(ua)
            assert is_bot is False, f"False positive for legitimate browser: {ua}"


# ═══════════════════════════════════════════════════════════════════════════════
# Headless Detection Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestHeadlessDetection:
    """Test headless browser detection."""
    
    def test_detect_headless_user_agent(self):
        """Test detection via user agent."""
        headers = {}
        user_agent = "HeadlessChrome/91.0"
        
        has_signals, signals = fds.detect_headless_signals(headers, user_agent)
        
        assert has_signals is True
        assert any("headless" in s.lower() for s in signals)
    
    def test_detect_missing_headers(self):
        """Test detection via missing headers."""
        headers = {
            "user-agent": "Chrome/120.0",
            # Missing accept-language and accept-encoding
        }
        user_agent = headers["user-agent"]
        
        has_signals, signals = fds.detect_headless_signals(headers, user_agent)
        
        assert has_signals is True
        assert any("missing" in s.lower() for s in signals)
    
    def test_legitimate_browser_headers(self):
        """Test that legitimate browser headers don't trigger false positives."""
        headers = {
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0",
            "accept-language": "en-US,en;q=0.9",
            "accept-encoding": "gzip, deflate, br",
            "accept": "text/html,application/xhtml+xml",
        }
        user_agent = headers["user-agent"]
        
        has_signals, signals = fds.detect_headless_signals(headers, user_agent)
        
        # Should have minimal or no signals
        assert len(signals) <= 1  # Allow one minor signal


# ═══════════════════════════════════════════════════════════════════════════════
# User Agent Structure Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestUserAgentStructure:
    """Test user agent structure analysis."""
    
    def test_empty_user_agent(self):
        """Test empty user agent is flagged."""
        is_suspicious, reason = fds.analyze_user_agent_structure("")
        
        assert is_suspicious is True
        assert "empty" in reason.lower()
    
    def test_too_short_user_agent(self):
        """Test very short user agent is flagged."""
        is_suspicious, reason = fds.analyze_user_agent_structure("Bot")
        
        assert is_suspicious is True
        assert "short" in reason.lower()
    
    def test_too_long_user_agent(self):
        """Test excessively long user agent is flagged."""
        ua = "A" * 600
        is_suspicious, reason = fds.analyze_user_agent_structure(ua)
        
        assert is_suspicious is True
        assert "long" in reason.lower()
    
    def test_valid_user_agent_structure(self):
        """Test valid user agent passes checks."""
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0"
        is_suspicious, reason = fds.analyze_user_agent_structure(ua)
        
        assert is_suspicious is False


# ═══════════════════════════════════════════════════════════════════════════════
# Duplicate Detection Tests
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestDuplicateDetection:
    """Test duplicate click detection."""
    
    async def test_first_click_not_duplicate(self, db):
        """Test first click is not flagged as duplicate."""
        is_dup, click_id = await fds.check_duplicate_click(
            db, "192.168.1.1", "pub123", "camp456"
        )
        
        assert is_dup is False
        assert click_id is None
    
    async def test_duplicate_click_detected(self, db):
        """Test duplicate click within window is detected."""
        from bson import ObjectId
        import hashlib
        
        # Create fingerprint
        fingerprint_data = "192.168.1.1:pub123:camp456"
        fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()
        
        # Insert original click
        original = {
            "fingerprint": fingerprint,
            "ip_address": "192.168.1.1",
            "publisher_id": "pub123",
            "campaign_id": "camp456",
            "created_at": datetime.utcnow(),
        }
        result = await db.clicks.insert_one(original)
        original_id = str(result.inserted_id)
        
        # Check for duplicate
        is_dup, click_id = await fds.check_duplicate_click(
            db, "192.168.1.1", "pub123", "camp456"
        )
        
        assert is_dup is True
        assert click_id == original_id
        
        # Cleanup
        await db.clicks.delete_one({"_id": result.inserted_id})
    
    async def test_old_click_not_duplicate(self, db):
        """Test old click outside window is not flagged."""
        import hashlib
        
        fingerprint_data = "192.168.1.1:pub123:camp456"
        fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()
        
        # Insert old click (2 hours ago)
        old_click = {
            "fingerprint": fingerprint,
            "ip_address": "192.168.1.1",
            "created_at": datetime.utcnow() - timedelta(hours=2),
        }
        result = await db.clicks.insert_one(old_click)
        
        # Check for duplicate (with 60 minute window)
        is_dup, click_id = await fds.check_duplicate_click(
            db, "192.168.1.1", "pub123", "camp456", window_minutes=60
        )
        
        assert is_dup is False
        
        # Cleanup
        await db.clicks.delete_one({"_id": result.inserted_id})


# ═══════════════════════════════════════════════════════════════════════════════
# Traffic Classification Tests
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestTrafficClassification:
    """Test comprehensive traffic classification."""
    
    async def test_classify_valid_traffic(self, db):
        """Test classification of legitimate traffic."""
        request_data = {
            "ip_address": "203.0.113.1",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
            "headers": {
                "accept-language": "en-US,en;q=0.9",
                "accept-encoding": "gzip, deflate, br",
            },
            "publisher_id": "pub123",
            "referer": "https://example.com",
        }
        
        result = await fds.classify_traffic(db, None, request_data)
        
        assert result["classification"] == fds.TRAFFIC_VALID
        assert result["score"] < 40
        assert result["should_reject"] is False
    
    async def test_classify_bot_traffic(self, db):
        """Test classification of bot traffic."""
        request_data = {
            "ip_address": "203.0.113.1",
            "user_agent": "python-requests/2.28.0",
            "headers": {},
            "publisher_id": "pub123",
        }
        
        result = await fds.classify_traffic(db, None, request_data)
        
        assert result["classification"] in [fds.TRAFFIC_BOT, fds.TRAFFIC_SUSPICIOUS]
        assert result["score"] >= 15
    
    async def test_classify_headless_traffic(self, db):
        """Test classification of headless browser traffic."""
        request_data = {
            "ip_address": "203.0.113.1",
            "user_agent": "HeadlessChrome/91.0",
            "headers": {},
            "publisher_id": "pub123",
        }
        
        result = await fds.classify_traffic(db, None, request_data)
        
        assert result["classification"] in [fds.TRAFFIC_BOT, fds.TRAFFIC_SUSPICIOUS, fds.TRAFFIC_INVALID]
        assert result["score"] >= 25
        assert "headless" in str(result["signals"]).lower()
    
    async def test_fraud_score_accumulation(self, db):
        """Test that fraud score accumulates from multiple signals."""
        request_data = {
            "ip_address": "203.0.113.1",
            "user_agent": "",  # Empty UA
            "headers": {},  # Missing headers
            "publisher_id": "pub123",
            "referer": "",  # No referer
        }
        
        result = await fds.classify_traffic(db, None, request_data)
        
        # Should have multiple signals
        assert len(result["reasons"]) >= 2
        assert result["score"] > 20


# ═══════════════════════════════════════════════════════════════════════════════
# URL Validation Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestURLValidation:
    """Test URL validation for security."""
    
    def test_validate_https_url(self):
        """Test valid HTTPS URL."""
        is_valid, reason = fds.validate_redirect_url("https://example.com/path")
        
        assert is_valid is True
        assert reason is None
    
    def test_reject_javascript_url(self):
        """Test rejection of javascript: URLs."""
        is_valid, reason = fds.validate_redirect_url("javascript:alert(1)")
        
        assert is_valid is False
        assert "scheme" in reason.lower()
    
    def test_reject_data_url(self):
        """Test rejection of data: URLs."""
        is_valid, reason = fds.validate_redirect_url("data:text/html,<script>alert(1)</script>")
        
        assert is_valid is False
        assert "scheme" in reason.lower()
    
    def test_reject_non_http_url(self):
        """Test rejection of non-HTTP URLs."""
        is_valid, reason = fds.validate_redirect_url("ftp://example.com")
        
        assert is_valid is False
    
    def test_allowed_domains_restriction(self):
        """Test domain whitelist restriction."""
        allowed = ["example.com", "trusted.com"]
        
        # Allowed domain
        is_valid, reason = fds.validate_redirect_url("https://example.com", allowed)
        assert is_valid is True
        
        # Subdomain of allowed
        is_valid, reason = fds.validate_redirect_url("https://sub.example.com", allowed)
        assert is_valid is True
        
        # Not allowed
        is_valid, reason = fds.validate_redirect_url("https://evil.com", allowed)
        assert is_valid is False
        assert "not in allowed list" in reason.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# SSRF Protection Tests
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestSSRFProtection:
    """Test SSRF protection."""
    
    async def test_detect_localhost(self):
        """Test detection of localhost URLs."""
        urls = [
            "http://localhost/admin",
            "http://127.0.0.1/metadata",
            "http://0.0.0.0/",
        ]
        
        for url in urls:
            is_ssrf, reason = await fds.check_ssrf_attempt(url)
            assert is_ssrf is True, f"Failed to detect SSRF: {url}"
    
    async def test_detect_internal_ips(self):
        """Test detection of internal IP ranges."""
        urls = [
            "http://192.168.1.1/",
            "http://10.0.0.1/",
            "http://172.16.0.1/",
        ]
        
        for url in urls:
            is_ssrf, reason = await fds.check_ssrf_attempt(url)
            assert is_ssrf is True, f"Failed to detect internal IP: {url}"
    
    async def test_detect_cloud_metadata(self):
        """Test detection of cloud metadata endpoints."""
        urls = [
            "http://169.254.169.254/latest/meta-data/",
            "http://metadata.google.internal/",
        ]
        
        for url in urls:
            is_ssrf, reason = await fds.check_ssrf_attempt(url)
            assert is_ssrf is True, f"Failed to detect metadata endpoint: {url}"
    
    async def test_allow_external_urls(self):
        """Test that external URLs are allowed."""
        urls = [
            "https://example.com",
            "https://api.service.com/endpoint",
        ]
        
        for url in urls:
            is_ssrf, reason = await fds.check_ssrf_attempt(url)
            assert is_ssrf is False, f"False positive for external URL: {url}"


# ═══════════════════════════════════════════════════════════════════════════════
# Input Sanitization Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestInputSanitization:
    """Test input sanitization."""
    
    def test_sanitize_xss_attempt(self):
        """Test XSS sanitization."""
        malicious = "<script>alert('XSS')</script>"
        sanitized = fds.sanitize_input(malicious)
        
        assert "<script>" not in sanitized
        assert "&lt;script&gt;" in sanitized
    
    def test_sanitize_length_limit(self):
        """Test length limiting."""
        long_input = "A" * 1000
        sanitized = fds.sanitize_input(long_input, max_length=100)
        
        assert len(sanitized) == 100
    
    def test_sanitize_null_bytes(self):
        """Test null byte removal."""
        input_with_null = "test\x00string"
        sanitized = fds.sanitize_input(input_with_null)
        
        assert "\x00" not in sanitized
    
    def test_sanitize_control_characters(self):
        """Test control character removal."""
        input_with_control = "test\x01\x02string"
        sanitized = fds.sanitize_input(input_with_control)
        
        assert "\x01" not in sanitized
        assert "\x02" not in sanitized


# ═══════════════════════════════════════════════════════════════════════════════
# IDOR Protection Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestIDORProtection:
    """Test IDOR (Insecure Direct Object Reference) protection."""
    
    def test_validate_object_id_valid(self):
        """Test valid ObjectId format."""
        assert validate_object_id("507f1f77bcf86cd799439011") is True
        assert validate_object_id("507f1f77bcf86cd799439012") is True
    
    def test_validate_object_id_invalid(self):
        """Test invalid ObjectId formats."""
        assert validate_object_id("invalid") is False
        assert validate_object_id("123") is False
        assert validate_object_id("") is False
        assert validate_object_id("507f1f77bcf86cd79943901g") is False  # Invalid char
    
    def test_check_resource_ownership_owner(self):
        """Test owner can access resource."""
        assert check_resource_ownership("user123", "user123", is_admin=False) is True
    
    def test_check_resource_ownership_not_owner(self):
        """Test non-owner cannot access resource."""
        assert check_resource_ownership("user123", "user456", is_admin=False) is False
    
    def test_check_resource_ownership_admin(self):
        """Test admin can access any resource."""
        assert check_resource_ownership("user123", "user456", is_admin=True) is True


# ═══════════════════════════════════════════════════════════════════════════════
# Error Message Sanitization Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestErrorSanitization:
    """Test error message sanitization to prevent information leakage."""
    
    def test_sanitize_internal_paths(self):
        """Test removal of internal file paths."""
        error = Exception("Error in /app/services/fraud_detection.py line 123")
        sanitized = sanitize_error_message(error)
        
        assert "/app/" not in sanitized
        assert "[file]" in sanitized
    
    def test_sanitize_object_ids(self):
        """Test removal of ObjectIds."""
        error = Exception("Invalid ObjectId('507f1f77bcf86cd799439011')")
        sanitized = sanitize_error_message(error)
        
        assert "507f1f77bcf86cd799439011" not in sanitized
        assert "[id]" in sanitized
    
    def test_sanitize_duplicate_key_error(self):
        """Test generic message for duplicate key errors."""
        error = Exception("E11000 duplicate key error collection: test.users index: email_1")
        sanitized = sanitize_error_message(error)
        
        assert "E11000" not in sanitized
        assert "already exists" in sanitized.lower()
    
    def test_truncate_long_errors(self):
        """Test truncation of very long error messages."""
        long_error = Exception("A" * 300)
        sanitized = sanitize_error_message(long_error)
        
        assert len(sanitized) < 250


# ═══════════════════════════════════════════════════════════════════════════════
# Timing Pattern Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestTimingPatterns:
    """Test timing pattern analysis."""
    
    def test_detect_too_fast_requests(self):
        """Test detection of requests that are too fast."""
        now = datetime.utcnow()
        times = [
            now,
            now + timedelta(milliseconds=100),
            now + timedelta(milliseconds=200),
        ]
        
        is_suspicious, reason = fds.analyze_timing_pattern(times, min_interval_seconds=0.5)
        
        assert is_suspicious is True
        assert "too fast" in reason.lower()
    
    def test_detect_regular_pattern(self):
        """Test detection of suspiciously regular patterns."""
        now = datetime.utcnow()
        times = [
            now + timedelta(seconds=i * 2) for i in range(5)
        ]
        
        is_suspicious, reason = fds.analyze_timing_pattern(times, min_interval_seconds=0.5)
        
        assert is_suspicious is True
        assert "regular" in reason.lower()
    
    def test_allow_natural_timing(self):
        """Test that natural human timing is allowed."""
        now = datetime.utcnow()
        times = [
            now,
            now + timedelta(seconds=3),
            now + timedelta(seconds=8),
            now + timedelta(seconds=15),
        ]
        
        is_suspicious, reason = fds.analyze_timing_pattern(times, min_interval_seconds=0.5)
        
        assert is_suspicious is False
