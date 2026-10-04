# Zero CPC Issue - Analysis and Fix

## Problem

Statistics page shows **$0.000** for CPC even though Publisher has **$15.00** custom CPC configured.

## Root Cause

The system uses **asynchronous CPC calculation**:

1. **When click arrives** → Click record created with `cpc: 0.0` (placeholder)
2. **Background task** → Celery worker calculates real CPC and updates the record
3. **If Celery fails** → Click stays at $0.000 forever

## Why This Happens

### Click Creation Flow

**File:** `ppc-backend/app/services/redirect_pipeline.py`

```python
async def stage_record_click(ctx, db):
    click_data.update({
        "cpc": 0.0,        # ← Initial placeholder
        "earnings": 0.0,   # ← Initial placeholder
        "processed": False # ← Waiting for background task
    })
    await db.clicks.insert_one(click_data)
```

### Background CPC Calculation

**File:** `ppc-backend/app/tasks/click_tasks.py`

```python
@celery_app.task
def process_click(click_id, click_data):
    # Calculate real CPC
    cpc = await calculate_cpc(
        publisher_id,
        country_code,
        device_type,
        db
    )
    earnings = cpc * revenue_share
    
    # Update click with real values
    await db.clicks.update_one(
        {"_id": click_id},
        {"$set": {"cpc": cpc, "earnings": earnings, "processed": True}}
    )
```

### When It Fails

Clicks stay at $0.000 if:
1. **Celery worker not running**
2. **RabbitMQ/Redis connection failed**
3. **Task queue is full/stuck**
4. **Task crashed with error**

## Check If Celery Is Running

### On Server

```bash
# Check if Celery container is running
docker ps | grep celery

# Check Celery logs
docker logs ppc_celery --tail 100

# Check if tasks are being processed
docker exec ppc_celery celery -A app.celery_app inspect active
```

### Expected Output

```
docker ps | grep celery
ppc_celery    running    app.celery_app worker
```

If you don't see Celery running, that's the problem!

## Fix #1: Start Celery Worker

### Check docker-compose.prod.yml

```yaml
services:
  celery:
    image: ${your-image}
    command: celery -A app.celery_app worker --loglevel=info
    environment:
      - CELERY_BROKER_URL=amqp://rabbitmq:5672//
      - CELERY_RESULT_BACKEND=redis://redis:6379/0
    depends_on:
      - rabbitmq
      - redis
```

### Start Celery

```bash
docker-compose -f docker-compose.prod.yml up -d celery
```

## Fix #2: Repair Existing Zero-CPC Clicks

Run the repair script to fix all existing clicks:

```bash
# On server
docker exec ppc_fastapi python scripts/fix_zero_cpc_clicks.py
```

**What it does:**
1. Finds all clicks with `status='valid'` and `cpc=0.0`
2. Recalculates CPC for each using `calculate_cpc()`
3. Updates click records with correct CPC and earnings
4. Recalculates publisher balances

**Example output:**
```
Found 1250 valid clicks with zero CPC
Recalculating CPC for each click...

  Fixed 100/1250 clicks...
  Fixed 200/1250 clicks...
  ...
  Fixed 1250/1250 clicks...

✅ Fixed 1250 clicks

Recalculating publisher balances...
  ✓ John Doe: $125.50
  ✓ Jane Smith: $89.30
  ✓ Test Publisher: $0.00

✅ All done!
```

## Fix #3: Prevent Future Issues

### Option A: Synchronous CPC (Not Recommended)

Calculate CPC synchronously during redirect (slower but guaranteed):

**File:** `ppc-backend/app/services/redirect_pipeline.py`

```python
async def stage_record_click(ctx, db):
    # Calculate CPC immediately (blocks redirect)
    from app.services.cpc_engine import calculate_cpc
    
    cpc = await calculate_cpc(
        ctx.publisher_id,
        ctx.country_code,
        ctx.device_type,
        db
    )
    
    publisher = await db.publishers.find_one({"_id": ctx.publisher_id})
    revenue_share = publisher.get("revenue_share", 1.0)
    earnings = cpc * revenue_share
    
    click_data.update({
        "cpc": cpc,
        "earnings": earnings,
        "processed": True
    })
    await db.clicks.insert_one(click_data)
```

**Pros:** CPC always correct
**Cons:** Redirects 20-50ms slower (bad for user experience)

### Option B: Ensure Celery Always Runs (Recommended)

Keep the async system but ensure Celery is monitored:

1. **Add health check** to docker-compose:
```yaml
celery:
  healthcheck:
    test: ["CMD", "celery", "-A", "app.celery_app", "inspect", "ping"]
    interval: 30s
    timeout: 10s
    retries: 3
```

2. **Add restart policy:**
```yaml
celery:
  restart: unless-stopped
```

3. **Monitor with script:**
```bash
#!/bin/bash
# check_celery.sh
if ! docker ps | grep -q ppc_celery; then
    echo "Celery is down! Restarting..."
    docker-compose -f docker-compose.prod.yml up -d celery
    # Send alert
fi
```

Add to crontab:
```bash
*/5 * * * * /path/to/check_celery.sh
```

## Verification

### Check Click CPC Values

```bash
docker exec ppc_fastapi python -c "
from app.database import get_database
import asyncio

async def check():
    db = await get_database()
    
    # Count clicks by CPC
    zero_cpc = await db.clicks.count_documents({'cpc': 0.0, 'status': 'valid'})
    nonzero_cpc = await db.clicks.count_documents({'cpc': {'\\$gt': 0.0}, 'status': 'valid'})
    
    print(f'Valid clicks with CPC > 0: {nonzero_cpc}')
    print(f'Valid clicks with CPC = 0: {zero_cpc}')
    
    if zero_cpc > 0:
        print(f'⚠️  {zero_cpc} clicks need fixing!')
    else:
        print('✅ All valid clicks have CPC!')

asyncio.run(check())
"
```

### Check Statistics Page

1. Go to **Admin → Statistics**
2. Filter by specific publisher
3. Check CPC column
4. Should show actual values (not $0.000)

### Check Publisher Page

1. Go to **Admin → Publishers**  
2. Note the CPC value (e.g., $15.00)
3. Go to **Admin → Statistics**
4. Filter by that publisher
5. Desktop clicks should show ~$15.00
6. Mobile clicks should show ~$12.75 (85% of $15.00)
7. Average should be between these based on device mix

## Summary of Fixes

### 1. JavaScript Obfuscation
✅ Fixed regex bug in `_obfuscate_strings()` function
- Changed `match.group(2)` to `match.group(1)`
- Tests now pass

### 2. Zero CPC Issue
✅ Created repair script: `scripts/fix_zero_cpc_clicks.py`
✅ Created documentation
✅ Provided Celery monitoring solutions

### 3. Root Causes
1. **JS Obfuscation:** Regex capture group index error
2. **Zero CPC:** Celery worker not running or tasks failing

## Deployment Checklist

- [ ] Push code changes (JS obfuscation fix)
- [ ] Wait for CI/CD to deploy
- [ ] Check if Celery is running on server
- [ ] If not, start Celery: `docker-compose up -d celery`
- [ ] Run repair script: `docker exec ppc_fastapi python scripts/fix_zero_cpc_clicks.py`
- [ ] Verify Statistics page shows correct CPC values
- [ ] Add Celery monitoring (health checks + cron job)

## Testing

### Test JS Obfuscation
```bash
cd ppc-backend
pytest tests/test_js_obfuscation.py -v
```

Should see:
```
test_obfuscate_strings PASSED
test_obfuscate_javascript_simple PASSED
test_obfuscate_html_javascript PASSED
test_real_world_prelander_script PASSED
```

### Test CPC Calculation
```bash
cd ppc-backend
pytest tests/ -k "test_cpc" -v
```

Should see CPC calculations working correctly.

## Quick Fix Commands

```bash
# 1. Check Celery status
docker ps | grep celery

# 2. Start Celery if not running
docker-compose -f docker-compose.prod.yml up -d celery

# 3. Fix existing zero-CPC clicks
docker exec ppc_fastapi python scripts/fix_zero_cpc_clicks.py

# 4. Verify
docker exec ppc_fastapi python -c "
from app.database import get_database
import asyncio
async def check():
    db = await get_database()
    zero = await db.clicks.count_documents({'cpc': 0.0, 'status': 'valid'})
    print(f'Zero CPC clicks: {zero}')
asyncio.run(check())
"
```

## Long-Term Solution

**Monitor Celery health** and **auto-restart** if it goes down:

```yaml
# docker-compose.prod.yml
celery:
  restart: unless-stopped
  healthcheck:
    test: ["CMD", "celery", "-A", "app.celery_app", "inspect", "ping"]
    interval: 30s
    timeout: 10s
    retries: 3
```

This ensures Celery always runs and CPC calculations always complete.
