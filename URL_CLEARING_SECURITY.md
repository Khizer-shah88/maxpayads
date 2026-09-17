# Ultra-Fast URL Clearing Security

## How It Works

### Two-Layer Defense:

#### 1. **Inline Script (Runs BEFORE React)**
Located in: `ppc-frontend/app/d/[slug]/layout.tsx`

- Runs with `strategy="beforeInteractive"` - executes BEFORE React hydrates
- Plain JavaScript (no React dependencies)
- Checks sessionStorage marker
- Immediately redirects to `about:blank` if unauthorized

**Speed**: Runs in ~1-5ms - faster than any page rendering

#### 2. **React useEffect (Backup Layer)**
Located in: `ppc-frontend/app/d/[slug]/page.tsx`

- Runs after component mounts (backup if script somehow fails)
- Same logic as inline script
- Prevents any data fetching if denied

## User Experience

### ✅ Legitimate User (Original Tab):
```
1. Click on anchor link
2. Redirect flow → Prelander domain
3. Script checks: Has external referrer → GRANT
4. Sets marker = 'granted'
5. Page loads normally
6. Reload works perfectly (marker persists)
```

### ❌ Unauthorized User (Pasted URL):
```
1. Copy URL from original tab
2. Open new tab
3. Paste URL and press Enter
4. Browser starts loading page
5. Inline script runs (<5ms)
6. Checks: No external referrer → DENY
7. Sets marker = 'denied'
8. Immediately redirects to about:blank
9. Address bar shows: about:blank
10. No content visible
11. No white flash
```

## Testing

### Test 1: Legitimate Flow
1. Start from anchor domain
2. Go through redirect chain
3. Prelander loads ✅
4. F5 to reload → Still works ✅

### Test 2: Copy to New Tab
1. Copy URL from address bar
2. Ctrl+T (new tab)
3. Paste URL, press Enter
4. **Watch carefully**: You'll see URL for <100ms, then immediately becomes `about:blank`
5. No white page visible ❌
6. No content shown ❌

### Test 3: Type URL Manually
1. Open new tab
2. Type prelander domain manually
3. Press Enter
4. Same as Test 2 - instant redirect to `about:blank` ❌

## Why This Is Fast

### Execution Timeline:
```
0ms    - Browser requests HTML
50ms   - HTML starts arriving
100ms  - <head> parsed
105ms  - Inline script executes ⚡ SECURITY CHECK HAPPENS HERE
106ms  - If denied: window.location.replace('about:blank')
107ms  - Browser cancels page load
108ms  - Redirects to about:blank
200ms  - React would have started loading (never reached if denied)
```

### Key Optimizations:
1. **beforeInteractive strategy** - Script in `<head>`, runs before `<body>`
2. **Inline script** - No external file to fetch
3. **Plain JavaScript** - No React overhead
4. **Synchronous execution** - Blocks page load until check completes
5. **Immediate redirect** - Uses `location.replace()` (no history entry)

## Technical Details

### SessionStorage Marker:
- **Key**: `prelander_tab_authorized`
- **Values**: `'granted'`, `'denied'`, or `null`
- **Scope**: Per-tab (survives reload, NOT in new tabs)

### Referrer Check:
```javascript
var ref = document.referrer;
var host = window.location.hostname;
var hasExternal = ref && ref.indexOf(host) === -1;
```

- **External referrer**: Different domain (redirect flow) → GRANT
- **No referrer / Same domain**: Pasted URL / Direct access → DENY

### Redirect Method:
```javascript
window.location.replace('about:blank');
```

- **replace()**: No browser history entry (can't use back button)
- **about:blank**: Universal browser protocol (always works)
- **Synchronous**: Executes immediately

## Browser Compatibility

Works in all browsers that support:
- ✅ sessionStorage (IE8+, all modern browsers)
- ✅ document.referrer (all browsers)
- ✅ about:blank (all browsers)
- ✅ Next.js Script component with beforeInteractive

## Limitations

### Cannot Prevent:
- ❌ Initial HTTP request (browser always makes it)
- ❌ Server logs seeing the request
- ❌ Network traffic analysis
- ❌ Screenshots of content in original tab
- ❌ Screen recordings

### Can Prevent:
- ✅ Viewing content in new tabs
- ✅ Sharing URLs with others
- ✅ Bookmarking and opening later
- ✅ Manual URL typing
- ✅ Content visibility (<5ms flash max)

## Security Notes

### This Is Client-Side Security:
- **NOT foolproof** - Determined attackers can bypass client-side checks
- **Good for casual users** - Prevents accidental URL sharing
- **Server-side backup** - Backend also validates authorization
- **Defense in depth** - Multiple layers of protection

### Bypass Scenarios:
- User disables JavaScript → Server-side auth still blocks
- User modifies sessionStorage → Server-side auth still blocks
- User intercepts network → Encrypted HTTPS protects data
- User uses developer tools → Can only affect their own tab

## Troubleshooting

### Original Tab Gets Blocked:
- Check referrer is being passed (some privacy extensions block it)
- Test in incognito mode without extensions
- Check browser console for errors

### New Tab Shows Content:
- Clear browser cache and sessionStorage
- Check if sessionStorage is enabled
- Verify script is in HTML (view page source)

### About:blank Doesn't Work:
- Check browser security settings
- Try different browser
- Check for conflicting browser extensions

## Performance Impact

- **Original tab**: +1-2ms (negligible)
- **Blocked tab**: -200ms (saves React load time)
- **Network**: No extra requests
- **Storage**: 1 tiny sessionStorage key

## Monitoring

Check browser console for security logs:
```
[SECURITY] First visit - checking authorization
[SECURITY] - Referrer: (none)
[SECURITY] ✗ Access DENIED - clearing URL immediately
```

Or for legitimate access:
```
[SECURITY] First visit - checking authorization
[SECURITY] - Referrer: https://external-domain.com
[SECURITY] ✓ Access GRANTED - external referrer detected
```
