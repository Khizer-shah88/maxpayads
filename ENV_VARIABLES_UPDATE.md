# Environment Variables Update

## New Required Variables for Security Question Feature

### For Production Deployment

Add these variables to your `.env.production` file on the server:

**Location:** `/home/deploy/maxpayads/fahad/deployment/.env.production`

```bash
# ============================================================================
# Admin Security Question Configuration (Required)
# ============================================================================
# Security question shown when admin changes password
# Default: "What is your mother's maiden name?" (if not specified)
ADMIN_SECURITY_QUESTION="What is your mother's maiden name?"

# Answer to the security question
# REQUIRED: Password changes will fail without this
# The answer will be hashed and stored securely (never plain text)
ADMIN_SECURITY_ANSWER="YourAnswerHere"
```

### How to Add (Server)

```bash
# 1. SSH to your server
ssh root@143.198.67.132

# 2. Edit the production environment file
nano /home/deploy/maxpayads/fahad/deployment/.env.production

# 3. Add the two variables at the end of the file

# 4. Save (Ctrl+X, then Y, then Enter)

# 5. Deploy will automatically pick up the new variables
```

### For Local Development (Optional)

If you want to test the security question feature locally:

**Location:** `ppc-backend/.env`

```bash
# Add these lines
ADMIN_SECURITY_QUESTION="What is your mother's maiden name?"
ADMIN_SECURITY_ANSWER="TestAnswer"
```

Then run:
```bash
cd ppc-backend
python scripts/auto_setup_security_question.py
```

### Variable Details

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ADMIN_SECURITY_QUESTION` | No | "What is your mother's maiden name?" | The security question text shown to admin |
| `ADMIN_SECURITY_ANSWER` | **YES** | None | The answer (will be hashed with bcrypt) |

### Security Notes

✅ **Safe:**
- Answer is hashed with bcrypt before storage
- Never stored in plain text
- Never exposed in API responses
- Never logged

⚠️ **Important:**
- Store your answer securely (password manager recommended)
- Remember it - you'll need it to change admin password
- Case-insensitive (Answer and answer are both valid)
- Whitespace is automatically trimmed

### What Happens During Deployment

1. CI/CD workflow syncs code to server
2. Deployment script (`2-deploy.sh`) runs
3. Script executes: `python scripts/auto_setup_security_question.py`
4. Script reads `ADMIN_SECURITY_ANSWER` from environment
5. Script finds admin account in database
6. Script checks if security question already configured:
   - **If not configured:** Hashes answer and stores it → "✅ Security question configured successfully!"
   - **If already configured:** Skips update → "✓ Already configured, skipping"
7. Deployment continues normally

### Troubleshooting

**Q: I forgot to add the variable before deployment**

A: No problem! Add it to `.env.production` and push a new commit. Next deployment will configure it.

**Q: What if I don't add the variable?**

A: You'll see this warning in deployment logs:
```
⚠️  ADMIN_SECURITY_ANSWER environment variable not set!
   Security question will NOT be configured.
   Password changes will fail until you set up the security question.
```

Password changes will fail with: "Security question not configured for this account"

**Q: Can I change the security answer later?**

A: Yes, but you need database access:
```bash
# 1. Update ADMIN_SECURITY_ANSWER in .env.production
# 2. Remove existing hash from database
docker exec -it ppc_mongo mongosh ppc_network --eval \
  'db.publishers.updateOne({role:"admin"}, {$unset:{security_answer_hash:""}})'
# 3. Run setup script
cd /home/deploy/maxpayads/fahad/ppc-backend
source ../deployment/.env.production
python scripts/auto_setup_security_question.py
```

**Q: What if I deploy without setting this variable?**

A: Deployment will succeed, but:
- Change password page will show security question field
- Password changes will fail with "Security question not configured"
- You can fix it by adding the variable and redeploying

### Migration Path

This feature is **backward compatible**:

- **Existing deployments:** Will continue to work, but password change requires the variable
- **New deployments:** Should add the variable before first deployment
- **No database migration needed:** Fields are auto-populated when variable is set

### Example .env.production File

```bash
# MongoDB
MONGODB_URL=mongodb://ppc_mongo:27017

# Redis
REDIS_URL=redis://ppc_redis:6379

# Admin Account
ADMIN_EMAIL=admin@vertexmonetize.com
ADMIN_PASSWORD=YourSecurePassword123
ADMIN_NAME=Admin

# Admin Security Question (NEW - Add these)
ADMIN_SECURITY_QUESTION="What is your mother's maiden name?"
ADMIN_SECURITY_ANSWER="Smith"

# Other variables...
```

---

**Status:** Ready for Production
**Required:** YES (for password change functionality)
**Backward Compatible:** YES
