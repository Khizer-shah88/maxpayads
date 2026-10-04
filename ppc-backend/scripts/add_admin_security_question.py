"""
Add security question to existing admin account.
Run: python scripts/add_admin_security_question.py

This script adds a security question and answer to the admin account.
The answer is hashed and never stored in plain text.
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.core.security import hash_password


async def add_security_question():
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.DB_NAME]

    # Find the admin account
    admin = await db.publishers.find_one({"role": "admin"})
    if not admin:
        print("❌ No admin account found!")
        client.close()
        return

    # Check if security question already exists
    if admin.get("security_answer_hash"):
        print(f"⚠️  Security question already configured for: {admin['email']}")
        update_choice = input("Do you want to update it? (yes/no): ").strip().lower()
        if update_choice != "yes":
            print("Aborted.")
            client.close()
            return

    print(f"📧 Found admin account: {admin['email']}")
    print("\n" + "="*60)
    print("SECURITY QUESTION SETUP")
    print("="*60)
    print("\nThe security question adds an extra layer of security when")
    print("changing the admin password. The answer will be hashed and")
    print("stored securely (never in plain text).\n")

    # Default security question from config
    default_question = settings.ADMIN_SECURITY_QUESTION
    print(f"Default question: {default_question}")
    custom = input("\nUse custom question? (yes/no, default=no): ").strip().lower()
    
    if custom == "yes":
        security_question = input("Enter your security question: ").strip()
        if not security_question:
            print("❌ Question cannot be empty!")
            client.close()
            return
    else:
        security_question = default_question

    # Get the answer
    print(f"\nQuestion: {security_question}")
    security_answer = input("Enter the answer: ").strip()
    
    if not security_answer:
        print("❌ Answer cannot be empty!")
        client.close()
        return

    # Confirm the answer
    security_answer_confirm = input("Confirm the answer: ").strip()
    
    if security_answer != security_answer_confirm:
        print("❌ Answers do not match!")
        client.close()
        return

    # Normalize and hash the answer (lowercase for case-insensitive comparison)
    normalized_answer = security_answer.strip().lower()
    answer_hash = hash_password(normalized_answer)

    # Update the admin account
    result = await db.publishers.update_one(
        {"_id": admin["_id"]},
        {
            "$set": {
                "security_question": security_question,
                "security_answer_hash": answer_hash,
                "updated_at": datetime.utcnow()
            }
        }
    )

    if result.modified_count > 0:
        print("\n✅ Security question configured successfully!")
        print(f"📧 Admin: {admin['email']}")
        print(f"❓ Question: {security_question}")
        print("🔒 Answer: [SECURELY HASHED]")
        print("\n⚠️  IMPORTANT: Remember your answer! It will be required")
        print("   when changing the admin password.")
    else:
        print("❌ Failed to update admin account")

    client.close()


if __name__ == "__main__":
    asyncio.run(add_security_question())
