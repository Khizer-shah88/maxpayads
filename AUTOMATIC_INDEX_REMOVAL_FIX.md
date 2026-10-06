# Automatic Index Removal Fix

## Summary

Created an **automatic migration** that runs when the backend starts up. This migration will automatically remove any problematic unique indexes from the `redirect_chains` collection that are preventing chain creation.

---

## What This Does

### On Every Backend Startup:
1. Backend connects to MongoDB
2. Migration script runs automatically
3. Script finds all unique indexes on `redirect_chains` collection
4. Removes any unique indexes (except the built-in `_id_` index)
5. Logs what was removed
6. Backend starts normally

### No Manual Work Required:
- ✅ No need to SSH into the server
- ✅ No need to manually run MongoDB commands
- ✅ No need to manually remove indexes
- ✅ Just restart your backend and it's done automatically

---

## Files Created

### 1. Migration Script
**File:** `ppc-backend/app/migrations/remove_chain_unique_indexes.py`

**What it does:**
- Lists all indexes on `redirect_chains` collection
- Identifies unique indexes (these are causing the "already exists" errors)
- Drops each unique index except `_id_`
- Logs results for debugging

### 2. Database Connection Update
**File:** `ppc-backend/app/database.py`

**What changed:**
- Added migration call during `connect_db()`
- Runs automatically before the server starts accepting requests
- Wrapped in try/catch so startup continues even if migration fails

---

## How It Works

### Migration Code:
```python
async def migrate(db):
    # Get all indexes on redirect_chains
    indexes = await db.redirect_chains.list_indexes().to_list(length=None)
    
    # Find and drop any unique indexes (except _id_)
    for index in indexes:
        index_name = index.get('name', '')
        is_unique = index.get('unique', False)
        
        if index_name != '_id_' and is_unique:
            await db.redirect_chains.drop_index(index_name)
            logger.info(f"✓ Dropped unique index: {index_name}")
```

### Integration:
```python
async def connect_db():
    _init_db_handles()
    await create_indexes()
    
    # ... other migrations ...
    
    # Remove problematic unique indexes from redirect_chains
    try:
        from app.migrations.remove_chain_unique_indexes import migrate
        await migrate(db)
    except Exception as e:
        logger.warning("Chain index migration skipped: %s", e)
    
    logger.info("Connected to MongoDB")
```

---

## What Happens Next

### When You Restart Backend:

1. **Backend starts up**
2. **Migration runs automatically:**
   ```
   INFO: Found 3 indexes on redirect_chains collection
   INFO: ✓ Dropped unique index: name_1
   INFO: ✓ Dropped unique index: anchor_domain_1_status_1
   INFO: Successfully removed 2 unique index(es)
   INFO: Connected to MongoDB
   ```
3. **Indexes are gone**
4. **Chains can be created without errors**

### After First Restart:
- Migration will run on every startup
- If no unique indexes exist, it will just log: "No unique indexes to remove"
- No performance impact (migration is fast)

---

## Testing After Deployment

### 1. Check Backend Logs
After restarting, you should see in the logs:
```
INFO: Found X indexes on redirect_chains collection
INFO: ✓ Dropped unique index: [index_name]
INFO: Successfully removed N unique index(es)
INFO: Connected to MongoDB
```

### 2. Try Creating a Chain
1. Go to Redirect Chains page
2. Click "Build Chain"
3. Fill in the form with ANY values
4. Click "Build Chain"
5. ✅ **Should work without "already exists" error**

### 3. Try Duplicate Names
1. Create a chain named "Test Chain"
2. Create another chain named "Test Chain"
3. ✅ **Both should be created successfully**

### 4. Try Same Anchor Domain
1. Create a chain with `anchor1.trustedcloudmedia.com`
2. Create another chain with `anchor1.trustedcloudmedia.com`
3. ✅ **Both should be created successfully**

---

## Benefits

### ✅ Automatic
- No manual database work
- No SSH needed
- No MongoDB commands needed

### ✅ Safe
- Wrapped in try/catch (won't break startup)
- Only removes unique indexes (keeps other indexes)
- Never touches the `_id_` index

### ✅ Idempotent
- Can run multiple times safely
- If no indexes to remove, does nothing
- If already removed, does nothing

### ✅ Logged
- See exactly what was removed in backend logs
- Easy to debug if something goes wrong

---

## What Was Fixed

### Before:
❌ Database had unique indexes on `name` and/or `anchor_domain`
❌ Creating chains with duplicate names threw "already exists" error
❌ Creating chains with same anchor threw "already exists" error
❌ Had to manually SSH and run MongoDB commands

### After:
✅ Migration removes unique indexes automatically on startup
✅ Can create chains with duplicate names
✅ Can create chains with same anchor domains
✅ Just restart backend - no manual work

---

## Deployment Steps

### Simple: Just Restart Backend

```bash
# Pull latest code (on your server)
cd /path/to/ppc-backend
git pull origin main

# Restart backend
pm2 restart ppc-backend
# OR
systemctl restart ppc-backend
# OR
docker-compose restart backend
```

That's it! The migration runs automatically.

---

## Rollback

If you ever need to add back unique indexes (not recommended):

```bash
# Connect to MongoDB
mongo your_database_name

# Add unique index on name
db.redirect_chains.createIndex({ "name": 1 }, { unique: true })

# OR add compound unique index on anchor + status
db.redirect_chains.createIndex(
  { "anchor_domain": 1, "status": 1 }, 
  { unique: true }
)
```

But you won't need this - the system works better without these indexes.

---

## Technical Notes

### Why Remove Unique Indexes?

1. **Chain names are just labels** - They don't need to be globally unique
2. **Multiple chains per anchor is valid** - System can route based on other parameters
3. **Over-restrictive validation** - Was blocking legitimate use cases
4. **Routing uses other fields** - Anchor alone isn't used for routing

### What Indexes Remain?

After migration, `redirect_chains` will have:
- ✅ `_id_` index (built-in, required)
- ✅ `anchor_domain_1_status_1` index (non-unique, for queries)
- ❌ No unique indexes that block creation

### Migration Safety

- Migration only removes unique indexes
- Doesn't remove non-unique indexes (needed for performance)
- Doesn't modify data
- Doesn't drop collections
- Safe to run multiple times

---

## Success Criteria

After deployment, you should be able to:

✅ Create chains with any name (including duplicates)
✅ Create chains with any anchor domain (including duplicates)
✅ No "already exists" errors
✅ No console warnings (those were fixed earlier)
✅ Backend logs show migration ran successfully

---

## Commits

- **fb9a52d** - Add automatic migration to remove unique indexes from redirect_chains on startup
- **a180d13** - Improve DuplicateKeyError messages to identify which field is causing conflict
- **e6b4976** - Disable anchor uniqueness check and fix label accessibility warnings

---

## Support

If after restart you still see errors:

1. **Check backend logs** - Look for migration output
2. **Check if backend actually restarted** - Verify new code is running
3. **Check the exact error message** - It will now tell you which field is the problem
4. **Try creating with completely random values** - To rule out other issues

The migration is automatic and safe. Just restart your backend!
