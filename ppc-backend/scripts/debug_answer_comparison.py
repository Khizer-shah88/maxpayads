"""
Debug security answer comparison to find why it's failing.
Run: python scripts/debug_answer_comparison.py
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.core.security import verify_password


async def debug_answer():
    """Debug the security answer comparison."""
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.DB_NAME]

    try:
        # Find the admin account
        admin = await db.publishers.find_one({"role": "admin"})
        if not admin:
            print("❌ No admin account found!")
            return

        print("="*70)
        print("SECURITY ANSWER DEBUG")
        print("="*70)
        print(f"\n📧 Admin: {admin['email']}")
        print(f"❓ Question: {admin.get('security_question', 'NOT SET')}")
        
        security_answer_hash = admin.get("security_answer_hash")
        if not security_answer_hash:
            print("❌ No security answer hash in database!")
            return
        
        print(f"\n🔒 Hash in DB: {security_answer_hash[:30]}...")
        
        # Get answer from environment
        env_answer = os.getenv("ADMIN_SECURITY_ANSWER", "").strip()
        print(f"\n📝 Environment Variable Analysis:")
        print(f"   Raw value: '{env_answer}'")
        print(f"   Length: {len(env_answer)} characters")
        print(f"   Has leading space: {env_answer != env_answer.lstrip()}")
        print(f"   Has trailing space: {env_answer != env_answer.rstrip()}")
        print(f"   Repr: {repr(env_answer)}")
        
        # Test with different normalizations
        print(f"\n🧪 Testing Different Normalizations:")
        
        test_cases = [
            ("Raw (no normalization)", env_answer),
            ("strip()", env_answer.strip()),
            ("lower()", env_answer.lower()),
            ("strip().lower()", env_answer.strip().lower()),
            ("lower().strip()", env_answer.lower().strip()),
        ]
        
        for name, test_val in test_cases:
            result = verify_password(test_val, security_answer_hash)
            status = "✅ MATCH" if result else "❌ NO MATCH"
            print(f"   {status} | {name:25} | '{test_val}' (len={len(test_val)})")
        
        # Ask user to test their input
        print(f"\n" + "="*70)
        print("INTERACTIVE TEST - Test what you're typing in the browser")
        print("="*70)
        user_input = input("\nEnter EXACTLY what you type in the browser: ")
        
        print(f"\n📝 Your Input Analysis:")
        print(f"   Raw: '{user_input}'")
        print(f"   Length: {len(user_input)}")
        print(f"   Repr: {repr(user_input)}")
        
        # Test user input with same normalizations
        print(f"\n🧪 Testing Your Input:")
        
        user_test_cases = [
            ("Raw", user_input),
            ("strip()", user_input.strip()),
            ("lower()", user_input.lower()),
            ("strip().lower()", user_input.strip().lower()),
        ]
        
        for name, test_val in user_test_cases:
            result = verify_password(test_val, security_answer_hash)
            status = "✅ MATCH" if result else "❌ NO MATCH"
            print(f"   {status} | {name:15} | '{test_val}'")
        
        # Show what SHOULD work
        print(f"\n" + "="*70)
        print("EXPECTED BEHAVIOR")
        print("="*70)
        print(f"Backend normalizes like this: your_input.strip().lower()")
        print(f"So you should type: '{env_answer}' (case doesn't matter)")
        print(f"Which becomes: '{env_answer.strip().lower()}' after normalization")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(debug_answer())
