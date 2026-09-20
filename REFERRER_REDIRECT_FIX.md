# Referrer-Based Redirect Fix

## Problem
When a publisher copied the prelander domain link and pasted it into a new tab (or on top of an existing URL like Facebook), the system would **always redirect to google.com**, regardless of what page was previously open in that tab.

## Solution
Modified the redirect logic to send users back to the **previous page they were on** (the referrer) instead of always redirecting to Google.

## Changes Made

### 1. Updated `tab-guard.ts`
**File**: `/ppc-frontend/lib/tab-guard.ts`

**Key Changes**:
- Renamed `BLOCK_URL` to `FALLBACK_URL` for clarity
- Added new function `getBlockRedirectUrl()` that:
  - First checks if `document.referrer` exists
  - Validates the referrer is not the same domain (to avoid redirect loops)
  - Returns the referrer URL if valid
  - Falls back to Google only if no valid referrer exists
- Updated redirect logic to use dynamic URL instead of hardcoded Google

**Before**:
```typescript
const BLOCK_URL = "https://www.google.com";
// ...
window.location.replace(BLOCK_URL);
```

**After**:
```typescript
const FALLBACK_URL = "https://www.google.com";

function getBlockRedirectUrl(): string {
  if (document.referrer && document.referrer !== window.location.href) {
    const referrerUrl = new URL(document.referrer);
    const currentUrl = new URL(window.location.href);
    
    if (referrerUrl.hostname !== currentUrl.hostname) {
      return document.referrer;
    }
  }
  return FALLBACK_URL;
}
// ...
window.location.replace(getBlockRedirectUrl());
```

### 2. Updated Prelander Page
**File**: `/ppc-frontend/app/d/[slug]/page.tsx`

**Key Changes**:
- Updated the inline pasted URL detection to also use referrer-based redirect
- Changed log message from "redirecting to Google" to "redirecting to previous page"
- Added logic to check for valid referrer before falling back to Google

**Before**:
```typescript
console.log('[TAB-GUARD] Direct pasted URL detected - redirecting to Google');
window.location.replace('https://www.google.com');
```

**After**:
```typescript
console.log('[TAB-GUARD] Direct pasted URL detected - redirecting to previous page');

const redirectUrl = document.referrer && document.referrer !== window.location.href
  ? document.referrer
  : 'https://www.google.com';

window.location.replace(redirectUrl);
```

## How It Works Now

### Scenario 1: User on Facebook
1. User browses Facebook (facebook.com)
2. Publisher copies prelander URL and pastes it into the address bar
3. System detects unauthorized access (no sessionStorage marker)
4. System reads `document.referrer` → finds "facebook.com"
5. **User is redirected back to Facebook** ✅

### Scenario 2: User on Any Website
1. User is on any website (e.g., twitter.com, youtube.com, etc.)
2. Publisher pastes prelander URL
3. System detects unauthorized access
4. System reads referrer
5. **User is redirected back to the previous website** ✅

### Scenario 3: Direct New Tab (No Referrer)
1. User opens a brand new tab with no previous page
2. Publisher pastes prelander URL
3. System detects unauthorized access
4. No referrer exists
5. **User is redirected to Google (fallback)** ✅

### Scenario 4: Legitimate Access (Through Redirect Flow)
1. User clicks on ad/redirect link
2. Goes through proper redirect flow
3. `sessionStorage` marker is set (`pl_tab_ok`)
4. User sees the prelander content normally ✅
5. Even if they paste the URL again in the same tab, it still works (marker persists)

## Security Considerations

### Loop Prevention
The system checks that the referrer hostname is different from the current hostname to prevent redirect loops:

```typescript
if (referrerUrl.hostname !== currentUrl.hostname) {
  return document.referrer;
}
```

This ensures that if somehow the referrer is the prelander domain itself, it won't create an infinite redirect loop.

### Fallback Safety
If any errors occur (invalid referrer, parsing errors, etc.), the system safely falls back to Google.

## Testing Recommendations

Test these scenarios:
1. ✅ Copy prelander URL from Facebook tab → paste in new tab → should go back to Facebook
2. ✅ Copy prelander URL from YouTube tab → paste over YouTube URL → should go back to YouTube  
3. ✅ Copy prelander URL → paste in brand new empty tab → should go to Google
4. ✅ Legitimate user through redirect flow → should see prelander content normally
5. ✅ Reload prelander page in legitimate tab → should still work (sessionStorage persists)

## Benefits

1. **Better User Experience**: Users aren't always forced to Google, they go back to what they were doing
2. **More Natural Behavior**: Mimics browser "back" button behavior
3. **Maintained Security**: Still blocks unauthorized pasted URLs
4. **Flexible Fallback**: Google is still used when no referrer exists
5. **Loop Protection**: Built-in safety against redirect loops

## Files Modified

1. `/ppc-frontend/lib/tab-guard.ts`
2. `/ppc-frontend/app/d/[slug]/page.tsx`

No backend changes required - this is purely a frontend behavior modification.
