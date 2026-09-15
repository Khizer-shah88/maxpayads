# Campaign URL Resolution & Loader Fixes

## Issues Fixed

### 1. Campaign URL Resolution Bug
**Problem**: When clicking through redirect chains, the prelander page was showing `https://example.com/offer` instead of the actual campaign URL configured in the admin panel.

**Root Cause**: In `app/routers/prelander_router.py`, when resolving prelander data, the code was looking up the campaign from the slug but only extracting the campaign name and password - NOT the campaign URL itself. This caused the system to fall through to the fallback logic which would either find a different campaign or use the hardcoded fallback URL.

**Fix**: Modified the campaign resolution logic (step 3 in `_get_prelander_data`) to extract the campaign URL from the campaign document when no more specific offer URL or geo rule was matched. The logic now:

1. Looks up campaign by ID from slug
2. Extracts campaign name for display
3. **NEW**: Extracts campaign URL (trying `default_offer_url`, `offer_url`, `url` fields in that order)
4. Extracts password if not already set

**Changes in `/app/routers/prelander_router.py`**:
- Line ~395-412: Enhanced campaign lookup to extract URL
- Added comprehensive logging to track campaign resolution
- Added logging to offer lookup (step 1)
- Added logging to fallback campaign search (step 4)

### 2. Enhanced Logging
Added detailed logging throughout the campaign resolution flow to help diagnose issues:
- Logs when offer is found/not found from slug
- Logs when campaign is found/not found from slug  
- Logs the actual campaign URL before cleaning
- Logs warnings when campaign has no URL configured
- Logs each fallback attempt (by OS, global, any active)

### 3. Loader Display
**Status**: No changes needed - loader is working correctly

The loader on inter domains was already properly implemented:
- Shows when `transitioning = true` 
- Displays for exactly 750ms (0.75 seconds) as specified
- Clean, professional design with gradient background
- Consistent across both redirect states (inter→prelander and bypass mode)

**Flow**:
1. `/d/[slug]` page loads on inter domain
2. Calls `/api/prelander/domain-type` to check domain type
3. Detects it's not on prelander domain
4. Sets `transitioning = true` → shows loader
5. Waits 750ms
6. Redirects to prelander domain OR campaign URL (depending on bypass mode)

## Testing

All prelander system tests pass:
```bash
pytest tests/test_prelander_system.py -xvs
# 32 tests passed
```

## Campaign URL Priority Order

The system now correctly follows this priority order for URL resolution:

1. **Specific Offer** (from slug offer_id) - highest priority
   - When targeting engine matched a specific offer
   
2. **GEO Rule** (country-specific)
   - When campaign has country-specific URLs configured
   
3. **Campaign from Slug** (NEW FIX)
   - When slug contains campaign_id and no more specific match
   - Uses campaign's `default_offer_url` → `offer_url` → `url`
   
4. **Fallback Campaign** (domain/OS matching)
   - Tries to find campaign by landing page domain
   - Then by device OS (windows/mac)
   - Then by global OS setting
   - Finally any active campaign
   
5. **Global Fallback**
   - `https://example.com/campaign-not-configured` (should rarely happen)

## URL Field Compatibility

The code checks multiple field names for backward compatibility:
- `default_offer_url` (current standard)
- `offer_url` (legacy)
- `url` (older legacy)

## Deployment Notes

After deploying these changes:
1. Monitor logs for the new `[PRELANDER]` log lines
2. Verify campaign URLs are being resolved correctly
3. Check that the 750ms loader displays on inter domains
4. Confirm bypass mode still works (direct to campaign URL)

## Related Files
- `/app/routers/prelander_router.py` - Main fix location
- `/app/services/traffic_router.py` - Campaign routing logic
- `/ppc-frontend/app/d/[slug]/page.tsx` - Loader display (no changes needed)

## User Impact
- ✅ Campaign URLs configured in admin panel now work correctly
- ✅ Clear logging helps diagnose any remaining issues
- ✅ Loader provides smooth user experience during redirects
- ✅ All existing functionality preserved (geo rules, offer targeting, bypass mode)
