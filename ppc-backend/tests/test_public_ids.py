"""
Tests for Public ID System (Phase 2)
======================================
Tests public publisher/website IDs, admin-created publishers, and smartlink generation.
"""

import pytest
from datetime import datetime
from bson import ObjectId
from app.utils.public_id_utils import (
    generate_public_id,
    generate_unique_publisher_id,
    generate_unique_website_id,
    resolve_publisher_id,
    resolve_website_id,
    get_publisher_public_id,
    get_website_public_id,
    is_public_id_format,
)
from app.services.smartlink_service import (
    generate_smartlink,
    generate_embed_code_with_smartlink,
    parse_smartlink_params,
)


class TestPublicIDGeneration:
    """Test public ID generation utilities."""
    
    def test_generate_public_id_format(self):
        """Test that generated IDs match expected format."""
        pub_id = generate_public_id("PUB")
        assert pub_id.startswith("PUB_")
        assert len(pub_id) == 12  # PUB_ + 8 chars
        assert pub_id[4:].isupper()
        assert pub_id[4:].isalnum()
    
    def test_generate_unique_ids(self):
        """Test that generated IDs are unique."""
        ids = {generate_public_id("PUB") for _ in range(100)}
        assert len(ids) == 100  # All unique
    
    @pytest.mark.asyncio
    async def test_generate_unique_publisher_id(self, db):
        """Test publisher ID generation with uniqueness check."""
        pub_id = await generate_unique_publisher_id(db)
        assert pub_id.startswith("PUB_")
        assert len(pub_id) == 12
    
    @pytest.mark.asyncio
    async def test_generate_unique_website_id(self, db):
        """Test website ID generation with uniqueness check."""
        site_id = await generate_unique_website_id(db)
        assert site_id.startswith("SITE_")
        assert len(site_id) == 13  # SITE_ + 8 chars


class TestPublicIDFormat:
    """Test public ID format validation."""
    
    def test_is_public_id_format_publisher(self):
        """Test publisher ID format validation."""
        assert is_public_id_format("PUB_ABCD1234", "publisher") is True
        assert is_public_id_format("PUB_ABC123", "publisher") is False  # Too short
        assert is_public_id_format("SITE_ABCD1234", "publisher") is False  # Wrong prefix
        assert is_public_id_format("abcd1234", "publisher") is False
    
    def test_is_public_id_format_website(self):
        """Test website ID format validation."""
        assert is_public_id_format("SITE_XYZ789AB", "website") is True
        assert is_public_id_format("SITE_XYZ", "website") is False  # Too short
        assert is_public_id_format("PUB_XYZ789AB", "website") is False  # Wrong prefix
    
    def test_is_public_id_format_any(self):
        """Test generic ID format validation."""
        assert is_public_id_format("PUB_ABCD1234") is True
        assert is_public_id_format("SITE_XYZ789AB") is True
        assert is_public_id_format("OTHER_123456") is False


@pytest.mark.asyncio
class TestPublisherIDResolution:
    """Test publisher ID resolution (public_id <-> internal_id)."""
    
    async def test_resolve_publisher_by_public_id(self, db, test_publisher):
        """Test resolving publisher by public_id."""
        # Add public_id to test publisher
        public_id = "PUB_TEST1234"
        await db.publishers.update_one(
            {"_id": test_publisher["_id"]},
            {"$set": {"public_id": public_id}}
        )
        
        resolved_id = await resolve_publisher_id(db, public_id)
        assert resolved_id == str(test_publisher["_id"])
    
    async def test_resolve_publisher_by_object_id(self, db, test_publisher):
        """Test backward compatibility: resolve by ObjectId."""
        resolved_id = await resolve_publisher_id(db, str(test_publisher["_id"]))
        assert resolved_id == str(test_publisher["_id"])
    
    async def test_resolve_publisher_not_found(self, db):
        """Test resolution returns None for invalid ID."""
        resolved_id = await resolve_publisher_id(db, "PUB_NOTFOUND")
        assert resolved_id is None
    
    async def test_get_publisher_public_id(self, db, test_publisher):
        """Test retrieving public_id for a publisher."""
        public_id = "PUB_LOOKUP01"
        await db.publishers.update_one(
            {"_id": test_publisher["_id"]},
            {"$set": {"public_id": public_id}}
        )
        
        result = await get_publisher_public_id(db, str(test_publisher["_id"]))
        assert result == public_id


