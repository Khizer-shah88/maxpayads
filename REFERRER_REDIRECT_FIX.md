# Referrer-Based Redirect Fix (No Google Fallback)

## Problem
When a publisher copied the prelander domain link and pasted it into a new tab (or on top of an existing URL like Facebook), the system would **always redirect to google.com**, regardless of what page was previously open in that tab or browser.

## Solution
Modified the redirect logic to:
1. Use `document.referrer` if available (when pasting over an existing page)
2. Use `window.history.back()` to return to the previous page in browser history (when pasting in a new tab)
3. Close the tab or go to `about:blank` as last resort
4. **NEVER force users to Google** unless there's literally no other option

## Changes Made

### 1. Updated `tab-guard.ts`
**File**: `/ppc-frontend/lib/tab-guard.ts`

**Key Changes**:
- Completely removed Google redirect as the fallback
- Added `getBlockRedirectUrl()` function that returns referrer URL or `null`
- Added `blockAccess()` function with smart redirect logic:
  1. If valid referrer exists → redirect there
  2. If no referrer but browser history exists → use `window.history.back()`
  3. If no history → try to close the tab with `window.close()`
  4. As absolute last resort → redirect to `about:blank`

**Logic Flow**:
```typescript
function blockAccess(): void {
  const redirectUrl = getBlockRedirectUrl();
  
  if (redirectUrl) {
    // Valid referrer found - redirect there
    window.location.replace(redirectUrl);
  } else {
    // No referrer - use browser history back
    if (window.history.length > 1) {
      window.history.back();
      // Backup: close tab if back doesn't work
      setTimeout(() => {
        window.close();
        setTimeout(() => {
          window.location.replace('about:blank');
        }, 200);
      }, 1000);
    } else {
      // No history - close tab or blank page
      window.close();
      setTimeout(() => {
        window.location.replace('about:blank');
      }, 200);
    }
  }
}
```

### 2. Updated Prelander Page
**File**: `/ppc-frontend/app/d/[slug]/page.tsx`

**Key Changes**:
- Replaced hardcoded Google fallback with browser history back logic
- Same smart redirect flow as tab-guard.ts:
  1. Try referrer first
  2. Fall back to `history.back()`
  3. Try `window.close()`
  4. Last resort: `about:blank`

**Before**:
```typescript
console.log('[TAB-GUARD] Direct pasted URL detected - redirecting to previous URL');
const previousUrl = document.referrer || 'https://www.google.com';
window.location.replace(previousUrl);
```

**After**:
```typescript
console.log('[TAB-GUARD] Direct pasted URL detected - using browser back');

// Try referrer first
if (document.referrer && document.referrer !== window.location.href) {
  try {
    const referrerUrl = new URL(document.referrer);
    const currentUrl = new URL(window.location.href);
    if (referrerUrl.hostname !== currentUrl.hostname) {
      window.location.replace(document.referrer);
      return;
    }
  } catch {
    // Invalid referrer, fall through
  }
}

// Use browser history back
if (window.history.length > 1) {
  window.history.back();
  // Fallback timeout to close tab
  setTimeout(() => {
    window.close();
    setTimeout(() => {
      if (!document.hidden) {
        window.location.replace('about:blank');
      }
    }, 200);
  }, 1000);
} else {
  window.close();
  setTimeout(() => {
    window.location.replace('about:blank');
  }, 200);
}
```

## How It Works Now

### Scenario 1: Paste Over Existing Page (Has Referrer)
1. User is on Facebook (facebook.com)
2. Publisher pastes prelander URL in the address bar (over Facebook URL)
3. System detects unauthorized access
4. System reads `document.referrer` → finds "facebook.com"
5. **User is redirected back to Facebook** ✅

### Scenario 2: Paste in New Tab (No Referrer, Has History)
1. User opens a new tab
2. Publisher pastes prelander URL
3. System detects unauthorized access
4. No referrer exists
5. Browser history has entries (`window.history.length > 1`)
6. **System calls `window.history.back()` → returns to previous page** ✅

