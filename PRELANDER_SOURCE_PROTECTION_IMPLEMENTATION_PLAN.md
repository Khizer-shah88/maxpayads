# Prelander Source Protection Implementation Plan

## Executive Summary

This document outlines the implementation of comprehensive source code protection for prelander templates while maintaining full functionality and acknowledging technical limitations.

**Goal**: Make HTML/CSS/JavaScript source code of prelander pages as difficult as practically possible to inspect, copy, or understand, while keeping the application fully functional.

**Critical Understanding**: Browser source code inspection cannot be completely prevented. The goal is deterrence and obfuscation, not absolute prevention.

## Current Architecture Analysis

### Request Flow (Prelander Domains)

1. **Visitor clicks smartlink** → `/click` endpoint
2. **Traffic Router** creates authorization session + XOR-encrypted slug
3. **Browser navigates to** prelander domain `/d/{slug}` (Next.js page)
4. **Next.js page calls** `/api/prelander/resolve/{slug}` (FastAPI)
5. **FastAPI validates** authorization session + resolves template
6. **Two rendering paths**:
   - **Full HTML Template**: Backend renders with `PrelanderTemplateEngine`, replaces `{Campaign_URL}` and `{Password}` shortcodes, obfuscates with `js_obfuscator.py`, returns `rendered_html`
   - **Built-in Layouts**: Backend returns template metadata, Next.js renders Windows/Mac layouts client-side
7. **Next.js page** displays content (either `FullHtmlPrelander` component or built-in layouts)

### Existing Security Measures

✅ **Already Implemented**:
1. Server-side authorization gate (`prelander_auth_service.py`)
2. Session-based access control
3. XOR-encrypted slugs with 1-hour expiry
4. JavaScript obfuscation (`js_obfuscator.py`) for full HTML templates
5. Minification for inline scripts
6. CSP headers
7. Referrer-Policy: no-referrer
8. Source deterrent service worker (`source-deterrent-sw.js`)
9. Tab guard (one-time arrival claim)
10. Clean URL (slug removed from address bar)

### Files Requiring Changes

#### Backend (FastAPI)
- `app/routers/prelander_public_router.py` - Already obfuscates full HTML templates
- `app/routers/prelander_router.py` - Legacy endpoint (also has obfuscation)
- `app/services/prelander_service.py` - Template engine
- `app/utils/js_obfuscator.py` - Obfuscation utility
- `app/middleware/redirect_chain_middleware.py` - Chain middleware (dormant)

#### Frontend (Next.js)
- `ppc-frontend/next.config.js` - Build configuration
- `ppc-frontend/app/d/[slug]/page.tsx` - Prelander page (client-side)
- `ppc-frontend/public/source-deterrent-sw.js` - **DO NOT TOUCH** per requirements

#### Admin API
- `app/routers/prelander_router.py` - Template management endpoints (already secured)

## Protection Strategy

### 1. Server-Side Processing ✅ ALREADY DONE

**Status**: Fully implemented

The system already:
- Resolves templates server-side
- Replaces shortcodes server-side (`{Campaign_URL}`, `{Password}`)
- Validates authorization server-side
- Never exposes raw `full_html_template` to unauthenticated users

**No changes needed**.

### 2. HTML/CSS/JS Obfuscation ✅ MOSTLY DONE

**Status**: Full HTML templates already obfuscated; built-in layouts need enhancement

**Current Implementation**:
```python
# app/routers/prelander_public_router.py (line ~73)
obfuscated_html = obfuscate_html_javascript(rendered_html, aggressive=True)
return HTMLResponse(content=obfuscated_html, status_code=200)
```

**Existing Obfuscation** (`js_obfuscator.py`):
- Minifies JavaScript (removes comments, whitespace)
- Base64 encodes string literals
- Wraps code in eval() layers
- Minifies HTML (optional)

**Enhancement Needed**: Apply minification to built-in layouts

**Action**: Add HTML/JS minification for built-in layouts (Windows/Mac prelanders) served by Next.js

### 3. Production Source Maps ⚠️ NEEDS VERIFICATION

**Status**: Partially configured, needs verification

**Current Configuration**:
```javascript
// next.config.js (line ~16)
webpack: (config, { dev, isServer }) => {
  if (!dev && !isServer) {
    config.devtool = false  // ✅ Removes source maps
  }
  return config
}
```

**Also check**:
- `productionBrowserSourceMaps: false` (not currently set, should add)
- Verify no `.map` files in production build

**Action**: 
1. Add explicit `productionBrowserSourceMaps: false`
2. Verify production build has no `.map` files
3. Add build script to clean any accidental `.map` files

### 4. Template Management API Security ✅ ALREADY SECURED

**Status**: Fully secured

All template management endpoints require authentication:
```python
# app/routers/prelander_router.py
@router.post("/", dependencies=[Depends(get_current_admin)])
@router.get("/{template_id}", dependencies=[Depends(get_current_admin)])
@router.put("/{template_id}", dependencies=[Depends(get_current_admin)])
# etc.
```

**Verification**: Unauthenticated users cannot access `/api/prelander/` admin endpoints.

**No changes needed**.