@pytest.mark.asyncio
class TestWebsiteIDResolution:
    """Test website ID resolution (public_id <-> internal_id)."""
    
    async def test_resolve_website_by_public_id(self, db, test_website):
        """Test resolving website by public_id."""
        public_id = "SITE_TEST5678"
        await db.websites.update_one(
            {"_id": test_website["_id"]},
            {"$set": {"public_id": public_id}}
        )
        
        resolved_id = await resolve_website_id(db, public_id)
        assert resolved_id == str(test_website["_id"])
    
    async def test_resolve_website_by_object_id(self, db, test_website):
        """Test backward compatibility: resolve by ObjectId."""
        resolved_id = await resolve_website_id(db, str(test_website["_id"]))
        assert resolved_id == str(test_website["_id"])
    
    async def test_get_website_public_id(self, db, test_website):
        """Test retrieving public_id for a website."""
        public_id = "SITE_LOOKUP99"
        await db.websites.update_one(
            {"_id": test_website["_id"]},
            {"$set": {"public_id": public_id}}
        )
        
        result = await get_website_public_id(db, str(test_website["_id"]))
        assert result == public_id


@pytest.mark.asyncio
class TestSmartlinkGeneration:
    """Test smartlink URL generation."""
    
    async def test_generate_smartlink_with_public_ids(self, db, test_publisher, test_website):
        """Test smartlink generation using public IDs."""
        pub_public_id = "PUB_SMART001"
        site_public_id = "SITE_SMART001"
        
        await db.publishers.update_one(
            {"_id": test_publisher["_id"]},
            {"$set": {"public_id": pub_public_id}}
        )
        await db.websites.update_one(
            {"_id": test_website["_id"]},
            {"$set": {"public_id": site_public_id}}
        )
        
        smartlink = await generate_smartlink(
            db,
            str(test_publisher["_id"]),
            str(test_website["_id"]),
            base_url="https://clickspot.icu",
            use_public_ids=True,
        )
        
        assert smartlink.startswith("https://clickspot.icu/click?")
        assert f"pub={pub_public_id}" in smartlink
        assert f"site={site_public_id}" in smartlink
    
    async def test_generate_smartlink_with_object_ids(self, db, test_publisher, test_website):
        """Test smartlink generation using ObjectIds (legacy mode)."""
        smartlink = await generate_smartlink(
            db,
            str(test_publisher["_id"]),
            str(test_website["_id"]),
            base_url="https://example.com",
            use_public_ids=False,
        )
        
        assert smartlink.startswith("https://example.com/click?")
        assert f"pub={str(test_publisher['_id'])}" in smartlink
        assert f"site={str(test_website['_id'])}" in smartlink
    
    async def test_generate_smartlink_with_custom_params(self, db, test_publisher):
        """Test smartlink with custom query parameters."""
        pub_public_id = "PUB_CUSTOM01"
        await db.publishers.update_one(
            {"_id": test_publisher["_id"]},
            {"$set": {"public_id": pub_public_id}}
        )
        
        smartlink = await generate_smartlink(
            db,
            str(test_publisher["_id"]),
            None,
            base_url="https://test.com",
            use_public_ids=True,
            custom_params={"campaign": "summer2024", "source": "email"},
        )
        
        assert "campaign=summer2024" in smartlink
        assert "source=email" in smartlink
    
    async def test_generate_smartlink_with_referrer(self, db, test_publisher):
        """Test smartlink with pre-set referrer."""
        pub_public_id = "PUB_REF001"
        await db.publishers.update_one(
            {"_id": test_publisher["_id"]},
            {"$set": {"public_id": pub_public_id}}
        )
        
        smartlink = await generate_smartlink(
            db,
            str(test_publisher["_id"]),
            None,
            base_url="https://test.com",
            use_public_ids=True,
            referrer="https://example.com/page",
        )
        
        assert "ref=https%3A%2F%2Fexample.com%2Fpage" in smartlink


