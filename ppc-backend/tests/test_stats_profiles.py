"""
Tests for Direct Link Stats Profiles
=====================================

Tests comprehensive stats profile functionality:
- Profile CRUD
- Opaque slug generation
- Statistics aggregation
- Manual conversions
- Access control
- No internal data leakage
"""

import pytest
from datetime import datetime, timedelta
from bson import ObjectId

from app.services import stats_profile_service as sps


# ═══════════════════════════════════════════════════════════════════════════════
# Slug Generation Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestSlugGeneration:
    """Test opaque slug generation."""
    
    def test_generate_slug(self):
        """Test slug generation returns 8-char string."""
        slug = sps.generate_profile_slug()
        
        assert isinstance(slug, str)
        assert len(slug) == 8
        assert slug.isalnum()
    
    def test_slug_randomness(self):
        """Test slugs are random (different each time)."""
        slugs = [sps.generate_profile_slug() for _ in range(10)]
        
        # All should be unique
        assert len(set(slugs)) == 10
    
    def test_slug_length_parameter(self):
        """Test custom slug length."""
        slug = sps.generate_profile_slug(length=12)
        assert len(slug) == 12
    
    @pytest.mark.asyncio
    async def test_ensure_unique_slug(self, db):
        """Test unique slug generation with collision detection."""
        slug = await sps.ensure_unique_slug(db)
        
        assert isinstance(slug, str)
        assert len(slug) == 8
        
        # Verify it's not in database
        existing = await db.stats_profiles.find_one({"slug": slug})
        assert existing is None


