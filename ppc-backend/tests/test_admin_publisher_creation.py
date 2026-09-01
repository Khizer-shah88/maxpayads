"""
Tests for Admin-Created Publishers (Phase 2)
=============================================
Tests admin publisher creation, website management, and ownership tracking.
"""

import pytest
from bson import ObjectId


@pytest.mark.asyncio
class TestAdminPublisherCreation:
    """Test admin creating publishers directly."""
    
    async def test_admin_create_publisher_basic(self, client, admin_token, db):
        """Test admin can create a publisher account."""
        response = await client.post(
            "/admin/publishers",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "Test Publisher",
                "email": "testpub@example.com",
                "password": "SecurePass123",
                "status": "active",
                "revenue_share": 0.75,
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert "publisher_id" in data
        
        # Verify publisher in database
        publisher = await db.publishers.find_one({"email": "testpub@example.com"})
        assert publisher is not None
        assert publisher["name"] == "Test Publisher"
        assert publisher["status"] == "active"
        assert publisher["revenue_share"] == 0.75
        assert publisher["is_admin_created"] is True
        assert publisher["created_by"] is not None  # Admin ID
        assert "public_id" in publisher
        assert publisher["public_id"].startswith("PUB_")
    
    async def test_admin_create_publisher_with_website(self, client, admin_token, db):
        """Test admin can create publisher with initial website."""
        response = await client.post(
            "/admin/publishers",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "Publisher With Site",
                "email": "pubwithsite@example.com",
                "password": "SecurePass123",
                "website_domain": "example-site.com",
                "status": "active",
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        publisher_id = data["publisher_id"]
        
        # Verify website was created
        website = await db.websites.find_one({"publisher_id": publisher_id})
        assert website is not None
        assert website["domain"] == "example-site.com"
        assert website["public_id"].startswith("SITE_")
    
    async def test_admin_create_publisher_custom_cpc(self, client, admin_token, db):
        """Test admin can set custom CPC during creation."""
        response = await client.post(
            "/admin/publishers",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "High CPC Publisher",
                "email": "highcpc@example.com",
                "password": "SecurePass123",
                "custom_cpc": 0.15,
                "status": "active",
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        
        publisher = await db.publishers.find_one({"email": "highcpc@example.com"})
        assert publisher["custom_cpc"] == 0.15
    
    async def test_admin_create_publisher_duplicate_email(self, client, admin_token, db, test_publisher):
        """Test admin cannot create publisher with duplicate email."""
        response = await client.post(
            "/admin/publishers",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "Duplicate",
                "email": test_publisher["email"],
                "password": "SecurePass123",
            }
        )
        
        assert response.status_code == 409
        data = response.json()
        assert "already registered" in data["detail"].lower()
    
    async def test_admin_create_publisher_missing_fields(self, client, admin_token):
        """Test admin creation fails with missing required fields."""
        response = await client.post(
            "/admin/publishers",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "Incomplete"
                # Missing email and password
            }
        )
        
        assert response.status_code == 400
    
    async def test_admin_create_publisher_short_password(self, client, admin_token):
        """Test admin creation enforces minimum password length."""
        response = await client.post(
            "/admin/publishers",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "name": "Short Pass",
                "email": "shortpass@example.com",
                "password": "123",  # Too short
            }
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "8 characters" in data["detail"]


@pytest.mark.asyncio
class TestAdminWebsiteManagement:
    """Test admin managing publisher websites."""
    
    async def test_admin_add_website_to_publisher(self, client, admin_token, db, test_publisher):
        """Test admin can add website directly to publisher."""
        response = await client.post(
            f"/admin/publishers/{str(test_publisher['_id'])}/websites",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "domain": "admin-added.com",
                "name": "Admin Added Site",
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert "website_id" in data
        
        # Verify website in database
        website = await db.websites.find_one({"domain": "admin-added.com"})
        assert website is not None
        assert website["publisher_id"] == str(test_publisher["_id"])
        assert website["name"] == "Admin Added Site"
        assert website["public_id"].startswith("SITE_")
    
    async def test_admin_add_website_missing_domain(self, client, admin_token, test_publisher):
        """Test admin website creation requires domain."""
        response = await client.post(
            f"/admin/publishers/{str(test_publisher['_id'])}/websites",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"name": "No Domain"}
        )
        
        assert response.status_code == 400
    
    async def test_admin_add_website_invalid_publisher(self, client, admin_token):
        """Test admin cannot add website to non-existent publisher."""
        fake_id = str(ObjectId())
        response = await client.post(
            f"/admin/publishers/{fake_id}/websites",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={"domain": "test.com"}
        )
        
        assert response.status_code == 404


@pytest.mark.asyncio
class TestPublisherOwnershipTracking:
    """Test admin-created vs self-registered tracking."""
    
    async def test_self_registered_publisher_tracking(self, db):
        """Test self-registered publishers are marked correctly."""
        from app.services.publisher_service import create_publisher
        
        publisher_data = {
            "name": "Self Registered",
            "email": "selfreg@example.com",
            "password": "password123",
        }
        
        publisher_id = await create_publisher(publisher_data, db, admin_id=None)
        
        publisher = await db.publishers.find_one({"_id": ObjectId(publisher_id)})
        assert publisher["is_admin_created"] is False
        assert publisher["created_by"] is None
        assert "public_id" in publisher
    
    async def test_admin_created_publisher_tracking(self, db, test_admin):
        """Test admin-created publishers track creator."""
        from app.services.publisher_service import create_publisher
        
        publisher_data = {
            "name": "Admin Created",
            "email": "admincreated@example.com",
            "password": "password123",
            "status": "active",
        }
        
        publisher_id = await create_publisher(
            publisher_data, db, admin_id=str(test_admin["_id"])
        )
        
        publisher = await db.publishers.find_one({"_id": ObjectId(publisher_id)})
        assert publisher["is_admin_created"] is True
        assert publisher["created_by"] == str(test_admin["_id"])
        assert publisher["status"] == "active"  # Admin can set status
        assert "public_id" in publisher


@pytest.mark.asyncio
class TestPublisherAuthorization:
    """Test publisher ownership and access control."""
    
    async def test_publisher_can_only_see_own_websites(self, client, db, test_publisher, publisher_token):
        """Test publishers only see their own websites."""
        # Create websites for test publisher
        await db.websites.insert_one({
            "publisher_id": str(test_publisher["_id"]),
            "public_id": "SITE_OWN001",
            "domain": "mysite.com",
            "name": "My Site",
            "status": "active",
            "total_clicks": 0,
            "total_earnings": 0.0,
        })
        
        # Create website for different publisher
        other_publisher = await db.publishers.insert_one({
            "name": "Other",
            "email": "other@test.com",
            "password_hash": "hash",
            "role": "publisher",
            "status": "active",
        })
        
        await db.websites.insert_one({
            "publisher_id": str(other_publisher.inserted_id),
            "public_id": "SITE_OTHER01",
            "domain": "othersite.com",
            "name": "Other Site",
            "status": "active",
            "total_clicks": 0,
            "total_earnings": 0.0,
        })
        
        # Get websites as test_publisher
        response = await client.get(
            "/publisher/websites",
            headers={"Authorization": f"Bearer {publisher_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        websites = data["websites"]
        
        # Should only see own website
        assert len(websites) == 1
        assert websites[0]["domain"] == "mysite.com"
        assert websites[0]["site_identifier"] == "SITE_OWN001"
    
    async def test_publisher_cannot_delete_other_website(self, client, db, test_publisher, publisher_token):
        """Test publishers cannot delete other publishers' websites."""
        # Create website for different publisher
        other_publisher = await db.publishers.insert_one({
            "name": "Other",
            "email": "other2@test.com",
            "password_hash": "hash",
            "role": "publisher",
            "status": "active",
        })
        
        other_website = await db.websites.insert_one({
            "publisher_id": str(other_publisher.inserted_id),
            "domain": "othersite.com",
            "name": "Other Site",
            "status": "active",
            "total_clicks": 0,
            "total_earnings": 0.0,
        })
        
        # Try to delete as test_publisher
        response = await client.delete(
            f"/publisher/websites/{str(other_website.inserted_id)}",
            headers={"Authorization": f"Bearer {publisher_token}"}
        )
        
        assert response.status_code == 404  # Not found (because ownership check fails)
        
        # Verify website still exists
        website = await db.websites.find_one({"_id": other_website.inserted_id})
        assert website is not None


@pytest.mark.asyncio
class TestPublicIDUniqueness:
    """Test public ID uniqueness constraints."""
    
    async def test_publisher_public_ids_are_unique(self, db):
        """Test that duplicate publisher public_ids are prevented."""
        from app.utils.public_id_utils import generate_unique_publisher_id
        
        # Generate and insert first publisher
        pub_id_1 = await generate_unique_publisher_id(db)
        await db.publishers.insert_one({
            "name": "Publisher 1",
            "email": "pub1@test.com",
            "password_hash": "hash",
            "public_id": pub_id_1,
            "role": "publisher",
            "status": "pending",
        })
        
        # Generate second ID - should be different
        pub_id_2 = await generate_unique_publisher_id(db)
        assert pub_id_1 != pub_id_2
        
        # Try to insert duplicate public_id - should fail
        with pytest.raises(Exception):  # DuplicateKeyError
            await db.publishers.insert_one({
                "name": "Publisher 2",
                "email": "pub2@test.com",
                "password_hash": "hash",
                "public_id": pub_id_1,  # Duplicate!
                "role": "publisher",
                "status": "pending",
            })
    
    async def test_website_public_ids_are_unique(self, db, test_publisher):
        """Test that duplicate website public_ids are prevented."""
        from app.utils.public_id_utils import generate_unique_website_id
        
        # Generate and insert first website
        site_id_1 = await generate_unique_website_id(db)
        await db.websites.insert_one({
            "publisher_id": str(test_publisher["_id"]),
            "public_id": site_id_1,
            "domain": "site1.com",
            "name": "Site 1",
            "status": "active",
        })
        
        # Generate second ID - should be different
        site_id_2 = await generate_unique_website_id(db)
        assert site_id_1 != site_id_2
        
        # Try to insert duplicate public_id - should fail
        with pytest.raises(Exception):
            await db.websites.insert_one({
                "publisher_id": str(test_publisher["_id"]),
                "public_id": site_id_1,  # Duplicate!
                "domain": "site2.com",
                "name": "Site 2",
                "status": "active",
            })
