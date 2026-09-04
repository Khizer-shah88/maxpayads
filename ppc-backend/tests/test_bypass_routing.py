"""
Tests for Bypass Traffic Routing Feature

Tests the two traffic flows:
1. Bypass OFF: Publisher → Anchor → Inter → Prelander Domain
2. Bypass ON:  Publisher → Anchor → Inter → Direct Campaign URL
"""
import pytest
from datetime import datetime
from bson import ObjectId
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_bypass_off_returns_prelander_url():
    """
    Test: When direct_redirect_mode = False (Bypass OFF)
    Expected: route_click returns prelander URL (last domain)
    """
    from app.services.traffic_router import route_click
    
    # Mock database
    db = MagicMock()
    redis = MagicMock()
    
    # Mock campaign with bypass OFF
    campaign_id = str(ObjectId())
    campaign = {
        "_id": ObjectId(campaign_id),
        "name": "Test Campaign",
        "default_offer_url": "https://offer.example.com",
        "direct_redirect_mode": False,  # BYPASS OFF
    }
    
    # Mock database queries
    async def find_one_side_effect(query, *args, **kwargs):
        if "_id" in query and query["_id"] == ObjectId(campaign_id):
            return campaign
        if "key" in query and query["key"] == "last_domain":
            return {"key": "last_domain", "value": "https://prelander.example.com"}
        return None
    
    db.campaigns.find_one = AsyncMock(side_effect=find_one_side_effect)
    db.system_settings.find_one = AsyncMock(side_effect=find_one_side_effect)
    db.redirection_domains.find_one = AsyncMock(return_value={
        "domain": "prelander.example.com",
        "domain_type": "last",
        "status": "active",
    })
    db.landing_pages.find = MagicMock()
    db.landing_pages.find.return_value.to_list = AsyncMock(return_value=[])
    
    # Mock targeting engine and domain resolution
    with patch("app.services.targeting_engine.resolve_campaign_for_click") as mock_resolve:
        mock_resolve.return_value = campaign_id
        
        with patch("app.services.targeting_engine.TargetingEngine") as MockEngine:
            mock_engine = MockEngine.return_value
            mock_engine.resolve_destination = AsyncMock(return_value=(
                "https://offer.example.com",
                False,
                {"rule_type": "default", "priority": 0}
            ))
            
            with patch("app.services.domain_service.resolve_domain_url") as mock_domain:
                # Return last domain URL
                async def domain_resolver(db, domain_type, publisher_id):
                    if domain_type == "last":
                        return "https://prelander.example.com"
                    return None
                mock_domain.side_effect = domain_resolver
                
                # Test data
                click_data = {
                    "publisher_id": str(ObjectId()),
                    "website_id": str(ObjectId()),
                    "country_code": "US",
                    "device_type": "desktop",
                    "os": "windows",
                }
                
                # Execute
                destination, referrer_suppression = await route_click(click_data, db, redis)
                
                # Verify: Should return prelander URL, not direct campaign URL
                assert destination != "https://offer.example.com", "Should not return direct campaign URL when bypass is OFF"
                assert "/d/" in destination, "Should return prelander URL with /d/ slug path"
                assert destination.startswith("https://"), "Should return valid HTTPS URL"


@pytest.mark.asyncio
async def test_bypass_on_returns_campaign_url():
    """
    Test: When direct_redirect_mode = True (Bypass ON)
    Expected: route_click returns direct campaign URL (skips prelander)
    """
    from app.services.traffic_router import route_click
    
    # Mock database
    db = MagicMock()
    redis = MagicMock()
    
    # Mock campaign with bypass ON
    campaign_id = str(ObjectId())
    campaign = {
        "_id": ObjectId(campaign_id),
        "name": "Test Campaign",
        "default_offer_url": "https://offer.example.com",
        "direct_redirect_mode": True,  # BYPASS ON
    }
    
    # Mock database queries
    async def find_one_side_effect(query, *args, **kwargs):
        if "_id" in query and query["_id"] == ObjectId(campaign_id):
            return campaign
        return None
    
    db.campaigns.find_one = AsyncMock(side_effect=find_one_side_effect)
    
    # Mock targeting engine
    with patch("app.services.targeting_engine.resolve_campaign_for_click") as mock_resolve:
        mock_resolve.return_value = campaign_id
        
        with patch("app.services.targeting_engine.TargetingEngine") as MockEngine:
            mock_engine = MockEngine.return_value
            mock_engine.resolve_destination = AsyncMock(return_value=(
                "https://offer.example.com",
                False,
                {"rule_type": "default", "priority": 0}
            ))
            
            # Test data
            click_data = {
                "publisher_id": str(ObjectId()),
                "website_id": str(ObjectId()),
                "country_code": "US",
                "device_type": "desktop",
                "os": "windows",
            }
            
            # Execute
            destination, referrer_suppression = await route_click(click_data, db, redis)
            
            # Verify: Should return direct campaign URL (bypass prelander)
            assert destination == "https://offer.example.com", "Should return direct campaign URL when bypass is ON"
            assert "/d/" not in destination, "Should not include prelander slug path when bypass is ON"


