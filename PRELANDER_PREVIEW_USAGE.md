# Prelander Template Preview - How to Test Templates

## Problem Fixed
The prelander system requires visitors to go through the click flow (/click → anchor → inter → prelander) with proper authorization. This prevents directly accessing prelander domains to test templates, resulting in 404 errors.

## Solution: Preview Mode
I've added a **preview mode** that bypasses authorization, allowing you to test template assignments directly on prelander domains.

## How to Use

### Option 1: Preview Page (Recommended)
Visit your prelander domain with the `/preview` path:

```
https://your-prelander-domain.com/preview?os=windows
https://your-prelander-domain.com/preview?os=mac
```

**Examples:**
- `https://clickfilesetup.info/preview?os=windows`
- `https://rydestudio.info/preview?os=mac`

### Option 2: API Endpoint (For Testing)
Call the preview API directly:

```
GET /api/prelander/preview?os=windows
GET /api/prelander/preview?os=mac
```

## What It Does

The preview mode:
1. ✅ Bypasses click-based authorization
2. ✅ Shows the template assigned to that prelander domain
3. ✅ Uses the OS parameter to determine which template to load (windows/mac)
4. ✅ Displays actual campaign URL and password (if configured)
5. ✅ Renders full HTML templates with shortcode substitution

## Testing Your Templates

1. **Go to Admin → Landing Pages** (`https://vertexmonetize.com/admin/landing-pages`)
2. **Assign templates** to your prelander domains
3. **Visit the preview URL** for that domain:
   - For Windows templates: `https://your-domain.com/preview?os=windows`
   - For Mac templates: `https://your-domain.com/preview?os=mac`

## Production Flow (Normal Click Flow)
The preview mode is ONLY for testing. Real visitors should go through the normal flow:

```
Publisher Site → /click → Anchor Domain → Inter Domain → Prelander Domain
```

This flow includes:
- Click tracking
- Targeting rules
- GEO routing
- Authorization validation
- Conversion tracking

## Notes

- Preview mode shows "Template Preview Mode" at the bottom
- Console logs show `[PREVIEW]` prefix for debugging
- No click tracking or conversion tracking in preview mode
- Safe for testing - doesn't affect production traffic

## Troubleshooting

If preview still shows an error:
1. Check that the domain is configured as "Prelander" type in Admin → Redirection Domains
2. Check that a template is assigned to that domain in Admin → Landing Pages
3. Check browser console for `[PREVIEW]` debug logs
4. Verify the domain status is "Active"

---

**Important:** Preview mode is for testing only. Real traffic should ALWAYS go through the click flow for proper tracking and authorization.
