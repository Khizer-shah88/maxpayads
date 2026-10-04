# Security Question Change Guide

## Problem
The database still has the old security question ("What is your Father's name?" / "Talib"), but you want to use the new one ("What is your Cat's name?" / "Raven").

The auto-setup script **refuses to update** if a question already exists in the database. This is by design to prevent accidental changes.

## Solution - Follow These Steps EXACTLY

### Step 1: Update Environment Variables (ALREADY DONE ✓)
Your `.env` file should have:
```bash
ADMIN_SECURITY_QUESTION="What is your Cat's name?"
ADMIN_SECURITY_ANSWER="Raven"
```

### Step 2: Code Update (DONE ✓)
The default in `app/config.py` has been updated to:
```python
ADMIN_SECURITY_QUESTION: str = "What is your Cat's name?"
```

### Step 3: Deploy the Code
```bash
git add .
git commit -m "Update security question to Cat's name"
git push
```

Wait for CI/CD to deploy.

### Step 4: Reset the Old Question (CRITICAL - YOU MUST DO THIS)
SSH to your server and run:
```bash
docker exec -it ppc_fastapi python scripts/reset_security_question.py
```

When prompted "Continue? (yes/no):", type `yes`

This will:
- Remove the old question from the database
- Remove the old answer hash from the database

### Step 5: Install the New Question
```bash
docker exec ppc_fastapi python scripts/auto_setup_security_question.py
```

This will read from your environment variables and install the new question.

### Step 6: Verify Installation
```bash
docker exec ppc_fastapi python scripts/test_security_answer.py
```

Expected output:
```
📧 Admin account: admin@maxpayads.com
❓ Security question: What is your Cat's name?
🔒 Security answer hash exists in database
   Hash preview: $2b$12$...
📝 Testing answer from ADMIN_SECURITY_ANSWER environment variable
   Original: 'Raven'
   Normalized: 'raven'
✅ SUCCESS! The answer from environment matches the stored hash!
```

### Step 7: Test Interactive Answer
When the script prompts "Enter the security answer to test:", type `Raven`

Expected output:
```
Testing answer: 'Raven'
Normalized: 'raven'
✅ SUCCESS! This answer is CORRECT!
```

### Step 8: Test Password Change
Go to https://vertexmonetize.com/admin/change-password

Fill in:
- Current Password: (your current admin password)
- Security Question Answer: `Raven` (case doesn't matter)
- New Password: (your new password)
- Confirm Password: (same as new password)

Click "Change Password" - it should succeed!

## Why This Happens

The `auto_setup_security_question.py` script has this logic:

```python
if existing_hash:
    print("✓ Admin account already has security question configured")
    print("  Skipping update (already configured).")
```

This is a **safety feature** to prevent accidental overwrites during deployment. To change the question, you MUST:

1. Run `reset_security_question.py` to clear the old one
2. Then run `auto_setup_security_question.py` to install the new one

## Common Mistakes

❌ **Running auto-setup without reset first**
- Result: Old question stays, new question ignored

❌ **Not updating environment variables**
- Result: Auto-setup uses the wrong answer

❌ **Typing "yes" in the browser instead of "Raven"**
- Result: Wrong answer, password change fails

❌ **Not deploying code after updating config.py**
- Result: Server still has old default question

## Verification Commands

Check environment variables:
```bash
docker exec ppc_fastapi printenv | grep ADMIN_SECURITY
```

Should show:
```
ADMIN_SECURITY_QUESTION=What is your Cat's name?
ADMIN_SECURITY_ANSWER=Raven
```

Check database:
```bash
docker exec ppc_fastapi python scripts/test_security_answer.py
```

Should show the new question and answer working.

## Current Status

✅ Code updated with new default question
✅ Environment variables set (confirmed by user)
⏳ Need to run reset script
⏳ Need to run auto-setup script
⏳ Need to test password change

## Next Actions for You

```bash
# SSH to your server
ssh deploy@vps3511370.uk-lon-dc.vps.ovh.ca

# Navigate to project
cd ~/maxpayads/fahad

# Reset old question (REQUIRED)
docker exec -it ppc_fastapi python scripts/reset_security_question.py
# Type "yes" when prompted

# Install new question
docker exec ppc_fastapi python scripts/auto_setup_security_question.py

# Verify it worked
docker exec ppc_fastapi python scripts/test_security_answer.py
# When prompted, type: Raven
```

After these steps, password change should work with "Raven" as the answer.
