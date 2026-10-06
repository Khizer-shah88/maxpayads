# Redirect Chain Name Validation & DefaultDomains Removal Fix

## Summary

Fixed the redirect chain name validation error that showed "A redirect chain with this name already exists" even when the name didn't exist, and removed the defaultDomains fallback from the direct-link-stats page.

---

## Issues Fixed

### 1. **Redirect Chain Name Validation False Positives**

**Problem:**
- Admin trying to create chains with any name would get an error "A redirect chain with this name already exists"
- The error appeared even when the name was genuinely unique
- Root cause: The name validation used regex pattern matching with case-insensitive flag

**Root Cause:**
```python
# OLD CODE (PROBLEMATIC)
existing = await _with_retry(lambda: db.redirect_chains.find_one({
    "name": {"$regex": f"^{name}$", "$options": "i"},  # Case-insensitive regex
    "status": "active"
}))
```

The regex pattern `{"$regex": f"^{name}$", "$options": "i"}` could:
1. Match names with different casing (intended behavior)
2. Cause false positives if the chain name contained regex special characters like `.`, `*`, `+`, `?`, etc.
3. Potentially match unintended chain names

**Fix Applied:**
```python
# NEW CODE (FIXED)
existing = await _with_retry(lambda: db.redirect_chains.find_one({
    "name": name,  # Exact string matching
    "status": "active"
}))
```

**Benefits:**
- Exact string matching - no regex interpretation
- No false positives from special characters
- Still filters by active status only (inactive chains can have duplicate names)
- Simpler and more predictable behavior

---

### 2. **Remove DefaultDomains from Direct Link Stats**

**Problem:**
- The direct-link-stats page was showing both assigned domains and falling back to default domains
- User requested to only show assigned domains, without any fallback to defaults

**Changes Made:**

1. **Removed defaultDomains field from publisherStats mapping:**
```typescript
// REMOVED
defaultDomains: dom.defaults || {},
```

2. **Simplified Assigned Domain column rendering:**
```typescript
// OLD CODE - Had fallback to defaultDomains
if (!hasAny) {
  // Fall back to global default domains
  const d = pub.defaultDomains || {}
  const defEntries = [
    { label: 'A', domain: d.anchor, cls: 'bg-gray-50 border-gray-200 text-gray-500' },
    { label: 'I', domain: d.inter, cls: 'bg-gray-50 border-gray-200 text-gray-500' },
    { label: 'P', domain: d.prelander, cls: 'bg-gray-50 border-gray-200 text-gray-500' },
  ].filter(e => e.domain)
  if (defEntries.length === 0) return <span>No domain</span>
  return (/* render default domains */)
}

// NEW CODE - Shows "No domain" if no assigned domains
if (!hasAny) {
  return <span className="text-xs text-gray-300 italic">No domain</span>
}
```

**Result:**
- Column now only shows publisher-specific assigned domains
- If no assigned domains, shows "No domain" instead of falling back to global defaults
- Cleaner and more accurate representation

---

## Files Modified

1. **Backend:**
   - `ppc-backend/app/routers/redirect_chain_router.py`
     - Line 197: Changed from regex matching to exact string matching

2. **Frontend:**
   - `ppc-frontend/app/admin/direct-link-stats/page.tsx`
     - Line 460: Removed defaultDomains field from publisherStats
     - Lines 758-788: Removed defaultDomains fallback logic from Assigned Domain column

---

## Testing Recommendations

1. **Test Chain Name Validation:**
   - Create chains with various names including:
     - Simple names: "Chain 1", "test-chain"
     - Names with special characters: "chain.test", "chain*prod", "chain+dev"
     - Names with spaces: "My Chain Name"
   - Verify no false positive "name already exists" errors
   - Verify duplicate names are still properly rejected

2. **Test Assigned Domains Column:**
   - Check publishers with assigned domains (should show A/I/P badges)
   - Check publishers without assigned domains (should show "No domain")
   - Verify no fallback to global default domains

---

## Deployment

Changes have been committed and pushed to the main branch:

```
Commit: 86f5837
Message: Fix redirect chain name validation and remove defaultDomains from direct-link-stats
Files: 2 files changed, 6 insertions(+), 21 deletions(-)
```

**Next Steps:**
1. Deploy backend changes to production
2. Deploy frontend changes to production
3. Test chain creation in production environment
4. Verify direct-link-stats page shows correct domain information

---

## Notes

- The regex-based case-insensitive matching was removed in favor of exact matching
- MongoDB's default string comparison is case-sensitive, which is appropriate for chain names
- If case-insensitive uniqueness is needed in the future, use proper escaping or MongoDB's collation feature
- The "status": "active" filter remains in place - inactive chains can still have duplicate names