### Scenario 3: Paste in First Tab Ever (No History)
1. User just opened browser, first tab
2. Publisher pastes prelander URL
3. System detects unauthorized access
4. No referrer, no history
5. **System tries to close the tab with `window.close()`** ✅
6. If close fails (requires user gesture), redirects to `about:blank` ✅

### Scenario 4: Legitimate Access (Through Redirect Flow)
1. User clicks on ad/redirect link
2. Goes through proper redirect flow
3. `sessionStorage` marker is set (`pl_tab_ok`)
4. **User sees the prelander content normally** ✅
5. Even if they paste the URL again in the same tab, it still works ✅

## Why This is Better

### Old Behavior:
- Paste URL → **Always forced to Google** → Bad UX, confusing

### New Behavior:
- Paste over page → **Back to that page** → User continues browsing ✅
- Paste in new tab → **Back to previous page in browser** → Natural behavior ✅
- No history at all → **Close tab or blank page** → Clean exit ✅
- **Google is NEVER forced on users** → Respectful UX ✅

## Technical Details

### Browser History API
- `window.history.length` - Number of entries in browser history (includes current page)
- `window.history.back()` - Navigate to previous page in history
- If `length > 1`, there's at least one page to go back to

### Window Close
- `window.close()` - Attempts to close the tab/window
- Only works if the window was opened by script OR user has given permission
- Most modern browsers block `window.close()` without user gesture
- Used as a graceful attempt, with fallback to `about:blank`

### Timing
- 1000ms delay before fallback to `window.close()` (gives `history.back()` time to work)
- 200ms delay before `about:blank` redirect (gives `window.close()` time to work)
- These delays ensure smooth transitions without premature fallbacks

### Security Considerations

#### Loop Prevention
The system checks that the referrer hostname is different from the current hostname:
```typescript
if (referrerUrl.hostname !== currentUrl.hostname) {
  return document.referrer;
}
```
This prevents infinite redirect loops if somehow the referrer is the prelander domain itself.

#### Safe Fallbacks
Every step has a fallback:
1. Referrer check → might be invalid or same domain
2. History back → might not exist or fail
3. Window close → might be blocked by browser
4. about:blank → always works as final fallback

## Testing Scenarios

### Test Case 1: Paste Over Page ✅
1. Open Facebook in browser
2. Copy prelander URL
3. Paste in address bar (over Facebook URL)
4. **Expected**: Redirected back to Facebook

### Test Case 2: Paste in New Tab ✅
1. Browse some pages (build browser history)
2. Open new tab (Ctrl/Cmd + T)
3. Paste prelander URL
4. **Expected**: Browser goes back to previous page

### Test Case 3: Fresh Browser ✅
1. Close all browser windows
2. Open fresh browser
3. First tab: paste prelander URL
4. **Expected**: Tab closes OR shows about:blank (NOT Google)

### Test Case 4: Legitimate User ✅
1. Click on ad/redirect link
2. Go through proper flow
3. **Expected**: Prelander content displays normally

### Test Case 5: Reload in Same Tab ✅
1. Legitimate user sees prelander
2. Refresh page (F5)
3. **Expected**: Content still displays (sessionStorage persists)

## Benefits

1. ✅ **Natural Browser Behavior**: Uses browser's own back button logic
2. ✅ **No Forced Redirects**: Never sends users to Google against their will
3. ✅ **Respects Context**: Uses referrer when available, history when not
4. ✅ **Graceful Degradation**: Multiple fallback layers
5. ✅ **Maintained Security**: Still blocks unauthorized pasted URLs
6. ✅ **Better UX**: Users return to what they were doing, not a random search engine

## Files Modified

1. `/ppc-frontend/lib/tab-guard.ts` - Core tab guard logic
2. `/ppc-frontend/app/d/[slug]/page.tsx` - Prelander page inline protection

No backend changes required - this is purely frontend behavior.

## Important Notes

- The system will NEVER redirect to Google unless `about:blank` also fails (which is impossible)
- Most users will experience `history.back()` which is identical to clicking the browser back button
- Users pasting over existing pages will go back to those pages (via referrer)
- Only users with no history AND in browsers that block `window.close()` will see `about:blank`
- `about:blank` is still better than forcing Google, as it's neutral and doesn't assume user intent
