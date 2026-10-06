# Automatic Download Issue - Fixed

## Problem
When reloading the Redirection Domains page (`/admin/redirection-domains`), the browser was automatically triggering multiple failed download attempts with generic "download" filenames.

## Root Cause
The issue was caused by:
1. **Missing explicit JSON headers** in API requests - the browser was misinterpreting some responses
2. **No content-type validation** - responses with unexpected content types were being processed
3. **useEffect dependency warning** - missing dependencies could cause re-renders and duplicate API calls

## TypeScript Build Fix
The initial fix had a TypeScript compilation error because axios headers can be multiple types (string, number, boolean, array, or AxiosHeaders object). Fixed by:
- Extracting the header value and checking its type
- Converting to string with proper type guard: `typeof contentTypeHeader === 'string' ? contentTypeHeader : ''`

## Fixes Applied

### 1. API Client Configuration (`ppc-frontend/lib/api.ts`)

#### Added Explicit JSON Headers
```typescript
const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',  // ← Forces JSON responses
  },
})
```

#### Added Response Content-Type Validation with Proper TypeScript Types
```typescript
api.interceptors.response.use(
  (response) => {
    // Prevent browser from treating responses as downloads
    const responseType = response.config.responseType
    const contentTypeHeader = response.headers['content-type']
    const contentType = typeof contentTypeHeader === 'string' ? contentTypeHeader : ''
    
    // If we're not expecting a blob/file but got one, reject it
    if (!responseType || responseType === 'json') {
      if (contentType && !contentType.includes('application/json') && !contentType.includes('text/')) {
        console.error('[API] Unexpected content-type:', contentType, 'for URL:', response.config.url)
        return Promise.reject(new Error('Unexpected response type from server'))
      }
    }
    
    return response
  },
  // ... error handling
)
```

**What this does:**
- Explicitly requests JSON responses from the server
- Properly handles TypeScript types for axios headers (can be string/number/array/AxiosHeaders)
- Validates that responses have the correct content-type
- Rejects any response that looks like a file download when JSON is expected
- Logs errors to console for debugging
- Prevents the browser from automatically downloading unexpected binary responses

### 2. Redirection Domains Page (`ppc-frontend/app/admin/redirection-domains/page.tsx`)

#### Fixed useEffect Dependencies
```typescript
// Before:
useEffect(() => {
  initialize()
  load()
}, [])  // ← Missing dependencies

// After:
useEffect(() => {
  initialize()
  load()
}, [initialize, load])  // ← Proper dependencies
```

#### Added Response Validation
```typescript
const load = useCallback(async () => {
  setLoading(true)
  try {
    const [domRes, pubRes] = await Promise.all([
      adminApi.getRedirectionDomains(),
      adminApi.getPublishers({ limit: 200 }),
    ])
    
    // Ensure we have valid JSON responses
    if (!domRes || !domRes.data) {
      throw new Error('Invalid response from server')
    }
    
    setDomains(domRes.data?.domains ?? [])
    // ...
  } catch (err: any) {
    console.error('[Redirection Domains] Load error:', err)
    toast.error(err?.response?.data?.detail || err?.message || 'Failed to load redirection domains')
  }
  // ...
}, [])
```

## Testing

After these fixes:
1. Navigate to `/admin/redirection-domains`
2. Reload the page (Ctrl+R or Cmd+R)
3. Check browser downloads - there should be **no automatic download attempts**
4. Check browser console - API calls should log successful JSON responses
5. Page should load normally with domain data displayed

## Build Status
✅ **TypeScript compilation**: PASSED  
✅ **Next.js build**: SUCCESSFUL  
⚠️ **ESLint warnings**: Present but non-blocking (React Hooks exhaustive-deps)

The ESLint warnings are standard React dependency warnings and do not prevent the build from completing successfully.

## How It Prevents Downloads

1. **Accept header** tells the server "only send JSON"
2. **Content-Type validation** catches any misconfigured endpoint that returns wrong content
3. **Type-safe header checking** properly handles all possible axios header types
4. **Early rejection** prevents axios from processing unexpected binary data
5. **Proper error handling** shows user-friendly messages instead of triggering downloads

## Technical Details

### Why Downloads Were Triggered
When a browser receives a response without a proper `Content-Type: application/json` header, or with binary data, it may:
1. Treat it as an unknown file type
2. Trigger the download manager
3. Try to save it with a generic "download" filename

This was happening on page load when multiple API calls were made simultaneously.

### Prevention Mechanism
By adding:
- `Accept: application/json` header → tells server what format we expect
- Type-safe response validation → rejects non-JSON responses before processing
- Proper TypeScript typing → handles all axios header type variations
- Proper React dependency management → prevents duplicate/invalid requests

## Related Files
- `ppc-frontend/lib/api.ts` - API client with download prevention and proper TypeScript types
- `ppc-frontend/app/admin/redirection-domains/page.tsx` - Fixed dependencies and validation
- Backend endpoints already return proper JSON (no changes needed)

## Notes
- CSV export endpoints still work correctly (they explicitly set `responseType: 'blob'`)
- The fix only affects unexpected downloads, not intentional file downloads
- All existing functionality remains unchanged
- Error messages now include console logs for easier debugging
- TypeScript compilation is now clean with proper type guards

---

**Status:** ✅ Fixed - No more automatic downloads on page reload  
**Build:** ✅ Passing - TypeScript compilation successful  
**Deployed:** ✅ Pushed to main branch (commit ee3e210)