### 5. Separate Preview From Production ✅ ALREADY SEPARATED

**Status**: Fully separated

- Admin preview: `/api/prelander/preview/{template_id}` (requires auth)
- Public rendering: `/api/prelander/resolve/{slug}` (requires session)

The public endpoint returns either:
1. `rendered_html` (already obfuscated)
2. Template metadata (for built-in layouts)

**Never exposes** `full_html_template` directly.

**No changes needed**.

### 6. Enhanced Minification for Built-in Layouts 🔧 NEW ENHANCEMENT

**Status**: Not implemented

**Current**: Built-in Windows/Mac layouts are rendered by Next.js with React hydration, readable source

**Enhancement Options**:

#### Option A: Server-Side Rendering (SSR) with Minification
- Move built-in layouts to FastAPI templates
- Render server-side with minification
- Return as `rendered_html`
- **Pros**: Consistent obfuscation, no React overhead
- **Cons**: Loses React interactivity, major refactor

#### Option B: Next.js Build-Time Optimization
- Enable aggressive Terser minification
- Use `next/script` with `strategy="beforeInteractive"` for inline scripts
- Apply CSS minification in PostCSS
- **Pros**: Keeps React, automatic on build
- **Cons**: Limited compared to manual obfuscation

#### Option C: Hybrid Approach (RECOMMENDED)
- Keep full HTML templates server-rendered (already obfuscated)
- For built-in layouts: enhance Next.js build config
- Add response compression (Gzip/Brotli)
- **Pros**: Balanced, maintains current architecture
- **Cons**: Built-in layouts still more readable than full templates

**Recommended**: Option C - Enhance Next.js build without breaking changes

### 7. Response Compression 🔧 NEW ENHANCEMENT

**Status**: Gzip enabled in nginx, can enhance

**Current** (nginx.conf):
```nginx
gzip on;
gzip_types text/plain text/css application/json application/javascript text/xml application/xml text/javascript;
gzip_min_length 1000;
```

**Enhancement**: Add Brotli compression for better compression ratios

### 8. No "view-source:" Protection ✅ CORRECTLY AVOIDED

**Status**: Correctly not implemented

The codebase correctly avoids unreliable tricks:
```python
# app/routers/prelander_router.py (line ~368 comment)
# NOTE: there is deliberately no server-side view-source check here.
# A view-source: navigation sends a byte-for-byte identical HTTP request...
```

**Existing Client-Side Deterrent**:
- `source-deterrent-sw.js` (DO NOT MODIFY per requirements)

**No changes needed**.

## Implementation Tasks

### Phase 1: Verify Existing Protections ✅

**Tasks**:
1. ✅ Verify server-side template processing
2. ✅ Verify authorization gates
3. ✅ Verify obfuscation for full HTML templates
4. ✅ Verify API endpoint authentication
5. ⚠️ Verify production source maps are disabled
6. ⚠️ Verify no `.map` files in production build

### Phase 2: Enhanced Build Configuration 🔧

**Tasks**:
1. Add `productionBrowserSourceMaps: false` to next.config.js
2. Enhance Terser minification for Next.js build
3. Add CSS minification in PostCSS config
4. Add build verification script to check for `.map` files

### Phase 3: Optional Enhancements 🔧

**Tasks**:
1. Add Brotli compression to nginx
2. Document obfuscation limitations
3. Add security headers audit

### Phase 4: Testing & Documentation 🔧