# ═══════════════════════════════════════════════════════════════════════════════
# Profile CRUD Tests
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestProfileCRUD:
    """Test profile creation, reading, updating, and deletion."""
    
    async def test_create_profile(self, db):
        """Test creating a stats profile."""
        slug = await sps.ensure_unique_slug(db)
        
        profile = {
            "slug": slug,
            "name": "Test Profile",
            "publisher_id": "pub123",
            "source_name": "Test Source",
            "stats_domain": "stats.test.com",
            "status": "active",
            "notes": "Test notes",
            "metadata": {"key": "value"},
            "total_impressions": 0,
            "total_clicks": 0,
            "unique_clicks": 0,
            "valid_clicks": 0,
            "invalid_clicks": 0,
            "total_conversions": 0,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        
        result = await db.stats_profiles.insert_one(profile)
        assert result.inserted_id is not None
        
        # Verify retrieval
        retrieved = await db.stats_profiles.find_one({"_id": result.inserted_id})
        assert retrieved is not None
        assert retrieved["slug"] == slug
        assert retrieved["name"] == "Test Profile"
        
        # Cleanup
        await db.stats_profiles.delete_one({"_id": result.inserted_id})
    
    async def test_serialize_profile(self, db):
        """Test profile serialization."""
        profile = {
            "_id": ObjectId(),
            "slug": "abc12345",
            "name": "Serialize Test",
            "publisher_id": "pub123",
            "source_name": "Source",
            "stats_domain": "stats.test.com",
            "status": "active",
            "notes": "Notes",
            "metadata": {"test": True},
            "total_impressions": 100,
            "total_clicks": 50,
            "unique_clicks": 40,
            "valid_clicks": 45,
            "invalid_clicks": 5,
            "total_conversions": 10,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        
        serialized = sps.serialize_profile(profile)
        
        assert serialized["id"] == str(profile["_id"])
        assert serialized["slug"] == "abc12345"
        assert serialized["name"] == "Serialize Test"
        assert serialized["total_impressions"] == 100
        assert serialized["total_clicks"] == 50
        assert "stats_url" in serialized
        assert serialized["stats_url"].startswith("https://")
    
    async def test_build_stats_url(self, db):
        """Test stats URL building."""
        url = sps.build_stats_url("abc12345", "stats.example.com")
        
        assert url == "https://stats.example.com/s/abc12345"
    
    async def test_build_stats_url_default_domain(self, db):
        """Test stats URL with default domain."""
        url = sps.build_stats_url("abc12345")
        
        assert url.startswith("https://")
        assert "/s/abc12345" in url


# ═══════════════════════════════════════════════════════════════════════════════
# Statistics Tracking Tests
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestStatisticsTracking:
    """Test statistics tracking functionality."""
    
    async def test_track_impression(self, db):
        """Test impression tracking."""
        # Create profile
        slug = await sps.ensure_unique_slug(db)
        profile = {
            "slug": slug,
            "name": "Impression Test",
            "publisher_id": "pub123",
            "status": "active",
            "total_impressions": 0,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        result = await db.stats_profiles.insert_one(profile)
        profile_id = result.inserted_id
        
        # Track impression
        request_data = {
            "ip_address": "192.168.1.1",
            "user_agent": "Test Browser",
            "referrer": "https://example.com",
        }
        
        success = await sps.track_impression(db, slug, request_data)
        assert success is True
        
        # Verify impression recorded
        impressions = await db.stats_profile_impressions.count_documents({"profile_slug": slug})
        assert impressions == 1
        
        # Verify counter updated
        updated_profile = await db.stats_profiles.find_one({"_id": profile_id})
        assert updated_profile["total_impressions"] == 1
        
        # Cleanup
        await db.stats_profiles.delete_one({"_id": profile_id})
        await db.stats_profile_impressions.delete_many({"profile_slug": slug})
    
    async def test_track_click(self, db):
        """Test click tracking."""
        # Create profile
        slug = await sps.ensure_unique_slug(db)
        profile = {
            "slug": slug,
            "name": "Click Test",
            "publisher_id": "pub123",
            "status": "active",
            "total_clicks": 0,
            "valid_clicks": 0,
            "invalid_clicks": 0,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        result = await db.stats_profiles.insert_one(profile)
        profile_id = result.inserted_id
        
        # Track valid click
        click_data = {
            "ip_address": "192.168.1.1",
            "user_agent": "Test Browser",
            "referrer": "https://example.com",
            "os": "Windows",
            "device_type": "desktop",
            "country": "US",
            "is_valid": True,
        }
        
        success = await sps.track_click(db, slug, click_data)
        assert success is True
        
        # Verify click recorded
        clicks = await db.stats_profile_clicks.count_documents({"profile_slug": slug})
        assert clicks == 1
        
        # Verify counters updated
        updated_profile = await db.stats_profiles.find_one({"_id": profile_id})
        assert updated_profile["total_clicks"] == 1
        assert updated_profile["valid_clicks"] == 1
        assert updated_profile["invalid_clicks"] == 0
        
        # Cleanup
        await db.stats_profiles.delete_one({"_id": profile_id})
        await db.stats_profile_clicks.delete_many({"profile_slug": slug})
    
    async def test_track_invalid_click(self, db):
        """Test invalid click tracking."""
        # Create profile
        slug = await sps.ensure_unique_slug(db)
        profile = {
            "slug": slug,
            "name": "Invalid Click Test",
            "publisher_id": "pub123",
            "status": "active",
            "total_clicks": 0,
            "valid_clicks": 0,
            "invalid_clicks": 0,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        result = await db.stats_profiles.insert_one(profile)
        profile_id = result.inserted_id
        
        # Track invalid click
        click_data = {
            "ip_address": "192.168.1.1",
            "user_agent": "Bot",
            "is_valid": False,
        }
        
        success = await sps.track_click(db, slug, click_data)
        assert success is True
        
        # Verify counters
        updated_profile = await db.stats_profiles.find_one({"_id": profile_id})
        assert updated_profile["total_clicks"] == 1
        assert updated_profile["valid_clicks"] == 0
        assert updated_profile["invalid_clicks"] == 1
        
        # Cleanup
        await db.stats_profiles.delete_one({"_id": profile_id})
        await db.stats_profile_clicks.delete_many({"profile_slug": slug})
    
    async def test_track_conversion(self, db):
        """Test conversion tracking."""
        # Create profile
        slug = await sps.ensure_unique_slug(db)
        profile = {
            "slug": slug,
            "name": "Conversion Test",
            "publisher_id": "pub123",
            "status": "active",
            "total_conversions": 0,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        result = await db.stats_profiles.insert_one(profile)
        profile_id = result.inserted_id
        
        # Track conversion
        conversion_data = {
            "ip_address": "192.168.1.1",
            "metadata": {"amount": 100},
        }
        
        success = await sps.track_conversion(db, slug, conversion_data)
        assert success is True
        
        # Verify conversion recorded
        conversions = await db.stats_profile_conversions.count_documents({"profile_slug": slug})
        assert conversions == 1
        
        # Verify counter updated
        updated_profile = await db.stats_profiles.find_one({"_id": profile_id})
        assert updated_profile["total_conversions"] == 1
        
        # Cleanup
        await db.stats_profiles.delete_one({"_id": profile_id})
        await db.stats_profile_conversions.delete_many({"profile_slug": slug})


# ═══════════════════════════════════════════════════════════════════════════════
# Statistics Aggregation Tests
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestStatisticsAggregation:
    """Test statistics aggregation."""
    
    async def test_aggregate_stats_empty(self, db):
        """Test stats aggregation with no data."""
        slug = await sps.ensure_unique_slug(db)
        profile = {
            "slug": slug,
            "name": "Empty Stats",
            "publisher_id": "pub123",
            "status": "active",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        result = await db.stats_profiles.insert_one(profile)
        
        stats = await sps.aggregate_stats(db, slug)
        
        assert stats is not None
        assert stats["total_clicks"] == 0
        assert stats["unique_clicks"] == 0
        assert stats["valid_clicks"] == 0
        assert stats["invalid_clicks"] == 0
        assert stats["impressions"] == 0
        assert stats["conversions"] == 0
        
        # Cleanup
        await db.stats_profiles.delete_one({"_id": result.inserted_id})
    
    async def test_aggregate_stats_with_data(self, db):
        """Test stats aggregation with sample data."""
        slug = await sps.ensure_unique_slug(db)
        profile = {
            "slug": slug,
            "name": "Stats Test",
            "publisher_id": "pub123",
            "status": "active",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        result = await db.stats_profiles.insert_one(profile)
        profile_id = str(result.inserted_id)
        
        # Add clicks
        await db.stats_profile_clicks.insert_many([
            {
                "profile_id": profile_id,
                "profile_slug": slug,
                "ip_address": "192.168.1.1",
                "os": "Windows",
                "is_valid": True,
                "created_at": datetime.utcnow(),
            },
            {
                "profile_id": profile_id,
                "profile_slug": slug,
                "ip_address": "192.168.1.2",
                "os": "Mac",
                "is_valid": True,
                "created_at": datetime.utcnow(),
            },
            {
                "profile_id": profile_id,
                "profile_slug": slug,
                "ip_address": "192.168.1.3",
                "os": "Linux",
                "is_valid": False,
                "created_at": datetime.utcnow(),
            },
        ])
        
        # Aggregate
        stats = await sps.aggregate_stats(db, slug)
        
        assert stats["total_clicks"] == 3
        assert stats["unique_clicks"] == 3  # 3 unique IPs
        assert stats["valid_clicks"] == 2
        assert stats["invalid_clicks"] == 1
        
        # Cleanup
        await db.stats_profiles.delete_one({"_id": result.inserted_id})
        await db.stats_profile_clicks.delete_many({"profile_slug": slug})
    
    async def test_aggregate_os_stats(self, db):
        """Test OS statistics aggregation."""
        slug = await sps.ensure_unique_slug(db)
        profile = {
            "slug": slug,
            "name": "OS Stats Test",
            "publisher_id": "pub123",
            "status": "active",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        result = await db.stats_profiles.insert_one(profile)
        profile_id = str(result.inserted_id)
        
        # Add clicks with different OS
        await db.stats_profile_clicks.insert_many([
            {"profile_id": profile_id, "profile_slug": slug, "os": "Windows", "is_valid": True, "created_at": datetime.utcnow()},
            {"profile_id": profile_id, "profile_slug": slug, "os": "Windows", "is_valid": True, "created_at": datetime.utcnow()},
            {"profile_id": profile_id, "profile_slug": slug, "os": "Mac", "is_valid": True, "created_at": datetime.utcnow()},
        ])
        
        os_stats = await sps.aggregate_os_stats(db, slug)
        
        assert len(os_stats) == 2
        
        # Windows should be first (most clicks)
        assert os_stats[0]["os"] == "Windows"
        assert os_stats[0]["clicks"] == 2
        assert os_stats[1]["os"] == "Mac"
        assert os_stats[1]["clicks"] == 1
        
        # Cleanup
        await db.stats_profiles.delete_one({"_id": result.inserted_id})
        await db.stats_profile_clicks.delete_many({"profile_slug": slug})


# ═══════════════════════════════════════════════════════════════════════════════
# Manual Conversions Tests
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestManualConversions:
    """Test manual conversion overrides."""
    
    async def test_manual_conversion_included_in_stats(self, db):
        """Test manual conversions are included in aggregated stats."""
        slug = await sps.ensure_unique_slug(db)
        profile = {
            "slug": slug,
            "name": "Manual Conv Test",
            "publisher_id": "pub123",
            "status": "active",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        result = await db.stats_profiles.insert_one(profile)
        
        # Add manual conversion
        today = datetime.utcnow().strftime("%Y-%m-%d")
        await db.stats_profile_manual_conversions.insert_one({
            "profile_slug": slug,
            "date": today,
            "conversions": 50,
            "reason": "Test override",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        })
        
        # Aggregate stats
        stats = await sps.aggregate_stats(db, slug)
        
        assert stats["conversions"] == 50
        assert len(stats["manual_conversions_data"]) == 1
        assert stats["manual_conversions_data"][0]["conversions"] == 50
        
        # Cleanup
        await db.stats_profiles.delete_one({"_id": result.inserted_id})
        await db.stats_profile_manual_conversions.delete_many({"profile_slug": slug})


# ═══════════════════════════════════════════════════════════════════════════════
# Security Tests
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestSecurity:
    """Test security features."""
    
    async def test_opaque_slug_no_internal_ids(self, db):
        """Test slugs don't expose internal IDs."""
        slug = sps.generate_profile_slug()
        
        # Slug should be base62 only
        assert slug.isalnum()
        
        # Should not look like MongoDB ObjectId
        assert len(slug) == 8  # ObjectId is 24 hex chars
        
        # Should not be sequential
        slug2 = sps.generate_profile_slug()
        assert slug != slug2
    
    async def test_inactive_profile_tracking_rejected(self, db):
        """Test tracking is rejected for inactive profiles."""
        slug = await sps.ensure_unique_slug(db)
        profile = {
            "slug": slug,
            "name": "Inactive Test",
            "publisher_id": "pub123",
            "status": "paused",  # Inactive
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        result = await db.stats_profiles.insert_one(profile)
        
        # Try to track impression
        request_data = {"ip_address": "192.168.1.1"}
        success = await sps.track_impression(db, slug, request_data)
        
        assert success is False
        
        # Cleanup
        await db.stats_profiles.delete_one({"_id": result.inserted_id})
    
    async def test_serialization_no_internal_data(self, db):
        """Test serialized profile doesn't expose internal data."""
        profile = {
            "_id": ObjectId(),
            "slug": "abc12345",
            "name": "Security Test",
            "publisher_id": "pub123",
            "status": "active",
            "metadata": {"internal_campaign_id": "secret123"},
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        
        serialized = sps.serialize_profile(profile)
        
        # Should have public fields
        assert "slug" in serialized
        assert "name" in serialized
        assert "stats_url" in serialized
        
        # Should NOT have MongoDB _id directly exposed
        assert "_id" not in serialized
        assert "id" in serialized  # String version only
        
        # Metadata should be preserved (admin controls this)
        assert "metadata" in serialized


# ═══════════════════════════════════════════════════════════════════════════════
# Date Filtering Tests
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
class TestDateFiltering:
    """Test date range filtering in stats."""
    
    async def test_stats_with_date_range(self, db):
        """Test stats filtering by date range."""
        slug = await sps.ensure_unique_slug(db)
        profile = {
            "slug": slug,
            "name": "Date Test",
            "publisher_id": "pub123",
            "status": "active",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        result = await db.stats_profiles.insert_one(profile)
        profile_id = str(result.inserted_id)
        
        # Add clicks on different dates
        today = datetime.utcnow()
        yesterday = today - timedelta(days=1)
        week_ago = today - timedelta(days=7)
        
        await db.stats_profile_clicks.insert_many([
            {"profile_id": profile_id, "profile_slug": slug, "is_valid": True, "created_at": today},
            {"profile_id": profile_id, "profile_slug": slug, "is_valid": True, "created_at": yesterday},
            {"profile_id": profile_id, "profile_slug": slug, "is_valid": True, "created_at": week_ago},
        ])
        
        # Get stats for last 2 days
        stats = await sps.aggregate_stats(
            db, slug,
            date_from=yesterday.replace(hour=0, minute=0, second=0),
            date_to=today
        )
        
        # Should only include today and yesterday (2 clicks)
        assert stats["total_clicks"] == 2
        
        # Cleanup
        await db.stats_profiles.delete_one({"_id": result.inserted_id})
        await db.stats_profile_clicks.delete_many({"profile_slug": slug})
