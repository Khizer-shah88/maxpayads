"""
Automatic Security Question Setup for CI/CD Deployment

This script runs automatically during deployment to ensure the admin account
has a security question configured. It reads the question and answer from
environment variables.

Required Environment Variables:
- ADMIN_SECURITY_QUESTION: The security question text (optional, uses default if not set)
- ADMIN_SECURITY_ANSWER: The answer to the security question (REQUIRED)

Example:
export ADMIN_SECURITY_QUESTION="What is your mother's maiden name?"
export ADMIN_SECURITY_ANSWER="Smith"
python scripts/auto_setup_security_question.py
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.core.security import hash_password


async def auto_setup_security_question():
    """
    Automatically configure security question for admin account.
    Safe to run multiple times - will only update if answer changed.
    """
    # Get security question and answer from environment
    security_question = os.getenv(
        "ADMIN_SECURITY_QUESTION", 
        settings.ADMIN_SECURITY_QUESTION
    )
    security_answer = os.getenv("ADMIN_SECURITY_ANSWER", settings.ADMIN_SECURITY_ANSWER).strip()

    if not security_answer:
        print("⚠️  ADMIN_SECURITY_ANSWER environment variable not set!")
        print("   Security question will NOT be configured.")
        print("   Password changes will fail until you set up the security question.")
        print("\n   To fix this:")
        print("   1. Add ADMIN_SECURITY_ANSWER to your .env file")
        print("   2. Or run: python scripts/add_admin_security_question.py")
        return

    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.DB_NAME]

    try:
        # Find the admin account
        admin = await db.publishers.find_one({"role": "admin"})
        if not admin:
            print("⚠️  No admin account found in database!")
            print("   Run seed_admin.py first to create the admin account.")
            return

        # Check if security question already configured
        existing_hash = admin.get("security_answer_hash")
        
        # Normalize answer (lowercase, trimmed)
        normalized_answer = security_answer.lower()
        new_hash = hash_password(normalized_answer)

        if existing_hash:
            print(f"✓ Admin account already has security question configured: {admin['email']}")
            print(f"  Question: {admin.get('security_question', security_question)}")
            # Note: We don't update if already exists to avoid accidental changes
            print("  Skipping update (already configured).")
        else:
            # Configure security question
            result = await db.publishers.update_one(
                {"_id": admin["_id"]},
                {
                    "$set": {
                        "security_question": security_question,
                        "security_answer_hash": new_hash,
                        "updated_at": datetime.utcnow()
                    }
                }
            )

            if result.modified_count > 0:
                print("✅ Security question configured successfully!")
                print(f"   Admin: {admin['email']}")
                print(f"   Question: {security_question}")
                print("   Answer: [SECURELY HASHED]")
            else:
                print("⚠️  Failed to update admin account")

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(auto_setup_security_question())
