"""
Test Redirect Chain Flow
=========================

Tests the complete redirect chain flow with configurable length:
- Anchor → Inter → Prelander (3-hop chain)
- Anchor → Inter → C → Prelander (4-hop chain)
- Anchor → Inter → C → D → Prelander (5-hop chain)
- Anchor → Inter → C → D → ... → N → Prelander (N-hop chain)

Verifies:
- Global rule: chains apply to ALL publishers
- Chain middleware handles all hops correctly
- Traffic router uses anchor as entry point when chain exists
- Extra domains are processed in order
"""

import pytest
from datetime import datetime


@pytest.mark.asyncio
class TestRedirectChainFlow:
    """Test complete redirect chain flow with configurable length."""
    
    async def test_3_hop_chain_basic(self, db):
        """Test basic 3-hop chain: Anchor → Inter → Prelander"""
        # Create redirect chain
        chain_doc = {
            "name": "3-Hop Chain",
            "anchor_domain": "anchor.test.com",
            "inter_domain": "inter.test.com",
            "prelander_pool": ["prelander1.test.com", "prelander2.test.com"],
            "extra_domains": [],
            "session_validation": True,
            "cookie_lifetime": 60,
            "status": "active",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "total_sessions": 0,
            "valid_sessions": 0,
            "blocked_sessions": 0,
            "conversion_rate": 0.0,
        }
        result = await db.redirect_chains.insert_one(chain_doc)
        chain_id = result.inserted_id
        
        # Verify chain was created
        chain = await db.redirect_chains.find_one({"_id": chain_id})
        assert chain is not None
        assert chain["name"] == "3-Hop Chain"
        assert chain["anchor_domain"] == "anchor.test.com"
        assert chain["inter_domain"] == "inter.test.com"
        assert len(chain["prelander_pool"]) == 2
        assert len(chain.get("extra_domains", [])) == 0
        
        # Test middleware helper functions
        from app.middleware.redirect_chain_middleware import RedirectChainMiddleware
        
        middleware = RedirectChainMiddleware(None)
        
        # Test domain position detection
        assert middleware._get_domain_position_in_chain(chain, "anchor.test.com") == "anchor"
        assert middleware._get_domain_position_in_chain(chain, "inter.test.com") == "inter"
        assert middleware._get_domain_position_in_chain(chain, "prelander1.test.com") == "prelander"
        
        # Test next hop resolution
        assert middleware._get_next_hop_in_chain(chain, "anchor") == "inter.test.com"
        assert middleware._get_next_hop_in_chain(chain, "inter") == "PRELANDER_POOL"
        assert middleware._get_next_hop_in_chain(chain, "prelander") is None
        
        # Cleanup
        await db.redirect_chains.delete_one({"_id": chain_id})
    
    async def test_4_hop_chain_with_one_extra(self, db):
        """Test 4-hop chain: Anchor → Inter → C → Prelander"""
        # Create redirect chain with one extra domain
        chain_doc = {
            "name": "4-Hop Chain",
            "anchor_domain": "anchor.test.com",
            "inter_domain": "inter.test.com",
            "extra_domains": ["extra-c.test.com"],
            "prelander_pool": ["prelander.test.com"],
            "session_validation": True,
            "cookie_lifetime": 60,
            "status": "active",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "total_sessions": 0,
            "valid_sessions": 0,
            "blocked_sessions": 0,
            "conversion_rate": 0.0,
        }
        result = await db.redirect_chains.insert_one(chain_doc)
        chain_id = result.inserted_id
        
        # Verify chain was created
        chain = await db.redirect_chains.find_one({"_id": chain_id})
        assert chain is not None
        assert len(chain.get("extra_domains", [])) == 1
        assert chain["extra_domains"][0] == "extra-c.test.com"
        
        # Test middleware helper functions
        from app.middleware.redirect_chain_middleware import RedirectChainMiddleware
        
        middleware = RedirectChainMiddleware(None)
        
        # Test domain position detection
        assert middleware._get_domain_position_in_chain(chain, "anchor.test.com") == "anchor"
        assert middleware._get_domain_position_in_chain(chain, "inter.test.com") == "inter"
        assert middleware._get_domain_position_in_chain(chain, "extra-c.test.com") == "extra_0"
        assert middleware._get_domain_position_in_chain(chain, "prelander.test.com") == "prelander"
        
        # Test next hop resolution
        assert middleware._get_next_hop_in_chain(chain, "anchor") == "inter.test.com"
        assert middleware._get_next_hop_in_chain(chain, "inter") == "extra-c.test.com"
        assert middleware._get_next_hop_in_chain(chain, "extra_0") == "PRELANDER_POOL"
        
        # Cleanup
        await db.redirect_chains.delete_one({"_id": chain_id})
    
    async def test_5_hop_chain_with_two_extras(self, db):
        """Test 5-hop chain: Anchor → Inter → C → D → Prelander"""
        # Create redirect chain with two extra domains
        chain_doc = {
            "name": "5-Hop Chain",
            "anchor_domain": "anchor.test.com",
            "inter_domain": "inter.test.com",
            "extra_domains": ["extra-c.test.com", "extra-d.test.com"],
            "prelander_pool": ["prelander.test.com"],
            "session_validation": True,
            "cookie_lifetime": 60,
            "status": "active",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "total_sessions": 0,
            "valid_sessions": 0,
            "blocked_sessions": 0,
            "conversion_rate": 0.0,
        }
        result = await db.redirect_chains.insert_one(chain_doc)
        chain_id = result.inserted_id
        
        # Verify chain was created
        chain = await db.redirect_chains.find_one({"_id": chain_id})
        assert chain is not None
        assert len(chain.get("extra_domains", [])) == 2
        assert chain["extra_domains"][0] == "extra-c.test.com"
        assert chain["extra_domains"][1] == "extra-d.test.com"
        
        # Test middleware helper functions
        from app.middleware.redirect_chain_middleware import RedirectChainMiddleware
        
        middleware = RedirectChainMiddleware(None)
        
        # Test domain position detection
        assert middleware._get_domain_position_in_chain(chain, "extra-c.test.com") == "extra_0"
        assert middleware._get_domain_position_in_chain(chain, "extra-d.test.com") == "extra_1"
        
        # Test next hop resolution
        assert middleware._get_next_hop_in_chain(chain, "anchor") == "inter.test.com"
        assert middleware._get_next_hop_in_chain(chain, "inter") == "extra-c.test.com"
        assert middleware._get_next_hop_in_chain(chain, "extra_0") == "extra-d.test.com"
        assert middleware._get_next_hop_in_chain(chain, "extra_1") == "PRELANDER_POOL"
        
        # Cleanup
        await db.redirect_chains.delete_one({"_id": chain_id})
    
    async def test_chain_domain_lookup(self, db):
        """Test that chain can be found by any domain in the chain"""
        # Create redirect chain with multiple domains
        chain_doc = {
            "name": "Full Chain",
            "anchor_domain": "anchor.test.com",
            "inter_domain": "inter.test.com",
            "extra_domains": ["extra1.test.com", "extra2.test.com", "extra3.test.com"],
            "prelander_pool": ["pre1.test.com", "pre2.test.com"],
            "session_validation": True,
            "cookie_lifetime": 60,
            "status": "active",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "total_sessions": 0,
            "valid_sessions": 0,
            "blocked_sessions": 0,
            "conversion_rate": 0.0,
        }
        result = await db.redirect_chains.insert_one(chain_doc)
        chain_id = result.inserted_id
        
        # Test that chain can be found by each domain
        from app.middleware.redirect_chain_middleware import RedirectChainMiddleware
        
        middleware = RedirectChainMiddleware(None)
        
        # Should find chain by anchor domain
        chain = await middleware._get_chain_for_domain(db, "anchor.test.com")
        assert chain is not None
        assert str(chain["_id"]) == str(chain_id)
        
        # Should find chain by inter domain
        chain = await middleware._get_chain_for_domain(db, "inter.test.com")
        assert chain is not None
        assert str(chain["_id"]) == str(chain_id)
        
        # Should find chain by extra domains
        chain = await middleware._get_chain_for_domain(db, "extra1.test.com")
        assert chain is not None
        chain = await middleware._get_chain_for_domain(db, "extra2.test.com")
        assert chain is not None
        chain = await middleware._get_chain_for_domain(db, "extra3.test.com")
        assert chain is not None
        
        # Should find chain by prelander domains
        chain = await middleware._get_chain_for_domain(db, "pre1.test.com")
        assert chain is not None
        chain = await middleware._get_chain_for_domain(db, "pre2.test.com")
        assert chain is not None
        
        # Should NOT find chain by unknown domain
        chain = await middleware._get_chain_for_domain(db, "unknown.test.com")
        assert chain is None
        
        # Cleanup
        await db.redirect_chains.delete_one({"_id": chain_id})
    
    async def test_global_rule_applies_to_all_publishers(self, db):
        """Test that chains apply to ALL publishers (global rule)"""
        # Create redirect chain
        chain_doc = {
            "name": "Global Chain",
            "anchor_domain": "anchor.global.com",
            "inter_domain": "inter.global.com",
            "extra_domains": [],
            "prelander_pool": ["pre.global.com"],
            "session_validation": True,
            "cookie_lifetime": 60,
            "status": "active",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "total_sessions": 0,
            "valid_sessions": 0,
            "blocked_sessions": 0,
            "conversion_rate": 0.0,
        }
        result = await db.redirect_chains.insert_one(chain_doc)
        chain_id = result.inserted_id
        
        # Create multiple publishers
        pub1 = await db.publishers.insert_one({
            "name": "Publisher 1",
            "email": "pub1@test.com",
            "status": "active",
            "created_at": datetime.utcnow(),
        })
        pub2 = await db.publishers.insert_one({
            "name": "Publisher 2",
            "email": "pub2@test.com",
            "status": "active",
            "created_at": datetime.utcnow(),
        })
        
        # Resolve chain for different publishers - should return same chain
        from app.services.traffic_router import resolve_active_chain
        
        chain_for_pub1 = await resolve_active_chain(db, str(pub1.inserted_id))
        chain_for_pub2 = await resolve_active_chain(db, str(pub2.inserted_id))
        chain_for_none = await resolve_active_chain(db, None)
        
        # All should get the same chain
        assert chain_for_pub1 is not None
        assert chain_for_pub2 is not None
        assert chain_for_none is not None
        assert str(chain_for_pub1["_id"]) == str(chain_id)
        assert str(chain_for_pub2["_id"]) == str(chain_id)
        assert str(chain_for_none["_id"]) == str(chain_id)
        
        # Cleanup
        await db.redirect_chains.delete_one({"_id": chain_id})
        await db.publishers.delete_one({"_id": pub1.inserted_id})
        await db.publishers.delete_one({"_id": pub2.inserted_id})
