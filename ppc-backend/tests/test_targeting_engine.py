"""
Tests for Centralized Targeting Engine
=======================================
Tests priority resolution, conflicting rules, and fallback behavior.
"""

import pytest
from bson import ObjectId
from app.services.targeting_engine import (
    TargetingEngine,
    ClickContext,
    TargetingRule,
    resolve_campaign_for_click,
)


class TestClickContext:
    """Test ClickContext normalization."""
    
    def test_os_normalization_mac(self):
        """Test Mac OS variants normalize to 'mac'."""
        contexts = [
            ClickContext(os="Mac OS"),
            ClickContext(os="Mac OS X"),
            ClickContext(os="macOS"),
            ClickContext(os="iOS"),
        ]
        for ctx in contexts:
            assert ctx.normalized_os == "mac"
    
    def test_os_normalization_windows(self):
        """Test Windows and Linux normalize to 'windows'."""
        ctx1 = ClickContext(os="Windows")
        ctx2 = ClickContext(os="Linux")
        assert ctx1.normalized_os == "windows"
        assert ctx2.normalized_os == "windows"
    
    def test_os_normalization_android(self):
        """Test Android stays as 'android'."""
        ctx = ClickContext(os="Android")
        assert ctx.normalized_os == "android"


@pytest.mark.asyncio
class TestTargetingEngine:
    """Test centralized targeting engine."""
    
    async def test_fallback_only(self, db):
        """Test fallback when no rules match."""
        engine = TargetingEngine(db)
        context = ClickContext(
            publisher_id="pub123",
            country_code="US",
        )
        
        url, ref_supp, metadata = await engine.resolve_destination(context)
        
        assert url == "https://example.com"  # Fallback URL
        assert metadata["rule_type"] == "fallback"
        assert metadata["priority"] == 0
    
    async def test_campaign_default(self, db):
        """Test campaign default URL (priority 500)."""
        # Create campaign
        campaign_id = ObjectId()
        await db.campaigns.insert_one({
            "_id": campaign_id,
            "name": "Test Campaign",
            "default_offer_url": "https://campaign-default.com",
            "status": "active",
        })
        
        engine = TargetingEngine(db)
        context = ClickContext(campaign_id=str(campaign_id))
        
        url, ref_supp, metadata = await engine.resolve_destination(context)
        
        assert url == "https://campaign-default.com"
        assert metadata["rule_type"] == "campaign_default"
        assert metadata["priority"] == 500
        
        # Cleanup
        await db.campaigns.delete_one({"_id": campaign_id})
    
    async def test_geo_rule_priority(self, db):
        """Test GEO rule overrides campaign default (priority 800 > 500)."""
        campaign_id = ObjectId()
        geo_rule_id = ObjectId()
        
        await db.campaigns.insert_one({
            "_id": campaign_id,
            "name": "Test Campaign",
            "default_offer_url": "https://campaign-default.com",
            "status": "active",
        })
        
        await db.geo_rules.insert_one({
            "_id": geo_rule_id,
            "campaign_id": str(campaign_id),
            "country_code": "US",
            "offer_url": "https://us-specific.com",
            "priority": 100,
        })
        
        engine = TargetingEngine(db)
        context = ClickContext(
            campaign_id=str(campaign_id),
            country_code="US",
        )
        
        url, ref_supp, metadata = await engine.resolve_destination(context)
        
        assert url == "https://us-specific.com"  # GEO rule wins
        assert metadata["rule_type"] == "geo"
        assert metadata["priority"] == 800
        
        # Cleanup
        await db.campaigns.delete_one({"_id": campaign_id})
        await db.geo_rules.delete_one({"_id": geo_rule_id})
    
    async def test_device_rule_priority(self, db):
        """Test device rule (priority 700)."""
        campaign_id = ObjectId()
        device_rule_id = ObjectId()
        
        await db.campaigns.insert_one({
            "_id": campaign_id,
            "name": "Test Campaign",
            "default_offer_url": "https://campaign-default.com",
            "status": "active",
        })
        
        await db.device_rules.insert_one({
            "_id": device_rule_id,
            "campaign_id": str(campaign_id),
            "device_type": "mobile",
            "offer_url": "https://mobile-offer.com",
            "priority": 100,
        })
        
        engine = TargetingEngine(db)
        context = ClickContext(
            campaign_id=str(campaign_id),
            device_type="mobile",
        )
        
        url, ref_supp, metadata = await engine.resolve_destination(context)
        
        assert url == "https://mobile-offer.com"
        assert metadata["rule_type"] == "device"
        assert metadata["priority"] == 700
        
        # Cleanup
        await db.campaigns.delete_one({"_id": campaign_id})
        await db.device_rules.delete_one({"_id": device_rule_id})
    
    async def test_device_os_rule_higher_priority(self, db):
        """Test device+OS rule (priority 800) beats device-only (priority 700)."""
        campaign_id = ObjectId()
        
        await db.campaigns.insert_one({
            "_id": campaign_id,
            "name": "Test Campaign",
            "default_offer_url": "https://campaign-default.com",
            "status": "active",
        })
        
        # Device-only rule
        await db.device_rules.insert_one({
            "campaign_id": str(campaign_id),
            "device_type": "mobile",
            "offer_url": "https://mobile-generic.com",
            "priority": 100,
        })
        
        # Device+OS rule
        device_os_rule_id = ObjectId()
        await db.device_rules.insert_one({
            "_id": device_os_rule_id,
            "campaign_id": str(campaign_id),
            "device_type": "mobile",
            "os": "android",
            "offer_url": "https://mobile-android.com",
            "priority": 100,
        })
        
        engine = TargetingEngine(db)
        context = ClickContext(
            campaign_id=str(campaign_id),
            device_type="mobile",
            os="Android",
        )
        
        url, ref_supp, metadata = await engine.resolve_destination(context)
        
        assert url == "https://mobile-android.com"  # More specific wins
        assert metadata["priority"] == 800
        
        # Cleanup
        await db.campaigns.delete_one({"_id": campaign_id})
        await db.device_rules.delete_many({"campaign_id": str(campaign_id)})
    
    async def test_offer_with_single_criterion(self, db):
        """Test offer with single targeting criterion (priority 1500)."""
        campaign_id = ObjectId()
        offer_id = ObjectId()
        
        await db.campaigns.insert_one({
            "_id": campaign_id,
            "name": "Test Campaign",
            "default_offer_url": "https://campaign-default.com",
            "status": "active",
        })
        
        await db.offers.insert_one({
            "_id": offer_id,
            "name": "US Only Offer",
            "offer_url": "https://us-offer.com",
            "campaign_id": str(campaign_id),
            "country_codes": ["US"],
            "status": "active",
        })
        
        engine = TargetingEngine(db)
        context = ClickContext(
            campaign_id=str(campaign_id),
            country_code="US",
        )
        
        url, ref_supp, metadata = await engine.resolve_destination(context)
        
        assert url == "https://us-offer.com"
        assert metadata["rule_type"] == "offer"
        assert metadata["priority"] == 1500  # 1000 base + 500 for geo
        
        # Cleanup
        await db.campaigns.delete_one({"_id": campaign_id})
        await db.offers.delete_one({"_id": offer_id})
    
    async def test_offer_multi_criteria_highest_priority(self, db):
        """Test offer with multiple criteria has highest priority."""
        campaign_id = ObjectId()
        publisher_id = str(ObjectId())
        website_id = str(ObjectId())
        
        await db.campaigns.insert_one({
            "_id": campaign_id,
            "name": "Test Campaign",
            "default_offer_url": "https://campaign-default.com",
            "status": "active",
        })
        
        # GEO rule (priority 800)
        await db.geo_rules.insert_one({
            "campaign_id": str(campaign_id),
            "country_code": "US",
            "offer_url": "https://us-geo.com",
            "priority": 100,
        })
        
        # Multi-criteria offer (priority 3000: 1000 + 500*4)
        await db.offers.insert_one({
            "name": "Super Specific Offer",
            "offer_url": "https://super-specific.com",
            "campaign_id": str(campaign_id),
            "country_codes": ["US"],
            "os_types": ["windows"],
            "publisher_ids": [publisher_id],
            "website_ids": [website_id],
            "status": "active",
        })
        
        engine = TargetingEngine(db)
        context = ClickContext(
            campaign_id=str(campaign_id),
            country_code="US",
            os="Windows",
            publisher_id=publisher_id,
            website_id=website_id,
        )
        
        url, ref_supp, metadata = await engine.resolve_destination(context)
        
        assert url == "https://super-specific.com"  # Most specific wins
        assert metadata["rule_type"] == "offer"
        assert metadata["priority"] == 3000  # 1000 + 500*4
        assert set(metadata["matched_criteria"]) == {"geo", "os", "publisher", "website"}
        
        # Cleanup
        await db.campaigns.delete_one({"_id": campaign_id})
        await db.geo_rules.delete_many({"campaign_id": str(campaign_id)})
        await db.offers.delete_many({"campaign_id": str(campaign_id)})
    
    async def test_conflicting_offers_most_specific_wins(self, db):
        """Test that when multiple offers match, most specific wins."""
        campaign_id = ObjectId()
        publisher_id = str(ObjectId())
        
        await db.campaigns.insert_one({
            "_id": campaign_id,
            "name": "Test Campaign",
            "default_offer_url": "https://campaign-default.com",
            "status": "active",
        })
        
        # Offer 1: Just geo (priority 1500)
        await db.offers.insert_one({
            "name": "Geo Only",
            "offer_url": "https://geo-only.com",
            "campaign_id": str(campaign_id),
            "country_codes": ["US"],
            "status": "active",
        })
        
        # Offer 2: Geo + Publisher (priority 2000)
        await db.offers.insert_one({
            "name": "Geo + Publisher",
            "offer_url": "https://geo-pub.com",
            "campaign_id": str(campaign_id),
            "country_codes": ["US"],
            "publisher_ids": [publisher_id],
            "status": "active",
        })
        
        engine = TargetingEngine(db)
        context = ClickContext(
            campaign_id=str(campaign_id),
            country_code="US",
            publisher_id=publisher_id,
        )
        
        url, ref_supp, metadata = await engine.resolve_destination(context)
        
        assert url == "https://geo-pub.com"  # More specific offer wins
        assert metadata["priority"] == 2000
        
        # Cleanup
        await db.campaigns.delete_one({"_id": campaign_id})
        await db.offers.delete_many({"campaign_id": str(campaign_id)})
    
    async def test_offer_mismatch_falls_back(self, db):
        """Test that offer with non-matching criteria is skipped."""
        campaign_id = ObjectId()
        
        await db.campaigns.insert_one({
            "_id": campaign_id,
            "name": "Test Campaign",
            "default_offer_url": "https://campaign-default.com",
            "status": "active",
        })
        
        # Offer for UK only
        await db.offers.insert_one({
            "name": "UK Only",
            "offer_url": "https://uk-only.com",
            "campaign_id": str(campaign_id),
            "country_codes": ["UK"],
            "status": "active",
        })
        
        engine = TargetingEngine(db)
        context = ClickContext(
            campaign_id=str(campaign_id),
            country_code="US",  # US click, but offer is UK-only
        )
        
        url, ref_supp, metadata = await engine.resolve_destination(context)
        
        # Should fall back to campaign default, not use the UK offer
        assert url == "https://campaign-default.com"
        assert metadata["rule_type"] == "campaign_default"
        
        # Cleanup
        await db.campaigns.delete_one({"_id": campaign_id})
        await db.offers.delete_many({"campaign_id": str(campaign_id)})
    
    async def test_referrer_suppression_from_campaign(self, db):
        """Test referrer suppression flag from campaign."""
        campaign_id = ObjectId()
        
        await db.campaigns.insert_one({
            "_id": campaign_id,
            "name": "Test Campaign",
            "default_offer_url": "https://campaign-default.com",
            "referrer_suppression": True,
            "status": "active",
        })
        
        engine = TargetingEngine(db)
        context = ClickContext(campaign_id=str(campaign_id))
        
        url, ref_supp, metadata = await engine.resolve_destination(context)
        
        assert ref_supp is True
        
        # Cleanup
        await db.campaigns.delete_one({"_id": campaign_id})


