# Prelander Security Testing Instructions

## What Changed

The security check now runs in a **separate useEffect** that executes **before** any data fetching, and it affects **all code paths** (both slug mode and session mode).

### Key Improvements:
1. **Runs on component mount** - Security check happens first, before any API calls
2. **Blocks all paths** - Works for `/d/{slug}` AND clean URL `/` (session mode)
3. **Separate from fetch logic** - Data fetch skips entirely if access denied
4. **Clear console logs** - Use `[SECURITY]` prefix for easy debugging

## Testing Steps

### Step 1: Test Legitimate Flow (Should Work)
1. Clear browser cache and sessionStorage (F12 → Application → Storage → Clear)
2. Start from anchor domain (the beginning of your redirect chain)
3. Go through normal redirect flow → Prelander domain should load ✅
4. **Open browser console** (F12) - You should see:
   ```
   [SECURITY] First visit - checking authorization
   [SECURITY] - Referrer: https://some-external-domain.com
   [SECURITY] - Has external referrer: true
   [SECURITY] ✓ Access GRANTED - external referrer detected
   ```
5. Content shows normally ✅

### Step 2: Test Same Tab Reload (Should Work)
1. **Without closing the tab**, press F5 to reload
2. Check console - You should see:
   ```
   [SECURITY] ✓ Authorized tab - access granted
   ```
3. Content still shows ✅
4. Reload multiple times - always works ✅

### Step 3: Test New Tab with Pasted URL (Should Block)
1. **Copy the URL** from address bar (e.g., `https://prelander-domain.com/`)
2. **Open NEW tab** (Ctrl+T / Cmd+T)
3. **Paste URL** and press Enter
4. Check console - You should see:
   ```
   [SECURITY] First visit - checking authorization
   [SECURITY] - Referrer: (none)
   [SECURITY] - Has external referrer: false
   [SECURITY] ✗ Access DENIED - no external referrer
   [PRELANDER] Skipping fetch - access denied by security check
   ```
5. Page shows **completely blank** (white screen) ❌
6. No content, no loader, nothing

### Step 4: Test Reload in Blocked Tab (Should Stay Blocked)
1. **In the blocked tab**, press F5 to reload
2. Check console - You should see:
   ```
   [SECURITY] ✗ Denied tab - blocking permanently
   [PRELANDER] Skipping fetch - access denied by security check
   ```
3. Page stays **completely blank** ❌
4. Reload multiple times - always blocked ❌

### Step 5: Test Typing URL Manually (Should Block)
1. Open new tab
2. Type the prelander domain manually in address bar
3. Same as Step 3 - should be blocked ❌

## Expected Console Logs

### Authorized Tab (First Load):
```
[SECURITY] First visit - checking authorization
[SECURITY] - Referrer: https://external-domain.com/...
[SECURITY] - Current host: prelander-domain.com
[SECURITY] - Has external referrer: true
[SECURITY] ✓ Access GRANTED - external referrer detected
[PRELANDER DEBUG] useEffect triggered
[PRELANDER DEBUG] Starting fetch
...
[PRELANDER SUCCESS] Setting prelander data
```

### Authorized Tab (Reload):
```
[SECURITY] ✓ Authorized tab - access granted
[PRELANDER DEBUG] useEffect triggered
[PRELANDER DEBUG] Starting fetch
...
[PRELANDER SUCCESS] Setting prelander data
```

### Blocked Tab (First Load):
```
[SECURITY] First visit - checking authorization
[SECURITY] - Referrer: (none)
[SECURITY] - Current host: prelander-domain.com
[SECURITY] - Has external referrer: false
[SECURITY] ✗ Access DENIED - no external referrer
[PRELANDER] Skipping fetch - access denied by security check
```

### Blocked Tab (Reload):
```
[SECURITY] ✗ Denied tab - blocking permanently
[PRELANDER] Skipping fetch - access denied by security check
```

## How It Works

### SessionStorage Marker:
- **Key**: `prelander_tab_authorized`
- **Values**: `'granted'`, `'denied'`, or `null` (not set)

### Decision Logic:
```
Component Mount
    ↓
Check sessionStorage marker
    ↓
┌───────────────┬─────────────────┬──────────────────┐
│ Marker Value  │ Action          │ Result           │
├───────────────┼─────────────────┼──────────────────┤
│ 'granted'     │ Allow access    │ Show content ✅  │
│ 'denied'      │ Block forever   │ Blank page ❌    │
│ null (unset)  │ Check referrer  │ See below ↓      │
└───────────────┴─────────────────┴──────────────────┘
                    ↓
        Check document.referrer
                    ↓
┌────────────────────┬──────────────────┬──────────────┐
│ Referrer           │ Action           │ Result       │
├────────────────────┼──────────────────┼──────────────┤
│ External domain    │ Set 'granted'    │ Allow ✅     │
│ Same domain / None │ Set 'denied'     │ Block ❌     │
└────────────────────┴──────────────────┴──────────────┘
```

## Why This Fix Works

### Previous Problem:
- Security check was INSIDE the fetch logic
- Session mode had separate tab marker logic
- Markers could be overwritten on reload

### Current Solution:
1. **Separate useEffect** - Runs before fetch logic
2. **Runs once on mount** - Empty dependency array `[]`
3. **Blocks fetch if denied** - Second useEffect checks `denied` state
4. **Single marker system** - One security marker for all paths
5. **Preserves state** - Once set, marker never changes in that tab

## Troubleshooting

### If Original Tab Gets Blocked:
- Check if browser is blocking sessionStorage
- Check if referrer is being stripped by privacy extensions
- Verify the redirect chain includes external domains

### If New Tab Shows Content:
- Clear browser cache and sessionStorage
- Check browser console for actual log messages
- Verify sessionStorage is enabled in browser settings
- Test in incognito mode to rule out extensions

### If Console Shows Nothing:
- JavaScript might not be loading
- Check browser console for errors
- Verify Next.js is running and compiled

## Browser Compatibility

Works in all modern browsers that support:
- sessionStorage (IE8+, all modern browsers)
- document.referrer (all browsers)

**Note**: Some privacy extensions (uBlock Origin, Privacy Badger) may interfere with referrer detection. This is expected behavior - those users cannot access pasted URLs.
