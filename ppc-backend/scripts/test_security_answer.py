"""
Test if a security answer matches the stored hash.
Run: python scripts/test_security_answer.py
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.core.security import verify_password


async def test_security_answer():
    """Test if the provided answer matches the stored hash."""
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.DB_NAME]

    try:
        # Find the admin account
        admin = await db.publishers.find_one({"role": "admin"})
        if not admin:
            print("❌ No admin account found in database!")
            return

        print(f"📧 Admin account: {admin['email']}")
        print(f"❓ Security question: {admin.get('security_question', 'NOT SET')}")
        
        security_answer_hash = admin.get("security_answer_hash")
        if not security_answer_hash:
            print("❌ No security answer hash found in database!")
            return
        
        print("\n🔒 Security answer hash exists in database")
        print(f"   Hash preview: {security_answer_hash[:20]}...")
        
        # Get answer from environment
        env_answer = os.getenv("ADMIN_SECURITY_ANSWER", "").strip()
        if env_answer:
            print(f"\n📝 Testing answer from ADMIN_SECURITY_ANSWER environment variable")
            print(f"   Original: '{env_answer}'")
            print(f"   Length: {len(env_answer)}")
            
            # Normalize like the backend does
            normalized = env_answer.strip().lower()
            print(f"   Normalized: '{normalized}'")
            print(f"   Normalized length: {len(normalized)}")
            
            # Test the hash
            if verify_password(normalized, security_answer_hash):
                print("\n✅ SUCCESS! The answer from environment matches the stored hash!")
                print("   You should be able to change password with this answer.")
            else:
                print("\n❌ FAIL! The answer from environment does NOT match the stored hash!")
                print("   Possible issues:")
                print("   1. The hash was created with a different answer")
                print("   2. There might be hidden characters in the environment variable")
                print("\n   To fix:")
                print("   1. Run: docker exec -it ppc_fastapi python scripts/reset_security_question.py")
                print("   2. Then: docker exec ppc_fastapi python scripts/auto_setup_security_question.py")
        else:
            print("\n⚠️  ADMIN_SECURITY_ANSWER not set in environment")
        
        # Interactive test
        print("\n" + "="*60)
        print("INTERACTIVE TEST")
        print("="*60)
        test_answer = input("Enter the security answer to test: ").strip()
        
        if not test_answer:
            print("No answer provided, skipping interactive test.")
            return
        
        normalized_test = test_answer.strip().lower()
        print(f"\nTesting answer: '{test_answer}'")
        print(f"Normalized: '{normalized_test}'")
        
        if verify_password(normalized_test, security_answer_hash):
            print("\n✅ SUCCESS! This answer is CORRECT!")
        else:
            print("\n❌ FAIL! This answer is INCORRECT!")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(test_security_answer())