@pytest.mark.asyncio
class TestCampaignResolution:
    """Test campaign resolution for clicks."""
    
    async def test_website_assigned_campaign(self, db):
        """Test website-assigned campaign has priority."""
        campaign_id = ObjectId()
        website_id = ObjectId()
        
        await db.campaigns.insert_one({
            "_id": campaign_id,
            "name": "Website Campaign",
            "status": "active",
        })
        
        await db.websites.insert_one({
            "_id": website_id,
            "domain": "test.com",
            "assigned_campaign_id": campaign_id,
        })
        
        click_data = {"website_id": str(website_id)}
        resolved_id = await resolve_campaign_for_click(click_data, db)
        
        assert resolved_id == str(campaign_id)
        
        # Cleanup
        await db.campaigns.delete_one({"_id": campaign_id})
        await db.websites.delete_one({"_id": website_id})
    
    async def test_os_specific_campaign(self, db):
        """Test OS-specific campaign selection."""
        campaign_id = ObjectId()
        
        await db.campaigns.insert_one({
            "_id": campaign_id,
            "name": "Mac Campaign",
            "device_os": "mac",
            "status": "active",
        })
        
        click_data = {"os": "macOS"}
        resolved_id = await resolve_campaign_for_click(click_data, db)
        
        assert resolved_id == str(campaign_id)
        
        # Cleanup
        await db.campaigns.delete_one({"_id": campaign_id})
    
    async def test_global_campaign_fallback(self, db):
        """Test global campaign as fallback."""
        campaign_id = ObjectId()
        
        await db.campaigns.insert_one({
            "_id": campaign_id,
            "name": "Global Campaign",
            "device_os": "global",
            "status": "active",
        })
        
        click_data = {"os": "Unknown OS"}
        resolved_id = await resolve_campaign_for_click(click_data, db)
        
        assert resolved_id == str(campaign_id)
        
        # Cleanup
        await db.campaigns.delete_one({"_id": campaign_id})