@pytest.mark.asyncio
async def test_offer_level_bypass_overrides_campaign():
    """
    Test: Offer-level bypass setting takes precedence over campaign-level
    Expected: If offer has bypass ON, return direct URL even if campaign bypass is OFF
    """
    from app.services.traffic_router import route_click
    
    # Mock database
    db = MagicMock()
    redis = MagicMock()
    
    # Mock campaign with bypass OFF
    campaign_id = str(ObjectId())
    campaign = {
        "_id": ObjectId(campaign_id),
        "name": "Test Campaign",
        "default_offer_url": "https://offer.example.com",
        "direct_redirect_mode": False,  # Campaign bypass OFF
    }
    
    # Mock offer with bypass ON
    offer_id = str(ObjectId())
    offer = {
        "_id": ObjectId(offer_id),
        "campaign_id": campaign_id,
        "offer_url": "https://special-offer.example.com",
        "direct_redirect_mode": True,  # Offer bypass ON (overrides campaign)
    }
    
    # Mock database queries
    async def find_one_side_effect(query, *args, **kwargs):
        if "_id" in query:
            if query["_id"] == ObjectId(campaign_id):
                return campaign
            elif query["_id"] == ObjectId(offer_id):
                return offer
        return None
    
    db.campaigns.find_one = AsyncMock(side_effect=find_one_side_effect)
    db.offers.find_one = AsyncMock(side_effect=find_one_side_effect)
    
    # Mock targeting engine to return offer-based destination
    with patch("app.services.targeting_engine.resolve_campaign_for_click") as mock_resolve:
        mock_resolve.return_value = campaign_id
        
        with patch("app.services.targeting_engine.TargetingEngine") as MockEngine:
            mock_engine = MockEngine.return_value
            mock_engine.resolve_destination = AsyncMock(return_value=(
                "https://special-offer.example.com",
                False,
                {"rule_type": "offer", "source_id": offer_id, "priority": 10}
            ))
            
            # Test data
            click_data = {
                "publisher_id": str(ObjectId()),
                "website_id": str(ObjectId()),
                "country_code": "US",
                "device_type": "desktop",
                "os": "windows",
            }
            
            # Execute
            destination, referrer_suppression = await route_click(click_data, db, redis)
            
            # Verify: Offer bypass ON should override campaign bypass OFF
            assert destination == "https://special-offer.example.com", \
                "Offer-level bypass ON should override campaign-level bypass OFF"
            assert "/d/" not in destination, "Should not include prelander path when offer bypass is ON"


@pytest.mark.asyncio
async def test_bypass_off_with_no_domains_falls_back_to_campaign_url():
    """
    Test: When bypass OFF but no prelander domains configured
    Expected: Fall back to campaign URL (graceful degradation)
    """
    from app.services.traffic_router import route_click
    
    # Mock database
    db = MagicMock()
    redis = MagicMock()
    
    # Mock campaign with bypass OFF
    campaign_id = str(ObjectId())
    campaign = {
        "_id": ObjectId(campaign_id),
        "name": "Test Campaign",
        "default_offer_url": "https://offer.example.com",
        "direct_redirect_mode": False,  # BYPASS OFF
    }
    
    # Mock database queries - NO domains configured
    async def find_one_side_effect(query, *args, **kwargs):
        if "_id" in query and query["_id"] == ObjectId(campaign_id):
            return campaign
        return None  # No domains found
    
    db.campaigns.find_one = AsyncMock(side_effect=find_one_side_effect)
    db.system_settings.find_one = AsyncMock(return_value=None)
    db.redirection_domains.find_one = AsyncMock(return_value=None)
    db.landing_pages.find = MagicMock()
    db.landing_pages.find.return_value.to_list = AsyncMock(return_value=[])
    
    # Mock targeting engine
    with patch("app.services.targeting_engine.resolve_campaign_for_click") as mock_resolve:
        mock_resolve.return_value = campaign_id
        
        with patch("app.services.targeting_engine.TargetingEngine") as MockEngine:
            mock_engine = MockEngine.return_value
            mock_engine.resolve_destination = AsyncMock(return_value=(
                "https://offer.example.com",
                False,
                {"rule_type": "default", "priority": 0}
            ))
            
            # Test data
            click_data = {
                "publisher_id": str(ObjectId()),
                "website_id": str(ObjectId()),
                "country_code": "US",
                "device_type": "desktop",
                "os": "windows",
            }
            
            # Execute
            destination, referrer_suppression = await route_click(click_data, db, redis)
            
            # Verify: Should gracefully fall back to campaign URL
            assert destination == "https://offer.example.com", \
                "Should fall back to campaign URL when no prelander domains configured"


