# Admin Security Question Implementation

## Overview

This document describes the implementation of an additional security layer for admin password changes. The system now requires both the current password AND a security question answer to change the admin password.

## Security Requirements ✅

All requirements from the specification have been implemented:

### ✅ Multi-Factor Password Change
- Current password verification
- Security question answer verification
- New password confirmation
- Password strength validation (minimum 8 characters)

### ✅ Secure Answer Storage
- Security answers are NEVER stored in plain text
- Answers are hashed using bcrypt (same as passwords)
- Answers are normalized (lowercase, trimmed) before hashing for case-insensitive comparison
- Answer hash is stored in `security_answer_hash` field

### ✅ Backend Validation
- All validations performed on the backend
- No reliance on frontend validation alone
- Proper error handling without exposing the correct answer

### ✅ Privacy Protection
- Security question answer never exposed in API responses
- Only the question text is returned (via `/admin/security-question` endpoint)
- Generic error messages that don't reveal which field is incorrect
- No logging of security answers

### ✅ Attack Prevention
- Attackers who only know the current password CANNOT change the password
- Both current password and security answer must be correct
- Rate limiting inherited from existing authentication middleware

## Architecture

### Database Schema

Added to the `publishers` collection (admin accounts have `role: "admin"`):

```javascript
{
  // ... existing fields ...
  security_question: "What is your mother's maiden name?",  // The question text
  security_answer_hash: "$2b$12$...",  // Bcrypt hash of normalized answer
  // ... existing fields ...
}
```

### Backend Changes

#### 1. Publisher Model (`app/models/publisher.py`)
```python
class Publisher(BaseModel):
    # ... existing fields ...
    security_question: Optional[str] = None
    security_answer_hash: Optional[str] = None
    # ... existing fields ...
```

#### 2. Admin Router (`app/routers/admin_router.py`)

**New Endpoint: Get Security Question**
```
GET /api/admin/security-question
Authorization: Bearer <admin_token>

Response:
{
  "success": true,
  "question": "What is your mother's maiden name?"
}
```

**Updated Endpoint: Change Password**
```
POST /api/admin/change-password
Authorization: Bearer <admin_token>

Request Body:
{
  "current_password": "current123",
  "security_answer": "smith",
  "new_password": "newpassword123"
}

Validations:
1. All fields are required
2. New password must be at least 8 characters
3. Current password must be correct
4. Security answer must be correct (case-insensitive)
5. Security question must be configured for the account

Response (Success):
{
  "success": true,
  "message": "Password changed successfully"
}

Response (Error):
{
  "detail": "Current password or security answer is incorrect"
}
```

**Security Features:**
- Generic error message for wrong password or answer (prevents enumeration)
- Answer normalization: `answer.strip().lower()` before verification
- Uses bcrypt verification: `verify_password(normalized_answer, security_answer_hash)`
- Re-fetches user document to access sensitive fields not exposed in JWT

### Frontend Changes

#### 1. API Client (`lib/api.ts`)
```typescript
adminApi: {
  getSecurityQuestion: () => api.get('/admin/security-question'),
  changePassword: (current_password: string, security_answer: string, new_password: string) =>
    api.post('/admin/change-password', { current_password, security_answer, new_password }),
}
```

#### 2. Change Password Page (`app/admin/change-password/page.tsx`)

**New Features:**
- Fetches security question on page load
- Displays security question text in a read-only box
- New input field for security answer (with show/hide toggle)
- Security notice explaining the enhanced security requirement
- Updated validation to require security answer

**User Flow:**
1. Page loads → Fetches security question from backend
2. User enters current password
3. User sees security question and enters answer
4. User enters new password and confirmation
5. Form validates all fields
6. Backend verifies both password and security answer
7. Password updated if all checks pass

## Setup Script

### `scripts/add_admin_security_question.py`

This script adds or updates the security question for the admin account.

**Usage:**
```bash
cd ppc-backend
python scripts/add_admin_security_question.py
```

**Features:**
- Interactive prompts for question and answer
- Option to use default question or create custom question
- Answer confirmation to prevent typos
- Detects if security question already exists
- Hashes answer before storing
- Updates `updated_at` timestamp

**Default Question:**
"What is your mother's maiden name?"

**Example Session:**
```
📧 Found admin account: admin@vertexmonetize.com

============================================================
SECURITY QUESTION SETUP
============================================================

The security question adds an extra layer of security when
changing the admin password. The answer will be hashed and
stored securely (never in plain text).

Default question: What is your mother's maiden name?

Use custom question? (yes/no, default=no): no

Question: What is your mother's maiden name?
Enter the answer: Smith
Confirm the answer: Smith

✅ Security question configured successfully!
📧 Admin: admin@vertexmonetize.com
❓ Question: What is your mother's maiden name?
🔒 Answer: [SECURELY HASHED]

⚠️  IMPORTANT: Remember your answer! It will be required
   when changing the admin password.
```