@pytest.mark.asyncio
class TestPriorityOrder:
    """Test deterministic priority ordering."""
    
    async def test_priority_order_complete(self, db):
        """Test complete priority hierarchy with all rule types present."""
        campaign_id = ObjectId()
        publisher_id = str(ObjectId())
        
        await db.campaigns.insert_one({
            "_id": campaign_id,
            "name": "Test Campaign",
            "default_offer_url": "https://campaign.com",
            "status": "active",
        })
        
        # Add all rule types
        await db.geo_rules.insert_one({
            "campaign_id": str(campaign_id),
            "country_code": "US",
            "offer_url": "https://geo.com",
            "priority": 100,
        })
        
        await db.device_rules.insert_one({
            "campaign_id": str(campaign_id),
            "device_type": "mobile",
            "offer_url": "https://device.com",
            "priority": 100,
        })
        
        # Multi-criteria offer (should win)
        await db.offers.insert_one({
            "name": "Best Offer",
            "offer_url": "https://best-offer.com",
            "campaign_id": str(campaign_id),
            "country_codes": ["US"],
            "publisher_ids": [publisher_id],
            "status": "active",
        })
        
        engine = TargetingEngine(db)
        context = ClickContext(
            campaign_id=str(campaign_id),
            country_code="US",
            device_type="mobile",
            publisher_id=publisher_id,
        )
        
        url, ref_supp, metadata = await engine.resolve_destination(context)
        
        # Offer with 2 criteria should win (priority 2000)
        assert url == "https://best-offer.com"
        assert metadata["priority"] == 2000
        
        # Cleanup
        await db.campaigns.delete_one({"_id": campaign_id})
        await db.geo_rules.delete_many({"campaign_id": str(campaign_id)})
        await db.device_rules.delete_many({"campaign_id": str(campaign_id)})
        await db.offers.delete_many({"campaign_id": str(campaign_id)})
