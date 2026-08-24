"""
Seed admin user into the database.
Run: python scripts/seed_admin.py
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.core.security import hash_password


async def seed_admin():
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.DB_NAME]

    existing = await db.publishers.find_one({"email": settings.ADMIN_EMAIL})
    if existing:
        print(f"Admin already exists: {settings.ADMIN_EMAIL}")
        client.close()
        return

    admin = {
        "_id": "admin_001",
        "name": settings.ADMIN_NAME,
        "email": settings.ADMIN_EMAIL,
        "password_hash": hash_password(settings.ADMIN_PASSWORD),
        "role": "admin",
        "status": "active",
        "revenue_share": 0.0,
        "balance": 0.0,
        "total_earnings": 0.0,
        "total_clicks": 0,
        "valid_clicks": 0,
        "invalid_clicks": 0,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    await db.publishers.insert_one(admin)
    print(f"Admin created successfully!")
    print(f"Email: {settings.ADMIN_EMAIL}")
    print(f"Password: {settings.ADMIN_PASSWORD}")
    client.close()


if __name__ == "__main__":
    asyncio.run(seed_admin())