@pytest.mark.asyncio
async def test_bypass_preserves_referrer_suppression():
    """
    Test: Referrer suppression setting is preserved regardless of bypass status
    Expected: referrer_suppression flag is returned correctly in both modes
    """
    from app.services.traffic_router import route_click
    
    # Test both bypass ON and OFF
    for bypass_mode in [True, False]:
        db = MagicMock()
        redis = MagicMock()
        
        campaign_id = str(ObjectId())
        campaign = {
            "_id": ObjectId(campaign_id),
            "name": "Test Campaign",
            "default_offer_url": "https://offer.example.com",
            "direct_redirect_mode": bypass_mode,
        }
        
        db.campaigns.find_one = AsyncMock(return_value=campaign)
        db.system_settings.find_one = AsyncMock(return_value=None)
        db.redirection_domains.find_one = AsyncMock(return_value=None)
        db.landing_pages.find = MagicMock()
        db.landing_pages.find.return_value.to_list = AsyncMock(return_value=[])
        
        with patch("app.services.targeting_engine.resolve_campaign_for_click") as mock_resolve:
            mock_resolve.return_value = campaign_id
            
            with patch("app.services.targeting_engine.TargetingEngine") as MockEngine:
                mock_engine = MockEngine.return_value
                # Return with referrer_suppression = True
                mock_engine.resolve_destination = AsyncMock(return_value=(
                    "https://offer.example.com",
                    True,  # referrer_suppression enabled
                    {"rule_type": "default", "priority": 0}
                ))
                
                click_data = {
                    "publisher_id": str(ObjectId()),
                    "website_id": str(ObjectId()),
                    "country_code": "US",
                    "device_type": "desktop",
                    "os": "windows",
                }
                
                destination, referrer_suppression = await route_click(click_data, db, redis)
                
                # Verify: referrer_suppression should be True regardless of bypass mode
                assert referrer_suppression is True, \
                    f"Referrer suppression should be preserved (bypass={bypass_mode})"


@pytest.mark.asyncio 
async def test_prelander_url_slug_encoding():
    """
    Test: Prelander slug is properly encoded with campaign data
    Expected: Slug contains encrypted campaign context
    """
    from app.services.traffic_router import route_click
    import base64
    
    db = MagicMock()
    redis = MagicMock()
    
    campaign_id = str(ObjectId())
    campaign = {
        "_id": ObjectId(campaign_id),
        "name": "Test Campaign",
        "default_offer_url": "https://offer.example.com",
        "direct_redirect_mode": False,
    }
    
    db.campaigns.find_one = AsyncMock(return_value=campaign)
    db.redirection_domains.find_one = AsyncMock(return_value={
        "domain": "prelander.example.com",
        "domain_type": "last",
        "status": "active",
    })
    db.system_settings.find_one = AsyncMock(return_value={
        "key": "last_domain",
        "value": "https://prelander.example.com"
    })
    db.landing_pages.find = MagicMock()
    db.landing_pages.find.return_value.to_list = AsyncMock(return_value=[])
    
    with patch("app.services.targeting_engine.resolve_campaign_for_click") as mock_resolve:
        mock_resolve.return_value = campaign_id
        
        with patch("app.services.targeting_engine.TargetingEngine") as MockEngine:
            mock_engine = MockEngine.return_value
            mock_engine.resolve_destination = AsyncMock(return_value=(
                "https://offer.example.com",
                False,
                {"rule_type": "default", "priority": 0}
            ))
            
            click_data = {
                "publisher_id": str(ObjectId()),
                "website_id": str(ObjectId()),
                "country_code": "US",
                "device_type": "desktop",
                "os": "windows",
            }
            
            destination, _ = await route_click(click_data, db, redis)
            
            # Verify: URL structure
            assert "prelander.example.com/d/" in destination, \
                "Prelander URL should contain domain and /d/ path"
            
            # Extract slug
            slug = destination.split("/d/")[-1]
            
            # Verify: Slug is base64url encoded
            try:
                # Add padding if needed
                missing_padding = len(slug) % 4
                if missing_padding:
                    slug += '=' * (4 - missing_padding)
                decoded = base64.urlsafe_b64decode(slug)
                assert len(decoded) > 0, "Slug should decode to non-empty data"
            except Exception as e:
                pytest.fail(f"Slug should be valid base64url: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