@pytest.mark.asyncio
class TestEmbedCodeGeneration:
    """Test embed code generation with smartlinks."""
    
    async def test_generate_embed_code_with_smartlink(self, db, test_publisher, test_website):
        """Test complete embed code + smartlink generation."""
        pub_public_id = "PUB_EMBED01"
        site_public_id = "SITE_EMBED01"
        
        await db.publishers.update_one(
            {"_id": test_publisher["_id"]},
            {"$set": {"public_id": pub_public_id}}
        )
        await db.websites.update_one(
            {"_id": test_website["_id"]},
            {"$set": {"public_id": site_public_id}}
        )
        
        result = await generate_embed_code_with_smartlink(
            db,
            str(test_publisher["_id"]),
            str(test_website["_id"]),
            "https://browsmac.org",
            use_public_ids=True,
        )
        
        assert "embed_code" in result
        assert "smart_link" in result
        assert "pub_identifier" in result
        assert "site_identifier" in result
        
        assert f'pub={pub_public_id}' in result["embed_code"]
        assert f'site={site_public_id}' in result["embed_code"]
        assert result["pub_identifier"] == pub_public_id
        assert result["site_identifier"] == site_public_id


@pytest.mark.asyncio
class TestSmartlinkParsing:
    """Test smartlink parameter parsing and resolution."""
    
    async def test_parse_smartlink_params_with_public_ids(self, db, test_publisher, test_website):
        """Test parsing smartlink with public IDs."""
        pub_public_id = "PUB_PARSE01"
        site_public_id = "SITE_PARSE01"
        
        await db.publishers.update_one(
            {"_id": test_publisher["_id"]},
            {"$set": {"public_id": pub_public_id}}
        )
        await db.websites.update_one(
            {"_id": test_website["_id"]},
            {"$set": {"public_id": site_public_id}}
        )
        
        result = await parse_smartlink_params(db, pub_public_id, site_public_id)
        
        assert result["publisher_id"] == str(test_publisher["_id"])
        assert result["website_id"] == str(test_website["_id"])
        assert result["pub_type"] == "public_id"
        assert result["site_type"] == "public_id"
    
    async def test_parse_smartlink_params_with_object_ids(self, db, test_publisher, test_website):
        """Test parsing smartlink with ObjectIds (backward compat)."""
        result = await parse_smartlink_params(
            db,
            str(test_publisher["_id"]),
            str(test_website["_id"]),
        )
        
        assert result["publisher_id"] == str(test_publisher["_id"])
        assert result["website_id"] == str(test_website["_id"])
        assert result["pub_type"] == "object_id"
        assert result["site_type"] == "object_id"
    
    async def test_parse_smartlink_params_publisher_only(self, db, test_publisher):
        """Test parsing smartlink with only publisher param."""
        pub_public_id = "PUB_ALONE01"
        await db.publishers.update_one(
            {"_id": test_publisher["_id"]},
            {"$set": {"public_id": pub_public_id}}
        )
        
        result = await parse_smartlink_params(db, pub_public_id, None)
        
        assert result["publisher_id"] == str(test_publisher["_id"])
        assert result["website_id"] is None
        assert result["site_type"] is None


@pytest.mark.asyncio
class TestClickTrackingWithPublicIDs:
    """Test click tracking with public ID smartlinks."""
    
    async def test_click_tracking_with_public_id(self, client, db, test_publisher, test_website):
        """Test /click endpoint accepts public_id parameters."""
        pub_public_id = "PUB_CLICK01"
        site_public_id = "SITE_CLICK01"
        
        await db.publishers.update_one(
            {"_id": test_publisher["_id"]},
            {"$set": {"public_id": pub_public_id, "status": "active"}}
        )
        await db.websites.update_one(
            {"_id": test_website["_id"]},
            {"$set": {"public_id": site_public_id}}
        )
        
        # Make click request with public IDs
        response = await client.get(
            f"/click?pub={pub_public_id}&site={site_public_id}",
            headers={"User-Agent": "Mozilla/5.0"},
            follow_redirects=False,
        )
        
        assert response.status_code in (302, 303, 307)  # Redirect response
        
        # Verify click was recorded with internal IDs
        click = await db.clicks.find_one({"publisher_id": str(test_publisher["_id"])})
        assert click is not None
        assert click["website_id"] == str(test_website["_id"])
    
    async def test_click_tracking_backward_compatible(self, client, db, test_publisher, test_website):
        """Test /click endpoint still accepts ObjectId parameters."""
        await db.publishers.update_one(
            {"_id": test_publisher["_id"]},
            {"$set": {"status": "active"}}
        )
        
        # Make click request with ObjectIDs (old format)
        response = await client.get(
            f"/click?pub={str(test_publisher['_id'])}&site={str(test_website['_id'])}",
            headers={"User-Agent": "Mozilla/5.0"},
            follow_redirects=False,
        )
        
        assert response.status_code in (302, 303, 307)
        
        click = await db.clicks.find_one({"publisher_id": str(test_publisher["_id"])})
        assert click is not None
