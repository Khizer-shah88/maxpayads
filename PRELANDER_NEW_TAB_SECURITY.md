# Prelander New Tab Security Implementation

## Requirement
Prevent users from copying the prelander URL and opening it in a new tab.

## Implementation Strategy

### Two-Layer Security:

#### 1. **Backend Authorization (Primary Security)**
The backend has a robust authorization system in `prelander_auth_service.py`:

- **Session-Based**: Each click creates an authorization session
- **Fingerprint Binding**: Tied to IP + User-Agent  
- **Time-Limited**: Sessions expire (default: 300 seconds)
- **One-Time Use**: Handoff tokens consumed after first use
- **Cookie-Based**: HttpOnly cookies prevent JavaScript access

**Result**: When URL is pasted in new tab → No authorization cookie → Backend returns 204/403 → Blank page

#### 2. **Frontend Marker (Secondary UX)**
Frontend uses sessionStorage to track legitimate tabs:

```typescript
// On successful backend auth:
sessionStorage.setItem('prelander_authorized', 'yes')

// On page load:
const isAuthorized = sessionStorage.getItem('prelander_authorized') === 'yes'
```

**How it works:**
- `sessionStorage` is per-tab (survives reload, not in new tabs)
- Marker set ONLY after backend validates access
- New tab = no marker = backend denies = no content shown

## Flow Diagram

### Legitimate Access (Original Tab):
```
Click → /d/{slug} → Backend Auth ✓ → Set marker → Show content
        ↓
     Reload → Has marker → Backend Auth ✓ → Show content
```

###new Tab (URL Copy):
```
Paste URL → /d/{slug} → No marker → Backend Auth ✗ → BLANK PAGE
```

## Testing

### ✅ Should Work:
1. **First load from click**: Content shows
2. **Same tab reload**: Content shows (has marker + backend validates)
3. **Back/forward in same tab**: Content shows

### ❌ Should Block:
1. **Copy URL to new tab**: Blank page (no marker + no backend auth)
2. **Share URL**: Blank page (no authorization session)
3. **Bookmark and open later**: Blank page (session expired)

## Backend Configuration

Ensure in `.env`:
```bash
PRELANDER_AUTH_REQUIRED=true
PRELANDER_SESSION_TTL=300
```

## Why This Works

1. **sessionStorage**: Per-tab storage, doesn't transfer to new tabs
2. **Backend Auth**: Real security layer, validates every request  
3. **No Marker in New Tab**: Even if somehow bypassed, backend still denies
4. **Cookie HttpOnly**: Can't be accessed/copied by JavaScript

## Limitations

- Users CAN screenshot the content while viewing
- Users CAN record screen
- This prevents URL SHARING, not content copying
- For maximum security, consider adding watermarks with user ID

## Monitoring

Check backend logs for denied access:
```
[PRELANDER-AUTH] Denied prelander access for slug=xxx ip=xxx
```

High volume of denials may indicate:
- Legitimate users trying to share URLs
- Session timeout too short
- Bot/scraper activity
