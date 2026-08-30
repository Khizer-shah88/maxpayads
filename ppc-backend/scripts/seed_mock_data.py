"""
seed_mock_data.py — Insert realistic mock data for UI/dashboard testing.

Usage:
    cd ppc-backend
    python scripts/seed_mock_data.py

What it seeds:
  - 3 publishers (active)
  - 2 campaigns
  - 2 offers
  - 2 landing pages
  - 2 prelander templates
  - 500 clicks spread over the last 30 days (valid + invalid)
  - 50 fraud logs
  - 2 direct links + 80 conversion events over 14 days
  - 3 withdrawals

Safe to run multiple times — checks for existing seed marker before inserting.
"""
import asyncio
import random
import secrets
import string
from datetime import datetime, timedelta

from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "ppc_network"

COUNTRIES = ["US", "GB", "CA", "AU", "DE", "FR", "NL", "SE", "NO", "CH", "IN", "BR", "MX"]
DEVICES = ["desktop", "mobile", "tablet"]
OS_LIST = ["Windows", "macOS", "iOS", "Android", "Linux"]
BROWSERS = ["Chrome", "Safari", "Firefox", "Edge", "Opera"]
FRAUD_REASONS = ["bot_user_agent", "datacenter_ip", "rate_limit_exceeded", "duplicate_ip"]

B62 = string.ascii_letters + string.digits


def rdate(days_back: int) -> datetime:
    offset = random.uniform(0, days_back * 86400)
    return datetime.utcnow() - timedelta(seconds=offset)


def slug(n: int = 8) -> str:
    return "".join(secrets.choice(B62) for _ in range(n))


