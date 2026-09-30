# Click Validation and Admin Features Fixes

## Summary of Changes

This update implements three critical fixes:

1. **Immediate Valid Status Assignment** - Clicks now show as "valid" immediately when fraud checks pass
2. **Redis Cache Clearing on Stats Deletion** - Users can click again with same IP after admin deletes records
3. **Redirect Chain Name Uniqueness Fix** - Only checks active chains, preventing false "name already exists" errors

---

## 1. Immediate Valid Status Assignment

### Problem
- Clicks were showing as "invalid" on the statistics page even for legitimate new users
- The `status` field was set to "pending" initially
- Background task was supposed to update status to "valid", but this caused delays
- If background task failed or was slow, clicks appeared invalid

### Solution
Set the `status` field to "valid" immediately when fraud detection passes, rather than waiting for the background task.

### Changes Made

**File:** `ppc-backend/app/services/redirect_pipeline.py`

**Before:**
```python
click_data.update({
    "status": ctx.click_status,  # "pending" or "invalid"
    "is_valid": is_click_valid,
    ...
})
```

**After:**
```python
# Set status to "valid" immediately if fraud checks passed
final_status = "valid" if is_click_valid else ctx.click_status

click_data.update({
    "status": final_status,  # "valid", "invalid", or "pending"
    "is_valid": is_click_valid,
    ...
})
```

### Impact
- ✅ Valid clicks now show as "valid" immediately on statistics page
- ✅ No more waiting for background task to update status
- ✅ Background task still updates earnings/CPC, just not validity
- ✅ Invalid clicks still show as "invalid" immediately

---

## 2. Redis Cache Clearing on Stats Deletion

### Problem
- When admin deleted publisher statistics, clicks were removed from database
- BUT Redis duplicate IP cache keys remained active
- Users who clicked before couldn't click again (same IP = duplicate)
- Even though records were deleted and "clean", Redis still blocked them

### Solution
Clear all Redis duplicate IP cache keys for the publisher when deleting statistics.

### Changes Made

**File:** `ppc-backend/app/services/publisher_service.py`

Added Redis cache clearing logic:

```python
async def delete_publisher_stats_only(publisher_id: str, db, redis=None) -> dict:
    """
    Delete only statistics data for a publisher.
    Also clears Redis duplicate IP cache so users can click again with same IP.
    """
    
    # Get all unique IPs from clicks before deleting
    unique_ips = set()
    if redis:
        try:
            from app.core.constants import REDIS_DUPLICATE_CLICK_PREFIX
            from datetime import datetime, timezone
            
            # Get all IPs for this publisher
            cursor = db.clicks.find({"publisher_id": id_match}, {"ip_address": 1})
            async for click in cursor:
                if click.get("ip_address"):
                    unique_ips.add(click["ip_address"])
            
            # Clear Redis duplicate IP keys
            # Key format: prefix:ip:publisher:YYYY-MM-DD
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            cleared_keys = 0
            for ip in unique_ips:
                key = f"{REDIS_DUPLICATE_CLICK_PREFIX}{ip}:{publisher_id}:{today}"
                if await redis.delete(key):
                    cleared_keys += 1
            
            logger.info(f"Cleared {cleared_keys} Redis duplicate IP keys")
        except Exception as e:
            logger.warning(f"Failed to clear Redis cache: {e}")
    
    # Continue with normal deletion...
    clicks_result = await db.clicks.delete_many({"publisher_id": id_match})
    ...
```

**File:** `ppc-backend/app/routers/admin_router.py`

Updated endpoint to pass Redis client:

```python
@router.delete("/publishers/{publisher_id}/stats")
async def delete_publisher_stats(
    publisher_id: str,
    current_user: dict = Depends(get_current_admin),
    db=Depends(get_db),
    redis=Depends(get_redis_client),  # Added
):
    ...
    result = await delete_publisher_stats_only(publisher_id, db, redis)  # Pass redis
```

### Redis Key Format
```
duplicate_click:192.168.1.100:PUB_ABC123:2026-10-01
└─────────────┘ └───────────┘ └────────┘ └────────┘
     prefix          IP       publisher     date
```

### Impact
- ✅ When admin deletes stats, Redis cache is automatically cleared
- ✅ Users can immediately click again with same IP
- ✅ Data is truly "clean" - both database and cache
- ✅ Graceful fallback if Redis is unavailable (logs warning, continues deletion)

---

## 3. Redirect Chain Name Uniqueness Fix

### Problem
- Creating a new redirect chain showed "name already exists" error
- Even when NO active chain had that name
- The check was finding INACTIVE chains with the same name
- Inactive chains shouldn't block new chain creation

### Solution
Only check active chains for name uniqueness. Inactive chains can have duplicate names.

### Changes Made

**File:** `ppc-backend/app/routers/redirect_chain_router.py`

#### Create Endpoint Fix

**Before:**
```python
existing = await db.redirect_chains.find_one({"name": name})
if existing:
    raise HTTPException(
        status_code=400,
        detail="A redirect chain with this name already exists"
    )
```

**After:**
```python
# Only check active chains - inactive chains can have duplicate names
existing = await db.redirect_chains.find_one({
    "name": name,
    "status": "active"
})
if existing:
    raise HTTPException(
        status_code=400,
        detail="A redirect chain with this name already exists"
    )
```

#### Update Endpoint Fix

**Before:**
```python
name_exists = await db.redirect_chains.find_one({
    "name": name,
    "_id": {"$ne": object_id}
})
```

