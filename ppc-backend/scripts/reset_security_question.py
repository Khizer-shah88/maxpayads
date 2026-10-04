"""
Reset security question for admin account.
This will remove the existing security question and answer, allowing you to set a new one.

Run: python scripts/reset_security_question.py
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings


async def reset_security_question():
    """Remove security question and answer from admin account."""
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.DB_NAME]

    try:
        # Find the admin account
        admin = await db.publishers.find_one({"role": "admin"})
        if not admin:
            print("❌ No admin account found in database!")
            return

        print(f"📧 Found admin account: {admin['email']}")
        
        # Check current security question
        current_question = admin.get("security_question")
        has_answer = bool(admin.get("security_answer_hash"))
        
        if current_question:
            print(f"Current question: {current_question}")
        if has_answer:
            print("Has security answer: YES")
        
        # Ask for confirmation
        print("\n⚠️  This will REMOVE the existing security question and answer.")
        print("After this, you can run auto_setup_security_question.py to set a new one.\n")
        
        confirm = input("Continue? (yes/no): ").strip().lower()
        if confirm != "yes":
            print("Aborted.")
            return

        # Remove security question fields
        result = await db.publishers.update_one(
            {"_id": admin["_id"]},
            {
                "$unset": {
                    "security_question": "",
                    "security_answer_hash": ""
                },
                "$set": {
                    "updated_at": datetime.utcnow()
                }
            }
        )

        if result.modified_count > 0:
            print("\n✅ Security question removed successfully!")
            print(f"   Admin: {admin['email']}")
            print("\nNext steps:")
            print("1. Make sure ADMIN_SECURITY_ANSWER is set in your .env file")
            print("2. Run: python scripts/auto_setup_security_question.py")
        else:
            print("⚠️  No changes made (security question may already be removed)")

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(reset_security_question())
