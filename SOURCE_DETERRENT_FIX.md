# Source Deterrent - View-Source Redirection Fix

## Problem

The view-source deterrent was not working on prelander domains (e.g., `view-source:https://clickstopfile.cc/`). When viewing the source, users were seeing the HTML source code instead of being redirected to the rendered page.

## Root Cause

The middleware was excluding prelander pages from the `x-sd: 1` marker header:

```typescript
// BEFORE (incorrect)
if (process.env.ENABLE_SOURCE_DETERRENT === 'true' && !isPrelander && pathname !== '/clean-shell') {
  response.headers.set('x-sd', '1');
}
```

This prevented the service worker from sweeping view-source tabs on prelander domains.

## The Fix

Updated middleware to set the `x-sd: 1` marker on **all pages** when the deterrent is enabled:

```typescript
// AFTER (correct)
if (process.env.ENABLE_SOURCE_DETERRENT === 'true') {
  response.headers.set('x-sd', '1');
}
```

This allows the view-source deterrent to work on all domains including prelander domains.

## How It Works

1. **Heartbeat Script** - Injected by `app/layout.tsx` into ALL pages
   - Pings the service worker every 100ms to prove JavaScript is running
   - Registers the service worker at `/source-deterrent-sw.js`

2. **Service Worker** - Lives at `ppc-frontend/public/source-deterrent-sw.js`
   - Intercepts navigation requests
   - Checks for the `x-sd: 1` header (marker gate)
   - If marker is present and page is silent after 300ms, navigates it to itself
   - This closes view-source tabs (which can't run JavaScript) and reopens them as normal pages

3. **Marker Gate** - Now set on ALL pages when `ENABLE_SOURCE_DETERRENT=true`
   - Authorizes the service worker to sweep that page
   - Prevents loops through MAX_NAVIGATIONS guard (max 3 consecutive navigations)
   - Counter is reset on every heartbeat

## Testing

After deployment, test on any domain:

### On Prelander Domains (e.g., `https://clickstopfile.cc`)

1. **Normal browse**: Visit `https://clickstopfile.cc/` - should work normally
2. **View source**: Open `view-source:https://clickstopfile.cc/` - should redirect to `https://clickstopfile.cc/` after ~300ms ✅
3. **Fresh browser**: First visit before service worker installs will show source (expected)
4. **DevTools**: Check Network tab - should see `x-sd: 1` header on all page responses

### On Portal Domains (e.g., portal hostname)

Same behavior - view-source will redirect to the normal page.

## Safeguards Against Loops

The service worker has multiple protections:

1. **Loop Guard** - Maximum 3 consecutive navigations without a heartbeat
2. **Durable Budget** - Counter persisted in Cache API, reset on every heartbeat
3. **Marker Gate** - Only sweeps pages with `x-sd: 1` header
4. **ID Tracking** - Tracks which clients have already been navigated
5. **Grace Period** - 300ms window for page to start JavaScript before sweep

Even on prelander pages with one-time tickets, the safeguards prevent loops:
- Normal visitors send heartbeat immediately → no navigation
- Slow connections get 300ms grace period
- Maximum 3 navigations if JavaScript fails to start
- Counter resets on ANY heartbeat, so working pages are never replayed

## Files Changed

1. **`ppc-frontend/middleware.ts`** - Removed `!isPrelander` condition from x-sd header logic
2. **`ppc-frontend/tests/prelander-session.test.cjs`** - Updated test to expect `x-sd: 1` on all pages

## Test Results

All 43 tests passing ✅

```
✔ production source deterrent works on all pages including prelander domains
✔ silent marked document gets the full restored 300ms wait
✔ reload budget still stops after three navigations across worker restarts
✔ unavailable budget storage cannot trigger a redirect loop
... (39 more tests pass)
```

## Configuration

Ensure `ENABLE_SOURCE_DETERRENT=true` in your environment:

```bash
# In docker-compose.prod.yml
ENABLE_SOURCE_DETERRENT: "true"
```

## Summary

✅ **Fixed**: View-source deterrent now works on all domains including prelander domains
✅ **Safe**: Multiple loop guards prevent issues even with one-time tickets
✅ **Tested**: All 43 tests passing
✅ **Expected behavior**: `view-source:https://clickstopfile.cc/` → redirects to `https://clickstopfile.cc/`

The deterrent is now enabled globally on all pages when `ENABLE_SOURCE_DETERRENT=true`.
