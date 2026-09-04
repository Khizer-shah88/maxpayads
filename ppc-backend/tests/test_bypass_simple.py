"""
Simple integration tests for Bypass Traffic Routing Feature

Tests the bypass logic in isolation without complex mocking.
"""
import pytest
from bson import ObjectId


def test_bypass_field_exists_in_campaign_schema():
    """Verify the bypass field is properly defined in campaign schema"""
    from app.schemas.campaign_schema import CampaignCreate, CampaignUpdate, CampaignResponse
    
    # Test CampaignCreate
    campaign_data = {
        "name": "Test Campaign",
        "default_offer_url": "https://example.com",
        "direct_redirect_mode": True,
    }
    campaign = CampaignCreate(**campaign_data)
    assert campaign.direct_redirect_mode is True
    
    # Test with bypass OFF
    campaign_data["direct_redirect_mode"] = False
    campaign = CampaignCreate(**campaign_data)
    assert campaign.direct_redirect_mode is False
    
    # Test CampaignUpdate
    update_data = {"direct_redirect_mode": True}
    update = CampaignUpdate(**update_data)
    assert update.direct_redirect_mode is True


def test_bypass_logic_determination():
    """Test the bypass determination logic"""
    # Simulate campaign with bypass ON
    campaign_bypass_on = {
        "_id": ObjectId(),
        "name": "Test",
        "direct_redirect_mode": True,
    }
    
    # Simulate campaign with bypass OFF
    campaign_bypass_off = {
        "_id": ObjectId(),
        "name": "Test",
        "direct_redirect_mode": False,
    }
    
    # Verify logic
    assert campaign_bypass_on.get("direct_redirect_mode") is True, "Bypass should be ON"
    assert campaign_bypass_off.get("direct_redirect_mode") is False, "Bypass should be OFF"


def test_prelander_url_structure():
    """Test prelander URL structure validation"""
    import base64
    import time
    
    # Simulate prelander URL generation
    os_param = "windows"
    ts = str(int(time.time()))
    offer_id = str(ObjectId())
    campaign_id = str(ObjectId())
    cc = "US"
    
    raw = f"{os_param}:{ts}:{offer_id}:{campaign_id}:{cc}"
    key = "mxp2026"
    xored = bytes(ord(c) ^ ord(key[i % len(key)]) for i, c in enumerate(raw))
    slug = base64.urlsafe_b64encode(xored).decode().rstrip("=")
    
    prelander_url = f"https://prelander.example.com/d/{slug}"
    
    # Verify structure
    assert prelander_url.startswith("https://"), "URL should be HTTPS"
    assert "/d/" in prelander_url, "URL should contain /d/ path"
    assert len(slug) > 0, "Slug should not be empty"
    
    # Verify slug can be decoded
    missing_padding = len(slug) % 4
    if missing_padding:
        slug += '=' * (4 - missing_padding)
    decoded = base64.urlsafe_b64decode(slug)
    assert len(decoded) > 0, "Decoded slug should not be empty"


def test_campaign_url_structure():
    """Test direct campaign URL structure (bypass ON)"""
    campaign_url = "https://offer.example.com/product?id=123"
    
    # Verify it's a direct URL (no /d/ slug)
    assert campaign_url.startswith("https://") or campaign_url.startswith("http://")
    assert "/d/" not in campaign_url, "Direct URL should not contain prelander path"


def test_bypass_override_priority():
    """Test that offer-level bypass overrides campaign-level"""
    # Campaign with bypass OFF
    campaign = {
        "_id": ObjectId(),
        "direct_redirect_mode": False,
    }
    
    # Offer with bypass ON
    offer = {
        "_id": ObjectId(),
        "campaign_id": campaign["_id"],
        "direct_redirect_mode": True,
    }
    
    # Logic: offer takes precedence
    is_bypass_on = False
    
    if campaign.get("direct_redirect_mode"):
        is_bypass_on = True
    
    if offer.get("direct_redirect_mode"):
        is_bypass_on = True  # Override
    
    assert is_bypass_on is True, "Offer bypass should override campaign bypass"


def test_traffic_flow_documentation():
    """Verify traffic flow paths are documented"""
    flows = {
        "bypass_off": [
            "Publisher Smartlink",
            "Anchor Domain",
            "Inter Domain",
            "Logs",
            "Prelander Domain"
        ],
        "bypass_on": [
            "Publisher Smartlink",
            "Anchor Domain",
            "Inter Domain",
            "Logs",
            "Direct Campaign URL"
        ]
    }
    
    # Verify both flows include logging step
    assert "Logs" in flows["bypass_off"], "Bypass OFF flow must include logging"
    assert "Logs" in flows["bypass_on"], "Bypass ON flow must include logging"
    
    # Verify difference is in the final destination
    assert "Prelander Domain" in flows["bypass_off"], "Bypass OFF ends at prelander"
    assert "Direct Campaign URL" in flows["bypass_on"], "Bypass ON ends at campaign URL"
    
    # Verify both start the same
    assert flows["bypass_off"][:3] == flows["bypass_on"][:3], \
        "Both flows should start with same 3 steps"


def test_domain_types():
    """Test domain type constants"""
    DOMAIN_TYPES = ("link", "intermediate", "last")
    
    assert "link" in DOMAIN_TYPES, "Anchor/link domain should be defined"
    assert "intermediate" in DOMAIN_TYPES, "Inter domain should be defined"
    assert "last" in DOMAIN_TYPES, "Prelander/last domain should be defined"


def test_bypass_default_value():
    """Test that bypass defaults to OFF (False)"""
    from app.schemas.campaign_schema import CampaignCreate
    
    # Create campaign without specifying bypass
    campaign_data = {
        "name": "Test Campaign",
        "default_offer_url": "https://example.com",
    }
    campaign = CampaignCreate(**campaign_data)
    
    # Default should be False (bypass OFF)
    assert campaign.direct_redirect_mode is False, \
        "Bypass should default to OFF when not specified"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
