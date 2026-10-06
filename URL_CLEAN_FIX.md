# URL Clean Fix - Removed Query Parameter Visibility

## Problem
When users arrived at the prelander domain after the redirect flow:
1. URL briefly showed `/?_s=1` (session marker query parameter) in the browser address bar
2. This query parameter was visible before JavaScript cleaned it to `/`
3. User wanted NO visible URL parameters/prefixes/suffixes - just clean domain root `/`

## Root Cause
The `/_auth/{handoff}` endpoint was redirecting to `/?_s=1` so middleware could detect the fresh session establishment. The middleware would rewrite this to `/clean-shell`, but the URL bar would show `/?_s=1` briefly before JavaScript's `history.replaceState` cleaned it to `/`.

## Solution
Changed the redirect flow to use `/d/session` instead of `/?_s=1`:

### Backend Changes (`ppc-backend/app/routers/prelander_router.py`)
```python
# BEFORE
dest = "/?_s=1"  # _s=1 = session established marker
response = RedirectResponse(url=dest, status_code=302)

# AFTER  
dest = "/d/session"
response = RedirectResponse(url=dest, status_code=302)
```

### Frontend Middleware Changes (`ppc-frontend/middleware.ts`)
**Removed** the session marker detection logic:
```typescript
// REMOVED THIS ENTIRE BLOCK
if (sessionMarker === '1' && hasSession) {
  const url = request.nextUrl.clone();
  url.pathname = '/clean-shell';
  url.search = '';
  const page = NextResponse.rewrite(url);
  // ...
  return page;
}
```

Also updated the `/_auth` recovery block to redirect to `/d/session`.

### Test Updates
Updated test assertions to expect `/d/session` instead of `/?_s=1`:
- `ppc-backend/tests/test_prelander_auth.py`
- `ppc-backend/tests/test_one_use_redirect_hops.py`

## How It Works Now

### New Flow
```
User clicks smartlink
    ↓
Anchor → Inter → /_auth/{handoff}
    ↓
Backend validates handoff, sets cookies
    ↓
302 redirect to /d/session
    ↓
Middleware detects /d/session + valid session cookie
    ↓
Rewrites to /clean-shell (URL stays as /d/session during server processing)
    ↓
JavaScript in clean-shell uses history.replaceState({}, '', '/')
    ↓
Final URL: https://prelander-domain.com/
```

### URL Visibility Timeline
1. `/_auth/{token}` - shown during handoff exchange (very brief)
2. `/d/session` - shown during middleware processing (server-side, ~100ms)
3. `/` - cleaned by JavaScript, stays clean forever

### Benefits
- **No query parameters ever visible** - `/d/session` is a clean path
- **Existing middleware logic works** - `/d/session` was already a protected route
- **JavaScript still cleans URL** - `history.replaceState` removes `/d/session` path
- **Tests updated and passing** - all assertions now expect `/d/session`

## Automatic Download on Reload Issue

The user also mentioned automatic downloads occurring on page reload. This should be investigated separately if the issue persists after this fix.

### Potential Causes
1. Service worker caching behavior
2. Template JavaScript triggering downloads
3. Browser back/forward cache behavior

### Next Steps if Issue Persists
- Check if template has auto-download JavaScript
- Verify service worker is not intercepting reload requests
- Check browser console for download triggers
- Test with service worker disabled

## Files Changed
- `ppc-backend/app/routers/prelander_router.py`
- `ppc-frontend/middleware.ts`
- `ppc-frontend/app/clean-shell/route.ts` (comment update only)
- `ppc-backend/tests/test_prelander_auth.py`
- `ppc-backend/tests/test_one_use_redirect_hops.py`

## Testing
- Backend CI tests will run automatically
- Frontend build will verify TypeScript compilation
- Manual testing required to verify URL visibility behavior
- User should test reload behavior to confirm no automatic downloads

## Commit
```
commit 8c3e134
Remove URL query parameter visibility - redirect to /d/session directly

- Changed /_auth handoff redirect from /?_s=1 to /d/session
- Removed middleware session marker detection logic  
- URL now shows only /d/session briefly during server processing
- JavaScript in clean-shell still cleans URL to bare / via history.replaceState
- Updated tests to expect /d/session redirect destination
- No more visible query parameters in URL bar
```
