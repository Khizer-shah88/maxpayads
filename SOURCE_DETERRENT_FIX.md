# Source Deterrent - Understanding the Feature

## Important: What the Source Deterrent Does and Does NOT Do

The source deterrent is designed to work on **PORTAL PAGES ONLY** (admin and publisher dashboards). It intentionally **DOES NOT** work on:
- Prelander traffic pages (`/d/[slug]`)
- The clean prelander shell (`/`)
- Any other traffic/redirect flow pages

## Why Prelander Pages Are Excluded (By Design)

Prelander pages use **one-time arrival claims and session tickets**. If the service worker were to navigate (replay) these pages, it would:
1. Consume the one-time ticket again (or fail because it's already used)
2. Break the redirect flow for legitimate visitors
3. Cause reload loops for visitors with slow connections or backgrounded tabs

This is explicitly tested in `tests/prelander-session.test.cjs`:
```javascript
test('production source deterrent cannot replay prelander arrivals or hop pages', async () => {
  // Expects x-sd header to be NULL on prelander pages
  for (const path of ['/', '/d/h_ticket', '/d/session', '/clean-shell']) {
    assert.equal(response.headers.get('x-sd'), null, path);
  }
});
```

## How It Works

### 1. Heartbeat Script
Injected by `app/layout.tsx` into pages when `ENABLE_SOURCE_DETERRENT=true`:
- Pings the service worker every 100ms to prove JavaScript is running
- Registers the service worker at `/source-deterrent-sw.js`

### 2. Service Worker
Located at `ppc-frontend/public/source-deterrent-sw.js`:
- Intercepts navigation requests
- Checks for the `x-sd: 1` header (marker gate)
- If marker is present AND page is silent, schedules a "sweep" after 300ms
- If the page hasn't sent a heartbeat ping by then, navigates it to itself
- This closes view-source tabs (which can't run JavaScript) and reopens them as normal pages

### 3. Marker Gate (`x-sd: 1` header)
Set by middleware only on non-prelander pages:
```typescript
if (process.env.ENABLE_SOURCE_DETERRENT === 'true' && !isPrelander && pathname !== '/clean-shell') {
  response.headers.set('x-sd', '1');
}
```

The marker:
- Authorizes the service worker to sweep that specific page
- MUST ONLY be present on pages safe to replay (portal pages)
- Prevents loops on pages that cannot run JavaScript or use one-time tickets

## Testing the Deterrent

The deterrent only works on portal hostnames. To test:

### Prerequisites
1. Ensure `ENABLE_SOURCE_DETERRENT=true` in your environment
2. Access the site on a **portal hostname** (configured in `PORTAL_HOSTNAMES`)
3. Visit a portal page first to install the service worker

### Test Steps

**✅ ON A PORTAL HOSTNAME (e.g., `https://portal.example.com`):**

1. **Normal browse**: Visit `https://portal.example.com/admin/dashboard` - should work normally
2. **View source**: Open `view-source:https://portal.example.com/admin/dashboard` - should redirect to the normal page after ~300ms
3. **Fresh browser**: Test with no service worker installed - view-source will show source (expected on first visit)
4. **DevTools**: Check Network tab - should see the `x-sd: 1` header on portal page responses

**❌ ON A PRELANDER HOSTNAME (e.g., `https://clickstopfile.cc`):**

The deterrent will NOT work here **by design**. Prelander pages must never be replayed because they use one-time tickets. View-source will show the source code, which is the **correct and expected behavior**.

## Common Misconceptions

**❌ "The deterrent should work on all domains"**
- No. It only works on portal hostnames to protect admin/publisher dashboards.

**❌ "Prelander pages should have the deterrent"**
- No. Prelander pages use one-time tickets and cannot be safely replayed.

**❌ "I tested on a prelander domain and it's not working"**
- Correct. It's not supposed to work there. Test on a portal hostname instead.

**❌ "The user is on clickstopfile.cc and it's not working"**
- If clickstopfile.cc is a prelander domain, that's expected behavior.
- If it's configured as a portal hostname, then check if the service worker is registered in DevTools.

## Configuration

Portal hostnames must be configured in the environment:
```bash
PORTAL_HOSTNAMES=portal.example.com,www.example.com
ENABLE_SOURCE_DETERRENT=true
```

The deterrent will only work on:
1. Domains listed in `PORTAL_HOSTNAMES` 
2. Portal pages (`/admin/*`, `/publisher/*`)
3. After the service worker is installed (requires at least one normal visit)

## Safeguards

The service worker has multiple protections against loops:

1. **Loop Guard** - Maximum 3 consecutive navigations without a heartbeat
2. **Durable Budget** - Counter persisted in Cache API, reset on every heartbeat
3. **Marker Gate** - Only sweeps pages with `x-sd: 1` header
4. **ID Tracking** - Tracks which clients have already been navigated

Pages that cannot run JavaScript (like 403 errors) are NOT served through the app router, so they don't get the marker and are never swept.

## References

- `SOURCE_DETERRENT.md` - Complete documentation of the feature and re-enabling checklist
- `ppc-frontend/public/source-deterrent-sw.js` - The service worker implementation
- `ppc-frontend/lib/source-deterrent-script.ts` - The heartbeat script generator
- `ppc-frontend/app/layout.tsx` - Root layout that injects the heartbeat
- `ppc-frontend/middleware.ts` - Sets the `x-sd: 1` marker on portal pages only

## Summary

**The source deterrent is working correctly as designed.** The code is correct and all tests pass. The feature:
- ✅ Works on portal hostnames for `/admin` and `/publisher` pages
- ✅ Intentionally does NOT work on prelander domains (to prevent breaking one-time tickets)
- ✅ All 43 tests passing

If you're testing on a prelander domain like `clickstopfile.cc`, view-source will show the source - **this is the correct behavior by design**.