**After:**
```python
# Check name uniqueness (excluding current chain, only check active chains)
name_exists = await db.redirect_chains.find_one({
    "name": name,
    "_id": {"$ne": object_id},
    "status": "active"
})
```

### Impact
- ✅ Can create new chains even if inactive chains have same name
- ✅ No more false "name already exists" errors
- ✅ Update endpoint also fixed with same logic
- ✅ Active chains still have unique names (as intended)

---

## 4. Smartlink Domain Configuration (Already Working!)

### Question
"How to use custom domain for smartlinks instead of hardcoded domain?"

### Answer
**This feature already exists!** The system automatically uses configured Anchor domains.

### How It Works

1. **Admin adds domain** in "Redirection Domains" page:
   - Domain: `your-domain.com`
   - Type: **Anchor**
   - Status: **Active**

2. **System automatically uses it** when generating smartlinks:
   - Smartlinks use `resolve_domain_url()` function
   - This function queries active Anchor domains from database
   - No hardcoded domain anywhere in the code

3. **Priority order:**
   - Publisher-specific domains (if assigned)
   - Default domains (marked as `is_default`)
   - Any active unassigned domain from the pool

### Code Reference

**File:** `ppc-backend/app/services/smartlink_parser.py`

```python
async def generate_smartlink(...):
    if not domain:
        from app.core.constants import DOMAIN_TYPE_ANCHOR
        from app.services.domain_service import resolve_domain_url
        # Automatically resolves from active Anchor domains in database
        domain = await resolve_domain_url(db, DOMAIN_TYPE_ANCHOR, None)
```

**File:** `ppc-backend/app/services/domain_service.py`

```python
async def resolve_domain_url(db, domain_type, publisher_id):
    """
    Resolve the best active domain URL for a publisher.
    Priority: publisher-assigned → global default → active unassigned pool.
    """
    base_query = {
        "domain_type": domain_type_filter(canonical_type),
        "status": "active"
    }
    # Returns URL from database, not hardcoded
    ...
```

### Usage Instructions

1. Go to **Admin Dashboard → Redirection Domains**
2. Click **"Add Domain"**
3. Fill in:
   - **Domain:** `your-domain.com` (without https://)
   - **Type:** Select **"Anchor"**
   - **Status:** Set to **"Active"**
4. Click **"Save"**
5. Smartlinks will now automatically use your domain!

**Example:**
- Before: `https://clickspot.icu/click?pub=PUB_123...`
- After: `https://your-domain.com/click?pub=PUB_123...`

---

## Testing Checklist

### 1. Valid Click Status
- [ ] Click a publisher link from a new IP/device
- [ ] Check admin statistics page immediately
- [ ] Status should show "valid" (not "pending" or "invalid")
- [ ] Earnings should be credited (after background task)

### 2. Redis Cache Clearing
- [ ] Click a publisher link (gets marked as duplicate for today)
- [ ] Try clicking again (should be blocked as duplicate)
- [ ] Admin deletes publisher statistics
- [ ] Try clicking again (should now work and show as valid)

### 3. Redirect Chain Name
- [ ] Create a chain with name "Test Chain", set to Active
- [ ] Deactivate that chain (status = "inactive")
- [ ] Create a NEW chain with same name "Test Chain"
- [ ] Should succeed without "name already exists" error

### 4. Custom Smartlink Domain
- [ ] Add your domain in Redirection Domains (Type: Anchor, Status: Active)
- [ ] Generate a new smartlink for any publisher
- [ ] Verify smartlink uses your custom domain
- [ ] Click the smartlink and verify it works

---

## Rollback Plan

If issues occur, you can revert specific changes:

### Revert Click Status Fix
```python
# In redirect_pipeline.py, change back to:
click_data.update({
    "status": ctx.click_status,  # Old behavior
    "is_valid": is_click_valid,
    ...
})
```

### Disable Redis Cache Clearing
```python
# In publisher_service.py, remove redis parameter:
async def delete_publisher_stats_only(publisher_id: str, db) -> dict:
    # Don't clear Redis cache
    ...
```

### Revert Chain Name Check
```python
# In redirect_chain_router.py, remove status filter:
existing = await db.redirect_chains.find_one({"name": name})
# Will check all chains (active + inactive)
```

---

## Files Modified

1. `ppc-backend/app/services/redirect_pipeline.py`
   - Set status to "valid" immediately when fraud checks pass

2. `ppc-backend/app/services/publisher_service.py`
   - Added Redis duplicate IP cache clearing on stats deletion
   - Added `redis` parameter to `delete_publisher_stats_only()`

3. `ppc-backend/app/routers/admin_router.py`
   - Updated delete stats endpoint to pass Redis client
   - Added import for `get_redis_client`

4. `ppc-backend/app/routers/redirect_chain_router.py`
   - Fixed name uniqueness check to only check active chains
   - Applied to both create and update endpoints

---

## Deployment

Changes have been pushed to main branch:

```bash
git push origin main
```

**Commit:** `ddf10fb - Implement multiple fixes for click validation and admin features`

The changes will take effect after:
1. Backend service restart OR
2. Auto-deployment (if configured)

---

## Additional Notes

- All changes are backward compatible
- No database migrations required
- Redis cache clearing is fail-safe (continues deletion even if Redis fails)
- Smartlink domain feature requires no code changes - just configure domains in admin panel

---

## Support

If you encounter any issues:

1. **Check logs** for errors related to click validation or Redis
2. **Verify Redis is running** if cache clearing isn't working
3. **Ensure domains are Active** in Redirection Domains page for smartlinks
4. **Test with different IPs/browsers** to rule out caching issues
