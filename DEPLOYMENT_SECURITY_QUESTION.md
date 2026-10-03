# Deployment Guide: Admin Security Question Feature

## Quick Summary

This deployment adds a security question requirement for admin password changes. After deployment, the admin will need to provide BOTH their current password AND the security question answer to change their password.

## 🚨 Important: Initial Setup Required

After deploying the code, you MUST run the setup script to configure the security question for your admin account. Without this, the change password feature will not work.

## Deployment Steps

### Step 1: Pull Latest Code on Server

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

## Testing the Feature

### 1. Access Change Password Page
Go to: https://vertexmonetize.com/admin/change-password

### 2. Verify UI Changes
You should see:
- ✅ Security notice box (blue background)
- ✅ Current password field
- ✅ Security question displayed in gray box
- ✅ Security answer input field (with show/hide toggle)
- ✅ New password field
- ✅ Confirm new password field

### 3. Test Security Validation

**Test 1: Wrong security answer**
- Current password: (correct)
- Security answer: (wrong answer)
- New password: test12345
- Expected: ❌ Error "Current password or security answer is incorrect"

**Test 2: Wrong current password**
- Current password: (wrong)
- Security answer: (correct answer)
- New password: test12345
- Expected: ❌ Error "Current password or security answer is incorrect"

**Test 3: Correct credentials**
- Current password: (correct)
- Security answer: (correct answer)
- New password: test12345
- Confirm: test12345
- Expected: ✅ Success "Password changed successfully"

**Test 4: Login with new password**
- Logout
- Login with new password
- Expected: ✅ Successful login

## Troubleshooting

### Issue: "Security question not configured for this account"

**Solution:**
```bash
cd /root/ppc-system/maxpayads/ppc-backend
python scripts/add_admin_security_question.py
```

### Issue: Page doesn't load security question

**Check:**
1. Backend is running: `pm2 status`
2. Backend logs: `pm2 logs ppc-backend --lines 50`
3. Security question exists in database:
```bash
mongosh
use ppc_system
db.publishers.findOne({role: "admin"}, {security_question: 1, security_answer_hash: 1})
```

### Issue: Can't remember security answer

**Recovery (requires database access):**
```bash
cd /root/ppc-system/maxpayads/ppc-backend
python scripts/add_admin_security_question.py
# Choose "yes" to update existing question
```

### Issue: Backend not restarting

**Force restart:**
```bash
pm2 delete ppc-backend
pm2 start ecosystem.config.js --only ppc-backend
```

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