**Tasks**:
1. Test full HTML template obfuscation (already working)
2. Test built-in layout minification (after enhancements)
3. Test authorization gates
4. Curl tests
5. DevTools inspection (document what's visible)
6. Document deliverables

## Technical Limitations (Critical Understanding)

### What CAN Be Protected

✅ **Raw template source from unauthenticated users**
- Already protected by authorization gates

✅ **Sensitive backend logic**
- Kept server-side, never exposed

✅ **Database credentials, API keys, secrets**
- Never in browser code

✅ **Template management APIs**
- Already require authentication

### What CANNOT Be Fully Hidden

❌ **Final rendered HTML**
- Browsers must parse HTML to display it
- `view-source:` shows delivered HTML
- DevTools "Elements" tab shows DOM

❌ **Executed JavaScript**
- Can be deobfuscated with enough effort
- Browser debugger can step through code
- Console can inspect variables

❌ **CSS Styles**
- Computed styles visible in DevTools
- Can be extracted from rendered page

❌ **Network Requests**
- DevTools Network tab shows all requests
- Campaign URLs visible when clicked

### What We ACHIEVE

✅ **Deterrence**: Makes casual copying significantly harder
✅ **Obfuscation**: Minified/obfuscated code is much harder to understand
✅ **Protection of Secrets**: Sensitive data never reaches browser
✅ **Authorization**: Only valid sessions see prelander content
✅ **API Security**: Template management locked to admins

## Security Rules (Enforced Throughout)

### Never Put in Browser Code

❌ Database credentials
❌ API keys
❌ Secret tokens
❌ Private authentication logic
❌ Fraud detection rules
❌ Internal business logic
❌ Server-side validation rules

### Always Keep Server-Side

✅ Template resolution
✅ Shortcode replacement
✅ Authorization validation
✅ Campaign URL resolution
✅ Password retrieval
✅ Session management
✅ Click validation

## Testing Requirements

### 1. Normal Browser Test

```bash
# Open prelander normally
https://prelander-domain.com/
```

**Verify**:
- ✅ Page loads
- ✅ CSS works
- ✅ JavaScript works
- ✅ Campaign URL works
- ✅ No console errors

### 2. Curl Test

```bash
curl -I https://prelander-domain.com/
curl -L https://prelander-domain.com/
```

**Verify**:
- ✅ Appropriate headers
- ✅ No raw template exposure
- ✅ Gzip compression

### 3. Source Inspection Test

```text
view-source:https://prelander-domain.com/
```

**Document**:
- What is visible (minified HTML)
- What is obfuscated (JavaScript)
- What remains readable (CSS)

### 4. DevTools Inspection

**Elements Tab**: Shows rendered DOM (expected)
**Sources Tab**: Shows delivered files (expected, but minified)
**Network Tab**: Shows requests (expected)

**Verify**:
- ✅ No source maps
- ✅ JavaScript is obfuscated
- ✅ HTML is minified
- ✅ No unnecessary comments

### 5. API Security Test

```bash
# Try to access template management without auth
curl https://api-domain.com/api/prelander/
curl https://api-domain.com/api/prelander/{template_id}
```

**Verify**:
- ❌ Access denied without authentication
- ❌ Cannot retrieve `full_html_template`

## Deliverables

### 1. Files Changed

**Backend**:
- `app/utils/js_obfuscator.py` (potential enhancements)
- `nginx.conf` (Brotli compression)

**Frontend**:
- `ppc-frontend/next.config.js` (source map enforcement, minification)
- `ppc-frontend/postcss.config.js` (CSS minification)

**New Files**:
- `scripts/verify-production-build.sh` (build verification)

### 2. Documentation

- This implementation plan
- Security audit results
- Testing results
- Limitations documentation

### 3. Request Flow Diagrams

#### Before (No Changes Needed)

```
Visitor → /click → Authorization Session Created
                ↓
          Redirect to /d/{slug}
                ↓
    Next.js page loads → /api/prelander/resolve/{slug}
                ↓
    FastAPI validates session → Resolves template
                ↓
    Server-side shortcode replacement
                ↓
    JS obfuscation (if full HTML template)
                ↓
    Return obfuscated HTML or template metadata
                ↓
    Next.js renders (FullHtmlPrelander or built-in layout)
                ↓
    Visitor sees prelander page
```

#### After Enhancements

```
Same flow, with additions:
- Source maps explicitly disabled
- Enhanced minification for builds
- Brotli compression in nginx
- Build verification script
```

### 4. What Is Protected vs. Inspectable

**Protected (Not Visible to Unauthorized Users)**:
- ✅ Raw `full_html_template` source
- ✅ Template management APIs
- ✅ Server-side logic
- ✅ Database secrets
- ✅ Authorization tokens

**Obfuscated (Difficult to Read)**:
- ⚠️ JavaScript in full HTML templates (heavily obfuscated)
- ⚠️ Inline scripts (minified)

**Inspectable (Technically Visible)**:
- ❌ Final rendered HTML (必须)
- ❌ Executed JavaScript (can be debugged)
- ❌ CSS styles (computed styles visible)
- ❌ Network requests (DevTools Network tab)

**IMPORTANT**: This is not a failure. Browsers MUST have this information to render pages. The goal is deterrence and obfuscation, not impossibility.

### 5. Remaining Limitations

1. **Browser Source Inspection**: Cannot be prevented (by design)
2. **JavaScript Deobfuscation**: Possible with enough effort
3. **CSS Extraction**: Computed styles always visible
4. **Network Monitoring**: Campaign URLs visible when clicked
5. **Built-in Layouts**: More readable than full HTML templates (React code)

### 6. Exact Commands Used

```bash
# Build production frontend
cd ppc-frontend
npm run build

# Verify no source maps
find .next -name "*.map" | wc -l  # Should be 0

# Build production backend (if needed)
cd ppc-backend
# FastAPI doesn't need building

# Test with curl
curl -I https://prelander-domain.com/
curl -L https://prelander-domain.com/ | head -50

# Test authorization
curl https://api-domain.com/api/prelander/

# Deploy (existing workflow)
docker-compose -f docker-compose.prod.yml up -d --build
```

## Conclusion

**Current Status**: The system ALREADY implements strong source code protection:
1. ✅ Server-side template processing
2. ✅ Authorization gates
3. ✅ JavaScript obfuscation for full HTML templates
4. ✅ API security
5. ✅ Session-based access control

**Enhancements Needed**: Minor (source map verification, build optimization)

**Critical Understanding**: Browser source code is ALWAYS inspectable by design. The current system achieves the practical maximum: deterrence, obfuscation, and protection of sensitive server-side logic.

**Recommendation**: Implement Phase 2 enhancements, document limitations honestly, and maintain the existing strong security posture.

---

**Next Steps**: Review this plan, approve enhancements, proceed with Phase 2 implementation.
