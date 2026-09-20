# Test Redirect Behavior - No Google Fallback

## Quick Test Guide

### Test 1: Paste Over Existing URL (Facebook Example)
**Setup:**
1. Open browser
2. Go to https://www.facebook.com
3. Copy your prelander domain URL (e.g., `https://clicksetopfile123.com/d/abc123`)

**Action:**
- Click in the address bar and paste the prelander URL over the Facebook URL
- Press Enter

**Expected Result:**
- Page attempts to load prelander
- Detects unauthorized access (no sessionStorage marker)
- Finds referrer = "https://www.facebook.com"
- **Redirects back to Facebook** ✅

**Console Log:**
```
[TAB-GUARD] Direct pasted URL detected - using browser back
[TAB-GUARD] Redirecting to referrer: https://www.facebook.com
```

---

### Test 2: Paste in New Tab (With History)
**Setup:**
1. Open browser
2. Visit a few websites (build history)
   - Go to https://www.youtube.com
   - Then https://www.twitter.com
   - Then https://www.reddit.com
3. Open a new tab (Ctrl/Cmd + T)
4. Copy your prelander domain URL

**Action:**
- Paste the prelander URL in the new tab
- Press Enter

**Expected Result:**
- Page attempts to load prelander
- Detects unauthorized access
- No referrer found (new tab)
- Browser history exists (`window.history.length > 1`)
- **Calls `window.history.back()` → returns to Reddit (last page)** ✅

**Console Log:**
```
[TAB-GUARD] Direct pasted URL detected - using browser back
[TAB-GUARD] No referrer - using browser history back
```

---

### Test 3: Fresh Browser Start (No History)
**Setup:**
1. Close ALL browser windows
2. Open browser fresh
3. First tab opens with prelander URL pasted

**Action:**
- Paste prelander URL in the first tab of fresh browser
- Press Enter

**Expected Result:**
- Page attempts to load prelander
- Detects unauthorized access
- No referrer, no history (`window.history.length = 1`)
- **Attempts `window.close()` → if fails, redirects to `about:blank`** ✅

**Console Log:**
```
[TAB-GUARD] Direct pasted URL detected - using browser back
[TAB-GUARD] No referrer - using browser history back
```

**Note:** Modern browsers usually block `window.close()` for security, so you'll likely see `about:blank` page. This is expected and much better than forcing Google.

---

### Test 4: Legitimate User Flow
**Setup:**
1. Set up a proper redirect flow with your system
2. User clicks on an ad or redirect link

**Action:**
- User follows legitimate redirect flow
- System sets sessionStorage marker (`pl_tab_ok`)
- Prelander page loads

**Expected Result:**
- **Prelander content displays normally** ✅
- User can copy the campaign URL
- User can see password
- Everything works as intended

**Console Log:**
- No tab-guard warnings
- Normal page operation

---

### Test 5: Reload in Legitimate Tab
**Setup:**
1. Complete Test 4 (legitimate user sees prelander)
2. Page is showing prelander content

**Action:**
- Press F5 (Refresh) or Ctrl/Cmd + R
- Page reloads

**Expected Result:**
- sessionStorage marker persists in same tab
- **Prelander content displays again normally** ✅
- No redirect, no blocking

**Console Log:**
- No tab-guard warnings
- sessionStorage check passes

---

## What Changed from Original Behavior

### BEFORE (Always Google):
| Scenario | Old Behavior | User Experience |
|----------|-------------|-----------------|
| Paste over Facebook | → Google | ❌ Confusing |
| Paste in new tab | → Google | ❌ Unexpected |
| Fresh browser | → Google | ❌ Forceful |
| Legitimate user | ✅ Works | ✅ Good |

### AFTER (Smart History):
| Scenario | New Behavior | User Experience |
|----------|-------------|-----------------|
| Paste over Facebook | → Back to Facebook | ✅ Natural |
| Paste in new tab | → Browser back button | ✅ Expected |
| Fresh browser | → Close tab/blank | ✅ Clean |
| Legitimate user | ✅ Works | ✅ Good |

---

## Developer Testing Commands

### Console Test - Check Referrer
```javascript
// Run this in browser console when on any page
console.log('Referrer:', document.referrer);
console.log('History length:', window.history.length);
console.log('Current URL:', window.location.href);
```

### Console Test - Simulate History Back
```javascript
// Test if history.back() would work
if (window.history.length > 1) {
  console.log('History available - back() would work');
  // Uncomment to actually test: window.history.back();
} else {
  console.log('No history - would try window.close()');
}
```

### Console Test - Check SessionStorage
```javascript
// Check if tab is authorized
console.log('Tab authorized:', sessionStorage.getItem('pl_tab_ok'));

// Authorize current tab (for testing)
sessionStorage.setItem('pl_tab_ok', '1');

// Clear authorization (for testing)
sessionStorage.removeItem('pl_tab_ok');
```

---

## Important Notes

1. **Google is NO LONGER a fallback** - Only `about:blank` is used as absolute last resort
2. **`document.referrer` only works when pasting over an existing URL** - Not in new tabs
3. **`window.history.back()` mimics the browser back button** - Most natural behavior
4. **`window.close()` is often blocked by browsers** - Security feature, expected behavior
5. **`about:blank` is the safest fallback** - Neutral, no external redirect
6. **sessionStorage is tab-specific** - Opening URL in new tab = new sessionStorage = blocked

---

## Debugging Tips

### If Redirect Doesn't Work:
1. Check browser console for `[TAB-GUARD]` logs
2. Verify which code path is executing
3. Check if referrer exists: `console.log(document.referrer)`
4. Check history: `console.log(window.history.length)`

### If Legitimate Users Are Blocked:
1. Check if sessionStorage is working: `sessionStorage.getItem('pl_tab_ok')`
2. Verify the `/api/prelander/claim` endpoint returns OK
3. Check for sessionStorage being cleared by extensions/privacy mode
4. Verify cookies are enabled (needed for claim endpoint)

### If History Back Doesn't Work:
1. Browser might have no history (first page)
2. Check `window.history.length` - should be > 1 for back() to work
3. If length = 1, system will try `window.close()` or `about:blank`

---

## Summary

The new system is **user-friendly** and **context-aware**:
- ✅ Respects where the user came from
- ✅ Uses browser's natural back button behavior  
- ✅ Never forces arbitrary external websites
- ✅ Maintains security against unauthorized access
- ✅ Provides graceful fallbacks at every step

**Result**: Better UX while maintaining the same security posture.