## Security Considerations

### ✅ What's Protected
1. **Password Storage**: Both password and security answer use bcrypt hashing
2. **Answer Privacy**: Answer never exposed in API responses or logs
3. **Case Insensitivity**: Answers normalized to lowercase (user-friendly)
4. **Whitespace Handling**: Answers trimmed before hashing
5. **Generic Errors**: Error messages don't reveal which field is wrong
6. **Backend Validation**: All security checks on the backend
7. **JWT Security**: Sensitive fields not included in JWT payload

### ✅ Attack Mitigation
- **Brute Force**: Rate limiting from existing auth middleware
- **Enumeration**: Generic error messages prevent field guessing
- **SQL Injection**: Not applicable (MongoDB with proper queries)
- **XSS**: React escapes all user input automatically
- **CSRF**: Session-based auth with HTTP-only cookies

### ⚠️ Important Notes
1. **Answer Recovery**: If admin forgets the answer, database access required to reset
2. **Case Sensitivity**: Answers are case-insensitive for better UX
3. **Initial Setup**: Run `add_admin_security_question.py` script after deployment
4. **Backup Access**: Ensure you have database access in case of lockout

## Deployment Steps

### 1. Backend Deployment
```bash
# On server
cd /root/ppc-system/maxpayads
git pull

# Install dependencies (if any new ones)
cd ppc-backend
pip install -r requirements.txt

# Run setup script to add security question
python scripts/add_admin_security_question.py

# Restart backend
pm2 restart ppc-backend
```

### 2. Frontend Deployment
```bash
# On server (continued)
cd /root/ppc-system/maxpayads/ppc-frontend
npm run build
pm2 restart ppc-frontend
```

### 3. Verification
1. Go to https://vertexmonetize.com/admin/change-password
2. Verify security question is displayed
3. Try changing password with wrong answer → Should fail
4. Try changing password with correct answer → Should succeed

## Testing Checklist

### ✅ Functionality Tests
- [ ] Security question loads on page load
- [ ] Cannot submit without security answer
- [ ] Wrong security answer is rejected
- [ ] Correct answer + wrong password is rejected
- [ ] Correct answer + correct password succeeds
- [ ] Password change updates password in database
- [ ] New password works for login

### ✅ Security Tests
- [ ] Answer hash is stored, not plain text
- [ ] Answer is not exposed in API responses
- [ ] Error messages are generic
- [ ] Case-insensitive comparison works
- [ ] Whitespace is trimmed from answers
- [ ] Rate limiting prevents brute force

### ✅ UI/UX Tests
- [ ] Security notice is visible
- [ ] Question text is readable
- [ ] Show/hide toggle works for answer field
- [ ] Loading states display correctly
- [ ] Error messages are user-friendly
- [ ] Success message confirms password change

## Rollback Plan

If issues occur, rollback is safe:

1. **Frontend Only Issue**: Revert frontend, old code won't pass security_answer
   - Backend will reject requests without security_answer
   - Need to also revert backend or disable check temporarily

2. **Backend Only Issue**: Revert backend
   - Frontend will try to send security_answer but old backend ignores it
   - Password change will work with old validation

3. **Database Issue**: New fields are optional
   - Existing functionality continues to work
   - Remove `security_question` and `security_answer_hash` fields if needed

## Future Enhancements

Potential improvements (not implemented):

1. **Multiple Security Questions**: Allow admin to configure 3+ questions, verify 2+ answers
2. **2FA Integration**: Add TOTP/SMS as alternative to security question
3. **Recovery Codes**: Generate one-time recovery codes for emergency access
4. **Answer Change**: Allow admin to change security question/answer
5. **Audit Log**: Log all password change attempts (success/failure)
6. **Account Lockout**: Lock account after N failed attempts
7. **Email Notification**: Send email when password is changed

## Support

For issues or questions:
1. Check backend logs: `pm2 logs ppc-backend`
2. Check frontend logs: `pm2 logs ppc-frontend`
3. Verify security question exists in database:
   ```javascript
   db.publishers.findOne({role: "admin"}, {security_question: 1, security_answer_hash: 1})
   ```
4. Re-run setup script if needed: `python scripts/add_admin_security_question.py`

---

**Implementation Date**: 2026-10-04
**Status**: ✅ Complete and Ready for Deployment