async def main():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    # Guard — don't re-seed
    if await db.system_settings.find_one({"key": "_mock_seed_done"}):
        print("Mock data already seeded — skipping.")
        client.close()
        return

    print("Seeding mock data …")

    # ── Publishers ────────────────────────────────────────────────────────────
    from passlib.context import CryptContext
    pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

    pub_ids = []
    for i in range(1, 4):
        r = await db.publishers.insert_one({
            "name": f"Mock Publisher {i}",
            "email": f"mock{i}@example.com",
            "password_hash": pwd.hash("Password123"),
            "role": "publisher",
            "status": "active",
            "balance": round(random.uniform(10, 500), 2),
            "total_earnings": round(random.uniform(100, 2000), 4),
            "total_clicks": random.randint(200, 2000),
            "valid_clicks": random.randint(100, 1500),
            "invalid_clicks": random.randint(20, 200),
            "revenue_share": 0.80,
            "created_at": rdate(90),
            "updated_at": datetime.utcnow(),
        })
        pub_ids.append(str(r.inserted_id))
    print(f"  Publishers: {len(pub_ids)}")

    # ── Websites ──────────────────────────────────────────────────────────────
    site_ids = []
    for pid in pub_ids:
        r = await db.websites.insert_one({
            "publisher_id": pid,
            "domain": f"mock-site-{pid[-4:]}.com",
            "name": f"Mock Site {pid[-4:]}",
            "status": "active",
            "total_clicks": random.randint(100, 800),
            "valid_clicks": random.randint(50, 600),
            "invalid_clicks": random.randint(10, 100),
            "total_earnings": round(random.uniform(20, 400), 4),
            "created_at": rdate(80),
            "updated_at": datetime.utcnow(),
        })
        site_ids.append(str(r.inserted_id))

    # ── Campaigns ─────────────────────────────────────────────────────────────
    camp_ids = []
    for name in ["Windows Traffic", "Mac Traffic"]:
        r = await db.campaigns.insert_one({
            "name": name,
            "status": "active",
            "default_offer_url": "https://example.com/offer",
            "device_os": "windows" if "Windows" in name else "mac",
            "direct_redirect_mode": False,
            "referrer_suppression": True,
            "rotation_weight": 100,
            "created_at": rdate(60),
            "updated_at": datetime.utcnow(),
        })
        camp_ids.append(str(r.inserted_id))
    print(f"  Campaigns: {len(camp_ids)}")

    # ── Offers ────────────────────────────────────────────────────────────────
    offer_ids = []
    for i, cid in enumerate(camp_ids):
        r = await db.offers.insert_one({
            "name": f"Mock Offer {i+1}",
            "offer_url": f"https://offer-network.com/track/{slug(6)}",
            "password": "",
            "status": "active",
            "payout": round(random.uniform(0.05, 0.25), 3),
            "campaign_id": cid,
            "publisher_ids": [],
            "os_types": [],
            "country_codes": [],
            "direct_redirect_mode": False,
            "created_at": rdate(55),
            "updated_at": datetime.utcnow(),
        })
        offer_ids.append(str(r.inserted_id))

    # ── Prelander Templates ───────────────────────────────────────────────────
    tpl_ids = []
    for os_t, name in [("windows", "Windows Download Template"), ("mac", "Mac Terminal Template")]:
        r = await db.prelander_templates.insert_one({
            "name": name,
            "description": f"Default {os_t} prelander design",
            "os_type": os_t,
            "status": "active",
            "title": "Your file is ready to download",
            "subtitle": "Copy the link below and follow the steps.",
            "button_text": "Copy Link",
            "show_password_field": True,
            "show_video": False,
            "video_url": None,
            "tags": ["mock", os_t],
            "notes": "Seeded by seed_mock_data.py",
            "created_at": rdate(45),
            "updated_at": datetime.utcnow(),
        })
        tpl_ids.append(str(r.inserted_id))
    print(f"  Prelander Templates: {len(tpl_ids)}")

    # ── Landing Pages ─────────────────────────────────────────────────────────
    for i, cid in enumerate(camp_ids):
        await db.landing_pages.insert_one({
            "name": f"Mock Landing Page {i+1}",
            "lander_url": f"https://mock-lander{i+1}.com",
            "campaign_id": cid,
            "prelander_template_id": tpl_ids[i] if i < len(tpl_ids) else None,
            "status": "active",
            "weight": 50,
            "created_at": rdate(40),
            "updated_at": datetime.utcnow(),
        })

    # ── Direct Links ──────────────────────────────────────────────────────────
    link_ids = []
    for i, pid in enumerate(pub_ids[:2]):
        lslug = slug(8)
        r = await db.direct_links.insert_one({
            "name": f"Mock Direct Link {i+1}",
            "publisher_id": pid,
            "campaign_id": camp_ids[i % len(camp_ids)],
            "masked_domain": f"mock-domain{i+1}.com",
            "slug": lslug,
            "destination_url": f"https://offer-network.com/direct/{slug(6)}",
            "prelander_template_id": tpl_ids[i % len(tpl_ids)],
            "status": "active",
            "notes": "Seeded",
            "daily_conversion_cap": 0,
            "total_clicks": 0,
            "total_conversions": 0,
            "created_at": rdate(30),
            "updated_at": datetime.utcnow(),
        })
        link_ids.append((str(r.inserted_id), lslug, pid))

    # ── Direct Link Events (conversions) ──────────────────────────────────────
    ev_docs = []
    for lid, lslug, pid in link_ids:
        for _ in range(40):
            ev_docs.append({
                "link_id": lid,
                "publisher_id": pid,
                "slug": lslug,
                "ip_address": f"{random.randint(1,254)}.{random.randint(1,254)}.{random.randint(1,254)}.{random.randint(1,254)}",
                "user_agent": "Mozilla/5.0 (Mock)",
                "referrer": "",
                "metadata": {},
                "created_at": rdate(14),
            })
    if ev_docs:
        await db.direct_link_events.insert_many(ev_docs)
        # Update counters
        for lid, _, _ in link_ids:
            cnt = sum(1 for e in ev_docs if e["link_id"] == lid)
            await db.direct_links.update_one(
                {"_id": __import__("bson").ObjectId(lid)},
                {"$set": {"total_clicks": cnt, "total_conversions": cnt}},
            )
    print(f"  Direct Links: {len(link_ids)} | Events: {len(ev_docs)}")

    # ── Clicks ────────────────────────────────────────────────────────────────
    click_docs = []
    for _ in range(500):
        pid = random.choice(pub_ids)
        sid = random.choice(site_ids)
        cid = random.choice(camp_ids)
        is_valid = random.random() > 0.25
        cpc = round(random.uniform(0.03, 0.15), 6)
        earnings = round(cpc * 0.80, 6) if is_valid else 0.0
        fraud_r = None if is_valid else random.choice(FRAUD_REASONS)
        click_docs.append({
            "publisher_id": pid,
            "website_id": sid,
            "campaign_id": cid,
            "ip_address": f"{random.randint(1,254)}.{random.randint(1,254)}.{random.randint(1,254)}.{random.randint(1,254)}",
            "country_code": random.choice(COUNTRIES),
            "country_name": "Mock Country",
            "device_type": random.choice(DEVICES),
            "os": random.choice(OS_LIST),
            "browser": random.choice(BROWSERS),
            "user_agent": "Mozilla/5.0 (Mock Agent)",
            "referrer": "https://mock-publisher.com/page",
            "destination_url": "https://example.com/offer",
            "status": "valid" if is_valid else "invalid",
            "is_valid": is_valid,
            "fraud_reason": fraud_r,
            "fraud_score": 0.0 if is_valid else round(random.uniform(0.65, 1.0), 3),
            "cpc": cpc if is_valid else 0.0,
            "earnings": earnings,
            "processed": True,
            "timestamp": rdate(30),
            "processed_at": datetime.utcnow(),
        })
    await db.clicks.insert_many(click_docs)
    print(f"  Clicks: {len(click_docs)}")

    # ── Fraud Logs ────────────────────────────────────────────────────────────
    fraud_docs = []
    invalid_clicks = [c for c in click_docs if not c["is_valid"]]
    for c in random.sample(invalid_clicks, min(50, len(invalid_clicks))):
        fraud_docs.append({
            "click_id": "mock",
            "publisher_id": c["publisher_id"],
            "ip_address": c["ip_address"],
            "country_code": c["country_code"],
            "device_type": c["device_type"],
            "user_agent": c["user_agent"],
            "fraud_reason": c["fraud_reason"],
            "fraud_score": c["fraud_score"],
            "details": {},
            "detected_at": c["timestamp"],
        })
    if fraud_docs:
        await db.fraud_logs.insert_many(fraud_docs)
    print(f"  Fraud Logs: {len(fraud_docs)}")

    # ── Withdrawals ───────────────────────────────────────────────────────────
    for pid in pub_ids:
        await db.withdrawals.insert_one({
            "publisher_id": pid,
            "publisher_name": "Mock Publisher",
            "amount": round(random.uniform(10, 100), 2),
            "payment_method": random.choice(["paypal", "usdt", "bank_transfer"]),
            "payment_details": "mock@paypal.com",
            "status": random.choice(["pending", "paid", "approved"]),
            "balance_deducted": True,
            "transaction_id": None,
            "admin_note": None,
            "requested_at": rdate(20),
            "processed_at": None,
        })
    print("  Withdrawals: 3")

    # ── Mark seed done ────────────────────────────────────────────────────────
    await db.system_settings.update_one(
        {"key": "_mock_seed_done"},
        {"$set": {"key": "_mock_seed_done", "value": True, "seeded_at": datetime.utcnow()}},
        upsert=True,
    )

    print("\nDone! Mock data inserted successfully.")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
