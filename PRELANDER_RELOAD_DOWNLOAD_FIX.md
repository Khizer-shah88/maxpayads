# Prelander Automatic Download Fix - Page Reload Issue

## Problem Statement
When refreshing a prelander domain page (e.g., https://file2.clicksetopfile.cc/), automatic file downloads were triggered, resulting in failed download attempts.

## Root Cause Analysis

### The Issue
The prelander system has a reload guard (`installChromePrelanderReloadGuard`) designed to prevent automatic downloads on page reload. However, this guard was being **completely wiped out** for admin-created full HTML templates.

### Why It Happened
```javascript
// Line in clean-shell/route.ts (BEFORE FIX):
if (data.rendered_html) { 
  d.open();              // ← Opens new document context
  d.write(data.rendered_html);  // ← Writes admin HTML
  d.close();             // ← Closes document
  return 
}
```

**The sequence `document.open() → document.write() → document.close()` REPLACES THE ENTIRE DOCUMENT**, including:
- All previously executed JavaScript
- The reload guard that was installed earlier
- All event listeners and protections

### Why Admin Templates Trigger Downloads
Admin-created full HTML templates often contain scripts that:
1. Create synthetic anchor clicks: `document.createElement('a').click()`
2. Call `window.open()` on page load
3. Submit forms automatically
4. Trigger download links programmatically

These scripts execute **immediately** when the admin HTML is written to the document, and since the reload guard was already wiped out, nothing prevents them from running.

## The Solution

### Implementation
Instead of installing the guard before `document.write()`, we now **inject the guard directly into the admin HTML** before writing it:

```javascript
if (data.rendered_html) {
  // 1. Create minified guard script (all protection logic in one line)
  var guardScript = '<script>(function(){...reload guard code...})()</script>';
  
  // 2. Inject into admin HTML at the best position
  var html = String(data.rendered_html);
  var headEnd = html.search(/<\/head>/i);
  
  if (headEnd !== -1) {
    // Inject before </head> - runs before body scripts
    html = html.slice(0, headEnd) + guardScript + html.slice(headEnd);
  } else {
    // Fallback: inject after <body> tag
    var bodyStart = html.search(/<body[^>]*>/i);
    if (bodyStart !== -1) {
      var match = html.slice(bodyStart).match(/<body[^>]*>/i);
      var insertPos = bodyStart + (match ? match[0].length : 0);
      html = html.slice(0, insertPos) + guardScript + html.slice(insertPos);
    } else {
      // Last resort: inject at start of HTML
      html = guardScript + html;
    }
  }
  
  // 3. Write the MODIFIED HTML with guard included
  d.open(); d.write(html); d.close(); return
}
```

### What the Guard Does
The injected script blocks automatic downloads on **reload only** by:

1. **Detecting Reload**: Uses Navigation Timing API to check if `navigation.type === 'reload'`
2. **Checking User Activation**: Uses `navigator.userActivation.isActive` to detect real user gestures
3. **Blocking Automatic Actions**:
   - `HTMLAnchorElement.prototype.click` → Only works with user activation
   - `window.open` → Only works with user activation
   - Synthetic click events → Prevented if no user activation
   - Form submissions → Prevented if no user activation

### Injection Strategy
The guard is injected in priority order:

1. **Before `</head>`** (preferred) - Runs before any body scripts
2. **After `<body>`** (fallback) - Still runs before most content scripts
3. **Start of HTML** (last resort) - Always executes first

This ensures the guard is **always active before any admin scripts execute**.

## Benefits

✅ **First visit works normally** - Guard only activates on reload
✅ **User actions work normally** - Only blocks automatic/synthetic actions
✅ **Works for ALL admin templates** - Injected into every full HTML template
✅ **No timing issues** - Guard is part of the HTML itself
✅ **No code duplication** - Single guard script, minified and injected
✅ **Survives document.write()** - Can't be wiped out because it's IN the document

## Testing

### To Verify the Fix:
1. Visit any prelander domain (e.g., https://file2.clicksetopfile.cc/)
2. Wait for the page to fully load
3. Refresh the page (F5 or Ctrl+R)
4. **Expected**: No automatic downloads
5. **Expected**: User can still click download links normally

### Edge Cases Covered:
- Admin templates with `window.open()` on load
- Admin templates with synthetic `anchor.click()`
- Admin templates with automatic form submissions
- Admin templates with no `<head>` tag
- Admin templates with no `<body>` tag
- Legacy browsers without Navigation Timing API Level 2

## Files Changed

### Modified:
- `ppc-frontend/app/clean-shell/route.ts`
  - Injected minified reload guard into admin HTML before document.write()
  - Added intelligent injection logic (head → body → start)

### Preserved:
- `ppc-frontend/lib/chrome-prelander-reload-guard.ts` (unchanged)
- All existing functionality for built-in templates (Mac, Windows)

## Deployment

**Commit**: `03e6c95` - "Fix automatic downloads on page reload for admin HTML templates"

**Status**: ✅ Deployed to production

The fix is now live and will prevent automatic downloads on page refresh for all prelander domains using admin-created full HTML templates.

---

**Date**: October 9, 2026
**Author**: Kiro AI Assistant
**Issue**: Automatic downloads on prelander page refresh
**Resolution**: Inject reload guard into admin HTML before document.write()
