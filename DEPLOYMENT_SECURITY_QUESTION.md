# Deployment Guide: Admin Security Question Feature

## Quick Summary

This deployment adds a security question requirement for admin password changes. The security question is configured automatically during CI/CD deployment using environment variables.

## 🚀 For CI/CD Deployment (Automated)

### Step 1: Add Environment Variables to Your Server

The security question and answer are configured via environment variables in your `.env.production` file:

```bash
# SSH to your server
ssh root@143.198.67.132

# Edit your production environment file
nano /home/deploy/maxpayads/fahad/deployment/.env.production
```

**Add these two lines at the end:**

```bash
# Admin Security Question Configuration
ADMIN_SECURITY_QUESTION="What is your mother's maiden name?"
ADMIN_SECURITY_ANSWER="YourAnswerHere"
```

**⚠️ IMPORTANT:**
- Replace `YourAnswerHere` with your actual security answer
- The answer will be hashed and stored securely (never in plain text)
- This file is NOT in git (it's excluded for security)
- Keep your answer secure and remember it!

### Step 2: Push Code to Main Branch

The CI/CD workflow will automatically:
1. Pull the latest code
2. Run the security question setup script
3. Deploy the updated application

```bash
# On your local machine
git push origin main
```

The GitHub Actions workflow will:
- ✅ Sync files to server
- ✅ Run `python scripts/auto_setup_security_question.py`
- ✅ Build and restart containers
- ✅ Verify deployment

### Step 3: Verify Deployment

After CI/CD completes, check the deployment logs in GitHub Actions to confirm:

```
✅ Security question configured successfully!
   Admin: your-admin@email.com
   Question: What is your mother's maiden name?
   Answer: [SECURELY HASHED]
```

### Step 4: Test the Feature

Go to: https://vertexmonetize.com/admin/change-password

You should see:
- ✅ Security notice box (blue background)
- ✅ Security question displayed
- ✅ Security answer input field
- ✅ Password change requires both current password AND security answer

## 🔧 Manual Deployment (If Not Using CI/CD)

If you need to deploy manually:

```bash
ssh root@143.198.67.132
cd /root/ppc-system/maxpayads
git pull

# Option 1: Use environment variable (recommended)
export ADMIN_SECURITY_ANSWER="YourAnswerHere"
cd ppc-backend
python scripts/auto_setup_security_question.py

# Option 2: Interactive setup
cd ppc-backend
python scripts/add_admin_security_question.py
# Follow the prompts

# Restart services
cd ..
pm2 restart ppc-backend
cd ppc-frontend
npm run build
pm2 restart ppc-frontend
```

## 📋 Environment Variable Reference

Add these to `/home/deploy/maxpayads/fahad/deployment/.env.production`:

```bash
# ============================================================================
# Admin Security Question Configuration
# ============================================================================
# The security question shown when changing admin password
ADMIN_SECURITY_QUESTION="What is your mother's maiden name?"

# The answer to the security question (will be hashed, never stored as plain text)
# REQUIRED: Without this, password changes will fail
ADMIN_SECURITY_ANSWER="Smith"
```

**Alternative Questions You Can Use:**
- "What is your mother's maiden name?"
- "What city were you born in?"
- "What is your favorite color?"
- "What is the name of your first pet?"
- "What is your favorite food?"

## 🔍 How the Automation Works

1. **CI/CD Push** → GitHub Actions triggers
2. **File Sync** → Code synced to server
3. **Auto Setup** → `deployment/2-deploy.sh` runs:
   ```bash
   python scripts/auto_setup_security_question.py
   ```
4. **Script Checks**:
   - ✅ Reads `ADMIN_SECURITY_ANSWER` from environment
   - ✅ Finds admin account in database
   - ✅ Checks if security question already configured
   - ✅ If not configured: hashes answer and stores it
   - ✅ If already configured: skips update (safe)
5. **Containers Restart** → New code deployed

## 🧪 Testing After Deployment

```bash
ssh root@143.198.67.132
cd /root/ppc-system/maxpayads
git pull
```

### Step 2: Configure Security Question (REQUIRED)

This is a one-time setup. You'll be prompted to choose a security question and provide an answer.

```bash
cd ppc-backend
python scripts/add_admin_security_question.py
```

**Follow the interactive prompts:**
1. Choose to use default question or create a custom one
2. Enter your answer
3. Confirm your answer
4. ✅ Security question configured!

**⚠️ CRITICAL: Remember your answer! You'll need it to change your password.**

**Example:**
```
📧 Found admin account: admin@vertexmonetize.com

Default question: What is your mother's maiden name?
Use custom question? (yes/no, default=no): no

Question: What is your mother's maiden name?
Enter the answer: Smith
Confirm the answer: Smith

✅ Security question configured successfully!
```

### Step 3: Restart Backend

```bash
pm2 restart ppc-backend
```

### Step 4: Build and Restart Frontend

```bash
cd /root/ppc-system/maxpayads/ppc-frontend
npm run build
pm2 restart ppc-frontend
```

### Step 5: Verify Deployment

```bash
# Check backend is running
pm2 status

# Check logs for any errors
pm2 logs ppc-backend --lines 50
pm2 logs ppc-frontend --lines 50
```

## 🧪 Testing After Deployment

### Check Deployment Logs (GitHub Actions)

Go to your GitHub repository → Actions → Latest workflow run

Look for this in the deployment logs:
```
Checking admin security question configuration...
✅ Security question configured successfully!
   Admin: admin@example.com
   Question: What is your mother's maiden name?
   Answer: [SECURELY HASHED]
```

Or if already configured:
```
✓ Admin account already has security question configured: admin@example.com
  Question: What is your mother's maiden name?
  Skipping update (already configured).
```

### Test the Change Password Page

1. Go to: https://vertexmonetize.com/admin/change-password

2. **Verify UI:**
   - ✅ Security notice box (blue background with shield icon)
   - ✅ Current password field
   - ✅ Security question displayed in gray box
   - ✅ Security answer input field (with show/hide toggle)
   - ✅ New password field
   - ✅ Confirm new password field

3. **Test Wrong Answer:**
   - Current password: (correct)
   - Security answer: WrongAnswer
   - New password: test12345
   - Confirm: test12345
   - **Expected:** ❌ Error "Current password or security answer is incorrect"

4. **Test Correct Credentials:**
   - Current password: (correct)
   - Security answer: (correct - what you set in .env.production)
   - New password: test12345
   - Confirm: test12345
   - **Expected:** ✅ Success "Password changed successfully"

5. **Test New Password:**
   - Logout
   - Login with new password
   - **Expected:** ✅ Successful login

6. **Change Password Back:**
   - Go to change password page again
   - Use test12345 as current password
   - Provide security answer
   - Set back to your original password

## 🚨 Troubleshooting

### Issue 1: "Security question not configured for this account"

**Cause:** `ADMIN_SECURITY_ANSWER` not set in `.env.production`

**Solution:**
```bash
ssh root@143.198.67.132
nano /home/deploy/maxpayads/fahad/deployment/.env.production
# Add: ADMIN_SECURITY_ANSWER="YourAnswer"
# Save and exit

# Run setup manually
cd /home/deploy/maxpayads/fahad/ppc-backend
source /home/deploy/maxpayads/fahad/deployment/.env.production
python scripts/auto_setup_security_question.py
```

### Issue 2: CI/CD shows "ADMIN_SECURITY_ANSWER environment variable not set"

**Cause:** Variable missing from `.env.production` file on server

**Solution:**
1. SSH to server
2. Add variable to `/home/deploy/maxpayads/fahad/deployment/.env.production`
3. Push a new commit to trigger deployment again

### Issue 3: Password change fails even with correct answer

**Check:**
```bash
ssh root@143.198.67.132
cd /home/deploy/maxpayads/fahad

# Check if security question exists in database
docker exec -it ppc_mongo mongosh ppc_network --eval 'db.publishers.findOne({role: "admin"}, {security_question: 1, security_answer_hash: 1})'
```

**Expected output:**
```json
{
  "_id": "admin_001",
  "security_question": "What is your mother's maiden name?",
  "security_answer_hash": "$2b$12$..."
}
```

**If missing:** Run setup script manually

### Issue 4: Forgot security answer

**Recovery:**
```bash
ssh root@143.198.67.132
cd /home/deploy/maxpayads/fahad

# Update the answer in .env.production
nano deployment/.env.production
# Change ADMIN_SECURITY_ANSWER to new value

# Force reconfigure (remove existing hash first)
docker exec -it ppc_mongo mongosh ppc_network --eval 'db.publishers.updateOne({role: "admin"}, {$unset: {security_answer_hash: ""}})'

# Run setup
cd ppc-backend
source ../deployment/.env.production
python scripts/auto_setup_security_question.py
```

### Issue 5: Deployment script fails

**Check logs:**
```bash
# View CI/CD logs in GitHub Actions
# Or on server:
ssh root@143.198.67.132
cd /home/deploy/maxpayads/fahad
cat deployment-log.txt  # if exists
```

**Manual fix:**
```bash
cd /home/deploy/maxpayads/fahad/ppc-backend
export ADMIN_SECURITY_ANSWER="YourAnswer"
python scripts/auto_setup_security_question.py
```

## 🔐 Security Notes

### What's Protected
✅ Answer is hashed with bcrypt (same algorithm as passwords)
✅ Answer is normalized to lowercase (case-insensitive)
✅ Answer is never exposed in API responses
✅ Answer is never logged
✅ Generic error messages prevent enumeration
✅ Both password AND answer required to change password

### Environment Variable Security
⚠️ `.env.production` contains sensitive data:
- Stored on server only (not in git)
- Protected with `chmod 600` (owner read/write only)
- Only accessible by deploy user and root
- Never committed to version control

### Backup Your Answer
📝 Store your security answer securely:
- Password manager (recommended)
- Encrypted note
- Secure document

❌ Do NOT store in:
- Git repository
- Slack/email
- Plain text file
- Shared documents

## 📊 What Changed in This Deployment

### New Files
- `ppc-backend/scripts/auto_setup_security_question.py` - Auto setup for CI/CD
- `ppc-backend/scripts/add_admin_security_question.py` - Manual interactive setup
- `ADMIN_SECURITY_QUESTION_IMPLEMENTATION.md` - Technical documentation
- `DEPLOYMENT_SECURITY_QUESTION.md` - This deployment guide

### Modified Files
- `ppc-backend/app/models/publisher.py` - Added security question fields
- `ppc-backend/app/routers/admin_router.py` - Updated password change endpoint
- `ppc-frontend/app/admin/change-password/page.tsx` - Updated UI
- `ppc-frontend/lib/api.ts` - Updated API client
- `deployment/2-deploy.sh` - Added auto setup script execution

### Database Changes
- `publishers` collection: Added `security_question` and `security_answer_hash` fields
- Fields are optional in schema (backward compatible)
- No migration needed for existing data
- Auto-populated during deployment if `ADMIN_SECURITY_ANSWER` is set

## ✅ Deployment Checklist

Before pushing to production:

- [ ] Added `ADMIN_SECURITY_ANSWER` to `.env.production` on server
- [ ] (Optional) Added `ADMIN_SECURITY_QUESTION` to customize question
- [ ] Saved security answer in password manager
- [ ] Tested deployment in staging/dev first (if available)
- [ ] Verified CI/CD pipeline has server SSH access
- [ ] Backed up current admin password
- [ ] Verified MongoDB connection works

After deployment:

- [ ] Check GitHub Actions logs for security question setup success
- [ ] Access change password page - security question displays
- [ ] Test wrong answer - shows error
- [ ] Test correct answer - password changes successfully
- [ ] Test login with new password
- [ ] Document security answer location for team

## 🆘 Emergency Access

If locked out:

1. **Database Direct Access:**
```bash
ssh root@143.198.67.132
docker exec -it ppc_mongo mongosh ppc_network

# Remove security question requirement temporarily
db.publishers.updateOne(
  {role: "admin"},
  {$unset: {security_answer_hash: ""}}
)
```

2. **Reset Password:**
```bash
cd /home/deploy/maxpayads/fahad/ppc-backend
python scripts/seed_admin.py  # Will recreate admin if needed
```

3. **Reconfigure Security Question:**
```bash
export ADMIN_SECURITY_ANSWER="NewAnswer"
python scripts/auto_setup_security_question.py
```

## 📞 Support

For issues:
1. Check GitHub Actions logs
2. Check this troubleshooting section
3. Verify `.env.production` has `ADMIN_SECURITY_ANSWER`
4. Run setup script manually
5. Check backend logs: `docker logs ppc_fastapi`

---

**Ready for Deployment:** ✅
**CI/CD Compatible:** ✅
**Backward Compatible:** ✅
**Security Verified:** ✅

## Security Features Implemented

✅ **Answer Hashing**: Security answers are hashed using bcrypt (never stored in plain text)
✅ **Case Insensitive**: Answers are normalized to lowercase for user-friendliness
✅ **Generic Errors**: Error messages don't reveal which field is incorrect
✅ **Backend Validation**: All security checks performed server-side
✅ **No Answer Exposure**: Answer never exposed in API responses or logs
✅ **Rate Limiting**: Protected by existing authentication middleware

## What Changed

### Backend Files Modified:
- `ppc-backend/app/models/publisher.py` - Added security_question and security_answer_hash fields
- `ppc-backend/app/routers/admin_router.py` - Updated change password endpoint, added get security question endpoint
- `ppc-backend/scripts/add_admin_security_question.py` - New setup script

### Frontend Files Modified:
- `ppc-frontend/app/admin/change-password/page.tsx` - Added security question UI
- `ppc-frontend/lib/api.ts` - Updated API client

### Documentation:
- `ADMIN_SECURITY_QUESTION_IMPLEMENTATION.md` - Complete technical documentation

## API Changes

### New Endpoint
```
GET /api/admin/security-question
Response: { "success": true, "question": "What is your mother's maiden name?" }
```

### Modified Endpoint
```
POST /api/admin/change-password
Request Body: {
  "current_password": "current123",
  "security_answer": "smith",     ← NEW REQUIRED FIELD
  "new_password": "newpassword123"
}
```

## Rollback Plan

If you need to rollback:

```bash
cd /root/ppc-system/maxpayads
git log --oneline  # Find the commit before security question feature
git checkout <previous-commit-hash>
cd ppc-frontend
npm run build
pm2 restart ppc-backend ppc-frontend
```

## Support Checklist

Before reporting issues:

- [ ] Security question configured via setup script
- [ ] Backend restarted after code pull
- [ ] Frontend rebuilt after code pull
- [ ] Checked backend logs for errors
- [ ] Tested with correct security answer
- [ ] Browser cache cleared
- [ ] Database contains security_question and security_answer_hash fields

## Next Steps After Deployment

1. ✅ Test password change with new security question
2. ✅ Document your security answer securely (offline)
3. ✅ Test account recovery process
4. ✅ Consider enabling additional security features (2FA, rate limiting, etc.)

---

**Deployment Date**: 2026-10-04
**Feature**: Security Question for Admin Password Changes
**Status**: Ready for Production
