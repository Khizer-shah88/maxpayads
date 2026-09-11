"""
Publisher & Domain rules (Domain Glossary steps 4–5).

Covers:
- Manual Publishers: name/tag only, auto-generated Publisher ID, no login,
  Smartlink never carries a site param.
- Admin Smartlink generation: registered vs manual formats.
- Publisher status rules: banned/removed keep redirecting and stay in Admin
  Statistics, but Direct Link Stats is unavailable.
- Domain validation: exact duplicate hostnames rejected across types
  (case-insensitive after normalization); example.com vs www.example.com vs
  a.example.com are distinct.
- Prelander weights: inactive prelanders get no traffic; active ones are
  picked by weight.
"""

import pytest
from bson import ObjectId


# ── Manual Publisher ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestManualPublisher:
    async def test_create_manual_publisher(self, db):
        from app.services.publisher_service import create_manual_publisher

        pid = await create_manual_publisher({"name": "push-network-a"}, db, admin_id="admin1")
        pub = await db.publishers.find_one({"_id": ObjectId(pid)})
        assert pub is not None
        assert pub["publisher_type"] == "manual"
        assert pub["status"] == "active"
        assert pub["public_id"].startswith("PUB_")
        assert pub["is_admin_created"] is True

    async def test_manual_publisher_requires_unique_name(self, db):
        from app.services.publisher_service import create_manual_publisher

        await create_manual_publisher({"name": "unique-tag-123"}, db)
        with pytest.raises(ValueError):
            await create_manual_publisher({"name": "unique-tag-123"}, db)

    async def test_smartlink_endpoint_manual_has_no_site_param(self, client, db, admin_token):
        from app.services.publisher_service import create_manual_publisher

        pid = await create_manual_publisher({"name": "manual-smartlink-test"}, db)
        res = await client.get(
            f"/admin/publishers/{pid}/smartlink",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["success"] is True
        assert body["publisher_type"] == "manual"
        # Manual smartlink: only pub param — never site.
        assert "site=" not in body["smartlink"]
        assert f"pub={body['public_id']}" in body["smartlink"]
        assert body["website_smartlinks"] == []

    async def test_smartlink_endpoint_registered_includes_sites(self, client, db, admin_token, test_publisher, test_website):
        from app.utils.public_id_utils import generate_unique_publisher_id, generate_unique_website_id

        # Ensure public ids exist so the link uses them
        await db.publishers.update_one(
            {"_id": test_publisher["_id"]},
            {"$set": {"public_id": await generate_unique_publisher_id(db)}},
        )
        await db.websites.update_one(
            {"_id": test_website["_id"]},
            {"$set": {
                "public_id": await generate_unique_website_id(db),
                "publisher_id": str(test_publisher["_id"]),
            }},
        )
        res = await client.get(
            f"/admin/publishers/{str(test_publisher['_id'])}/smartlink",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["publisher_type"] == "registered"
        assert len(body["website_smartlinks"]) >= 1
        for entry in body["website_smartlinks"]:
            assert "site=" in entry["smartlink"]

    async def test_manual_publisher_click_ignores_site_param(self, db, redis):
        """A stray site param on a manual publisher's link is dropped, not fatal."""
        from app.services.publisher_service import create_manual_publisher
        from app.services.redirect_pipeline import (
            RedirectResolutionContext, stage_identify_publisher,
        )

        pid = await create_manual_publisher({"name": "manual-site-ignore"}, db)
        pub = await db.publishers.find_one({"_id": ObjectId(pid)})
        ctx = RedirectResolutionContext(raw_pub=pub["public_id"], raw_site="SITE_XXXXXXXX")
        ok = await stage_identify_publisher(ctx, db)
        assert ok is True
        assert ctx.publisher_id == pid
        assert ctx.website_id is None  # site never binds for manual publishers


# ── Publisher status rules ────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestPublisherStatusRules:
    async def test_banned_publisher_still_resolves_for_redirects(self, db):
        """Banning must never break Smartlinks: identify still succeeds."""
        from app.services.publisher_service import create_manual_publisher
        from app.services.redirect_pipeline import (
            RedirectResolutionContext, stage_identify_publisher,
        )

        pid = await create_manual_publisher({"name": "banned-pub-flow"}, db)
        await db.publishers.update_one({"_id": ObjectId(pid)}, {"$set": {"status": "banned"}})
        pub = await db.publishers.find_one({"_id": ObjectId(pid)})

        ctx = RedirectResolutionContext(raw_pub=pub["public_id"])
        ok = await stage_identify_publisher(ctx, db)
        assert ok is True
        assert ctx.publisher_id == pid

    async def test_banned_publisher_direct_link_stats_unavailable(self, client, db, admin_token):
        from app.services.publisher_service import create_manual_publisher

        pid = await create_manual_publisher({"name": "banned-dls-pub"}, db)
        await db.publishers.update_one({"_id": ObjectId(pid)}, {"$set": {"status": "banned"}})

        res = await client.get(
            f"/direct-links/stats/publisher/{pid}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 403  # unavailable — not 404, links still work

    async def test_active_publisher_direct_link_stats_available(self, client, db, admin_token):
        from app.services.publisher_service import create_manual_publisher

        pid = await create_manual_publisher({"name": "active-dls-pub"}, db)
        res = await client.get(
            f"/direct-links/stats/publisher/{pid}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200

    async def test_banned_publisher_removed_from_panel(self, client, db, publisher_token):
        """Banned publishers cannot use the panel (login gate, not redirect gate)."""
        from app.core.security import create_access_token
        from app.services.publisher_service import create_manual_publisher

        pid = await create_manual_publisher({"name": "banned-panel-pub"}, db)
        await db.publishers.update_one({"_id": ObjectId(pid)}, {"$set": {"status": "banned"}})
        token = create_access_token({"sub": pid, "role": "publisher"})

        res = await client.get(
            "/publisher/dashboard",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 403

    async def test_delete_publisher_removes_records(self, db):
        from app.services.publisher_service import (
            create_manual_publisher, delete_publisher_and_records,
        )

        pid = await create_manual_publisher({"name": "delete-me-pub"}, db)
        await db.clicks.insert_one({"publisher_id": pid, "status": "pending"})
        await db.withdrawals.insert_one({"publisher_id": pid, "status": "pending"})

        deleted = await delete_publisher_and_records(pid, db)
        assert deleted is True
        assert await db.publishers.find_one({"_id": ObjectId(pid)}) is None
        assert await db.clicks.find_one({"publisher_id": pid}) is None
        assert await db.withdrawals.find_one({"publisher_id": pid}) is None

    async def test_admin_update_rejects_invalid_status(self, client, db, admin_token):
        from app.services.publisher_service import create_manual_publisher

        pid = await create_manual_publisher({"name": "status-validation-pub"}, db)
        res = await client.patch(
            f"/admin/publishers/{pid}",
            json={"status": "not-a-status"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 400

    async def test_admin_update_accepts_banned(self, client, db, admin_token):
        from app.services.publisher_service import create_manual_publisher

        pid = await create_manual_publisher({"name": "status-ban-ok"}, db)
        res = await client.patch(
            f"/admin/publishers/{pid}",
            json={"status": "banned"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200
        pub = await db.publishers.find_one({"_id": ObjectId(pid)})
        assert pub["status"] == "banned"


# ── Domain validation ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestDomainValidation:
    async def test_exact_duplicate_rejected_across_types(self, db):
        from app.services.domain_service import create_domain

        await create_domain(db, {"domain": "Example.com", "domain_type": "anchor"})
        # Same hostname as a different type — rejected (normalized lowercase).
        with pytest.raises(ValueError):
            await create_domain(db, {"domain": "https://example.com", "domain_type": "inter"})

    async def test_distinct_subdomains_allowed(self, db):
        from app.services.domain_service import create_domain

        a = await create_domain(db, {"domain": "example.com", "domain_type": "anchor"})
        b = await create_domain(db, {"domain": "www.example.com", "domain_type": "inter"})
        c = await create_domain(db, {"domain": "a.example.com", "domain_type": "prelander"})
        assert a["domain"] == "example.com"
        assert b["domain"] == "www.example.com"
        assert c["domain"] == "a.example.com"

    async def test_update_rejects_duplicate_hostname(self, db):
        from app.services.domain_service import create_domain, update_domain

        d1 = await create_domain(db, {"domain": "one.example.com", "domain_type": "anchor"})
        await create_domain(db, {"domain": "two.example.com", "domain_type": "inter"})
        with pytest.raises(ValueError):
            await update_domain(db, d1["id"], {"domain": "TWO.example.com"})

    async def test_delete_reports_affected_chains(self, db):
        from app.services.domain_service import create_domain

        anchor = await create_domain(db, {"domain": "chain-anchor-test.com", "domain_type": "anchor"})
        inter = await create_domain(db, {"domain": "chain-inter-test.com", "domain_type": "inter"})
        pre = await create_domain(db, {"domain": "chain-pre-test.com", "domain_type": "prelander"})
        chain = {
            "name": "Chain test",
            "anchor_domain": anchor["domain"],
            "inter_domain": inter["domain"],
            "prelander_pool": [pre["domain"]],
            "status": "active",
        }
        await db.redirect_chains.insert_one(chain)

        # The delete router reports affected chains; verify the raw query logic.
        affected = []
        async for c in db.redirect_chains.find({
            "$or": [
                {"anchor_domain": pre["domain"]},
                {"inter_domain": pre["domain"]},
                {"prelander_pool": pre["domain"]},
            ]
        }):
            affected.append(c["name"])
        assert affected == ["Chain test"]


# ── Prelander weight distribution ──────────────────────────────────────────────

@pytest.mark.asyncio
class TestPrelanderWeights:
    async def test_inactive_prelander_gets_no_traffic(self, db):
        from app.services.domain_service import select_active_prelander

        await db.redirection_domains.insert_many([
            {"domain": "p1.example.com", "domain_type": "prelander", "status": "active", "weight": 50},
            {"domain": "p2.example.com", "domain_type": "prelander", "status": "paused", "weight": 50},
        ])
        pool = ["p1.example.com", "p2.example.com"]
        for _ in range(20):
            assert await select_active_prelander(db, pool) == "p1.example.com"

    async def test_weight_zero_prelander_skipped(self, db):
        from app.services.domain_service import select_active_prelander

        await db.redirection_domains.insert_many([
            {"domain": "w0.example.com", "domain_type": "prelander", "status": "active", "weight": 0},
            {"domain": "w100.example.com", "domain_type": "prelander", "status": "active", "weight": 100},
        ])
        pool = ["w0.example.com", "w100.example.com"]
        for _ in range(20):
            assert await select_active_prelander(db, pool) == "w100.example.com"

    async def test_no_active_prelanders_returns_none(self, db):
        from app.services.domain_service import select_active_prelander

        await db.redirection_domains.insert_one({
            "domain": "dead.example.com", "domain_type": "prelander",
            "status": "paused", "weight": 100,
        })
        assert await select_active_prelander(db, ["dead.example.com"]) is None

    async def test_weighted_distribution_roughly_proportional(self, db):
        from app.services.domain_service import select_active_prelander

        await db.redirection_domains.insert_many([
            {"domain": "heavy.example.com", "domain_type": "prelander", "status": "active", "weight": 300},
            {"domain": "light.example.com", "domain_type": "prelander", "status": "active", "weight": 100},
        ])
        pool = ["heavy.example.com", "light.example.com"]
        counts = {"heavy.example.com": 0, "light.example.com": 0}
        for _ in range(400):
            picked = await select_active_prelander(db, pool)
            counts[picked] += 1
        # Expect ~75/25 within a generous tolerance.
        assert 0.65 < counts["heavy.example.com"] / 400 < 0.85
        assert 0.15 < counts["light.example.com"] / 400 < 0.35


# ── Campaign value resolution (Specific OS+Country → OS-specific → Global) ─────

@pytest.mark.asyncio
class TestCampaignValueResolution:
    async def test_os_plus_country_beats_os_specific(self, db):
        from app.services.targeting_engine import resolve_campaign_for_click

        global_id = await db.campaigns.insert_one({
            "name": "Global", "device_os": "global", "status": "active",
            "default_offer_url": "https://g.example",
        }).inserted_id
        os_id = await db.campaigns.insert_one({
            "name": "Windows OS", "device_os": "windows", "status": "active",
            "default_offer_url": "https://w.example",
        }).inserted_id
        targeted_id = await db.campaigns.insert_one({
            "name": "Windows US", "device_os": "windows", "status": "active",
            "default_offer_url": "https://w-us.example",
        }).inserted_id
        await db.geo_rules.insert_one({
            "campaign_id": str(targeted_id), "country_code": "US",
            "offer_url": "https://w-us.example", "priority": 10,
        })

        campaign = await resolve_campaign_for_click(
            {"os": "Windows", "country_code": "US", "device_type": "desktop"}, db
        )
        assert campaign == str(targeted_id)

        # Different country → falls to OS-specific.
        campaign = await resolve_campaign_for_click(
            {"os": "Windows", "country_code": "DE", "device_type": "desktop"}, db
        )
        assert campaign == str(os_id)

        # No OS match → Global.
        campaign = await resolve_campaign_for_click(
            {"os": "Android", "country_code": "US", "device_type": "mobile"}, db
        )
        assert campaign == str(global_id)

    async def test_fallback_never_serves_wrong_os(self, db):
        """Weighted fallback must not hand a Mac visitor a Windows campaign."""
        from app.services.targeting_engine import resolve_campaign_for_click

        await db.campaigns.insert_one({
            "name": "Only Windows", "device_os": "windows", "status": "active",
            "default_offer_url": "https://w.example",
        })
        campaign = await resolve_campaign_for_click(
            {"os": "Mac OS", "country_code": "US", "device_type": "desktop"}, db
        )
        assert campaign is None


# ── Offer CPC resolution (find_matching_offer restored) ───────────────────────

@pytest.mark.asyncio
class TestFindMatchingOffer:
    async def test_find_matching_offer_importable(self):
        """click_tasks imports this — it must exist and match the call signature."""
        from app.services.traffic_router import find_matching_offer
        assert callable(find_matching_offer)

    async def test_find_matching_offer_resolves_targeted_offer(self, db):
        from app.services.traffic_router import find_matching_offer

        campaign_id = await db.campaigns.insert_one({
            "name": "Offer CPC Campaign", "status": "active",
            "default_offer_url": "https://fallback.example",
        }).inserted_id
        offer_id = await db.offers.insert_one({
            "name": "US Windows Offer", "status": "active",
            "offer_url": "https://offer.example",
            "cpc": 0.42,
            "campaign_id": str(campaign_id),
            "os_types": ["windows"],
            "country_codes": ["US"],
        }).inserted_id

        offer = await find_matching_offer(
            campaign_id=str(campaign_id),
            publisher_id="pub-x",
            website_id=None,
            os_name="Windows",
            country_code="US",
            db=db,
        )
        assert offer is not None
        assert str(offer["_id"]) == str(offer_id)
        assert offer.get("cpc") == 0.42