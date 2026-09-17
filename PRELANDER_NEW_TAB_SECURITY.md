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
Anchor Click → Redirect Flow → /d/{slug} (with external referrer)
                                    ↓
                          Check sessionStorage marker
                                    ↓
                          No marker found (first visit)
                                    ↓
                          Check document.referrer
                                    ↓
                          Has external referrer ✓
                                    ↓
                          Set marker = 'granted' → Show content
                                    ↓
                          Page Reload (same tab)
                                    ↓
                          Check sessionStorage marker
                                    ↓
                          Marker = 'granted' ✓ → Show content
```

### Blocked Access (New Tab with Pasted URL):
```
Copy URL → Paste in new tab → /d/{slug} (no external referrer)
                                    ↓
                          Check sessionStorage marker
                                    ↓
                          No marker found (new tab)
                                    ↓
                          Check document.referrer
                                    ↓
                          No external referrer (empty or self-referrer) ✗
                                    ↓
                          Set marker = 'denied' → BLANK PAGE
                                    ↓
                          Try to reload
                                    ↓
                          Check sessionStorage marker
                                    ↓
                          Marker = 'denied' ✗ → BLANK PAGE (permanent)
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

## How It Works

### SessionStorage Marker System:

The security uses a `sessionStorage` marker with three possible states:

1. **`'granted'`**: Tab was authorized (came from redirect flow with external referrer)
2. **`'denied'`**: Tab was blocked (direct access without external referrer)  
3. **`null`**: No marker (first visit in this tab)

### Decision Flow:

```typescript
// Check existing marker first (preserves state across reloads)
if (marker === 'granted') {
  // Previously authorized → Allow access
}
else if (marker === 'denied') {
  // Previously denied → Block permanently
}
else {
  // No marker → First visit → Check referrer
  if (hasExternalReferrer) {
    // Redirect flow → Set marker = 'granted' → Allow
  } else {
    // Direct access → Set marker = 'denied' → Block
  }
}
```

### Why This Works:

1. **SessionStorage is per-tab**: Doesn't transfer to new tabs, but survives reloads
2. **Check marker BEFORE referrer**: Preserves authorization state on reload
3. **Permanent denial**: Once denied, always denied (even on reload)
4. **External referrer validation**: Only grants access when coming from redirect flow

### Key Behavior:

- **First load from redirect**: External referrer → Grant → Set marker
- **Reload in original tab**: Has `'granted'` marker → Allow (no referrer check)
- **Copy to new tab**: No marker → Check referrer → Self/empty → Deny → Set marker
- **Reload in blocked tab**: Has `'denied'` marker → Block permanently

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
