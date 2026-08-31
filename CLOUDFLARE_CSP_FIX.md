# Cloudflare CSP Fix - Required Action

## Problem
The Content Security Policy (CSP) is blocking JavaScript execution on vertexmonetize.com, causing the application to fail with:
```
Content Security Policy blocks the use of 'eval' in JavaScript
```

## Root Cause
Cloudflare is adding a restrictive CSP header that blocks `unsafe-eval`, which Next.js requires for proper functionality.

## Solution

You need to disable or modify the CSP in your Cloudflare dashboard:

### Option 1: Disable CSP (Recommended for Now)

1. Log in to your Cloudflare dashboard
2. Select your domain: **vertexmonetize.com**
3. Go to **Security** → **Page Rules** or **Security** → **Settings**
4. Look for **Content Security Policy** settings
5. **Disable** CSP or set it to **Report Only** mode

### Option 2: Modify CSP to Allow Next.js

If you want to keep CSP enabled, add these directives:

```
Content-Security-Policy: 
  default-src 'self';
  script-src 'self' 'unsafe-inline' 'unsafe-eval';
  style-src 'self' 'unsafe-inline';
  img-src 'self' data: blob: https:;
  font-src 'self' data: https://fonts.gstatic.com;
  connect-src 'self' https:;
  frame-src 'self';
```

**Important:** The key directive is `script-src 'self' 'unsafe-inline' 'unsafe-eval'`

### Where to Find CSP Settings in Cloudflare

1. **Dashboard** → **Security** → **Page Rules**
2. **Dashboard** → **Security** → **Settings** → **Security Headers**
3. **Dashboard** → **Rules** → **Transform Rules** → **HTTP Response Header Modification**

### Testing After Changes

1. Clear your browser cache and cookies
2. Open Developer Console (F12)
3. Navigate to https://vertexmonetize.com/admin/direct-link-stats
4. Check if the CSP error is gone

## Technical Details

Next.js uses `eval()` and `new Function()` for:
- Hot Module Replacement (HMR) in development
- Code splitting and dynamic imports
- Runtime optimizations

Without `unsafe-eval`, the app cannot execute properly.

## Temporary Workaround

If you cannot access Cloudflare settings immediately, you can:
1. Bypass Cloudflare temporarily using the origin server IP
2. Use Cloudflare's "Development Mode" which bypasses some security features

## Verification

After fixing CSP, you should see:
- ✅ No CSP errors in browser console
- ✅ JavaScript executes normally
- ✅ Pages load without "Application error" message
- ✅ All interactive features work

## Contact

If you need help with Cloudflare settings, contact your Cloudflare administrator or support.
