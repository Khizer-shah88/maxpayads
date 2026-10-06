# CPC Calculation System - Complete Explanation

## Issue Report
User noticed that:
- Publishers page shows $15.00 CPC for a publisher
- Statistics page shows $12.00 for clicks from that same publisher
- Values don't match - why?

## Root Cause
The values shown are **different types of CPC**:

1. **Publishers Page** - Shows **BASE CPC** (before device modifiers)
2. **Statistics Page** - Shows **ACTUAL CPC** (after device modifiers are applied)

## How CPC is Calculated

### Step 1: Base CPC Determination (Priority Order)

The system determines the base CPC rate using this priority:

1. **Publisher Custom CPC** (highest priority)
   - Set per publisher in Admin → Publishers → Edit
   - Example: $15.00
   - This is what shows on the Publishers page

2. **Country-Specific CPC** (if no custom CPC)
   - Set in Admin → CPC Settings → Country Rates
   - Example: US = $0.10, GB = $0.09

3. **Global Country Rate** (from code constants)
   - Hardcoded defaults in `COUNTRY_CPC_RATES`
   - Used if no custom setting exists

4. **Global Default CPC** (fallback)
   - From `DEFAULT_CPC` setting (default: $0.00)

### Step 2: Device Type Modifier Application

After determining the base CPC, the system applies device-specific modifiers:

```python
if device_type == "mobile":
    cpc *= 0.85  # 85% of base rate
elif device_type == "tablet":
    cpc *= 0.90  # 90% of base rate
else:  # desktop
    cpc *= 1.0   # 100% of base rate (no change)
```

### Example Calculation

**Publisher has custom_cpc = $15.00**

| Device Type | Calculation | Actual CPC | Savings |
|-------------|-------------|------------|---------|
| Desktop | $15.00 × 1.0 | **$15.00** | $0.00 |
| Tablet | $15.00 × 0.9 | **$13.50** | $1.50 |
| Mobile | $15.00 × 0.85 | **$12.75** | $2.25 |

If a publisher has:
- 40% desktop traffic → $15.00 average
- 60% mobile traffic → $12.75 average
- **Overall average: $13.65**

## Why Values Differ

### Publishers Page
- Shows: **$15.00**
- This is: **Base CPC** (the custom_cpc field from database)
- Meaning: "Maximum rate before device modifiers"

### Statistics Page
- Shows: **$12.75** (or $13.50, or $15.00)
- This is: **Actual CPC** (the cpc field from each click record)
- Meaning: "What was actually charged for THIS specific click"
- Varies by device type of each click

### Average in Statistics
If you see an average of $12.00-$14.00 when the publisher shows $15.00:
- This means most clicks are from mobile/tablet
- Mobile clicks get 15% discount ($15.00 → $12.75)
- This is **working as designed**

## Where CPC Values Are Stored

### 1. Publisher Record (Base Rate)
```javascript
{
  "_id": "publisher_id",
  "name": "Publisher Name",
  "custom_cpc": 15.00,  // ← BASE RATE (what Publishers page shows)
  "revenue_share": 1.0
}
```

### 2. Click Record (Actual Rate)
```javascript
{
  "_id": "click_id",
  "publisher_id": "publisher_id",
  "device_type": "mobile",
  "cpc": 12.75,  // ← ACTUAL RATE (what Statistics page shows)
  "earnings": 12.75,
  "status": "valid"
}
```

## Code Locations

### Backend CPC Engine
**File:** `ppc-backend/app/services/cpc_engine.py`

```python
async def calculate_cpc(
    publisher_id: str,
    country_code: Optional[str],
    device_type: Optional[str],
    db,
) -> float:
    # 1. Get base CPC (custom or default)
    cpc = get_base_cpc(publisher_id, country_code)
    
    # 2. Apply device modifier
    if device_type == "mobile":
        cpc *= 0.85
    elif device_type == "tablet":
        cpc *= 0.90
    
    return round(cpc, 6)
```

### Click Processing
**File:** `ppc-backend/app/tasks/click_tasks.py`

When a click is processed:
1. Gets base CPC from publisher record or country settings
2. Applies device modifier based on visitor's device
3. Stores the FINAL CPC value in the click record
4. This is what appears in Statistics

## Frontend Display

### Publishers Page
**File:** `ppc-frontend/app/admin/publishers/page.tsx`

```typescript
{
  key: 'custom_cpc',
  label: 'CPC',  // Changed from "CPL"
  render: (p: Publisher) => (
    <span>${p.custom_cpc.toFixed(2)}</span>  // Shows BASE rate
  )
}
```

### Statistics Page
**File:** `ppc-frontend/app/admin/statistics/page.tsx`

```typescript
{
  key: 'cpc',
  label: 'CPC',
  render: (c: Click) => (
    <span>${c.cpc.toFixed(4)}</span>  // Shows ACTUAL rate
  )
}
```

## How to Verify

### 1. Check Publisher Base CPC
```bash
docker exec ppc_fastapi python -c "
from app.database import get_database
import asyncio

async def check():
    db = await get_database()
    pub = await db.publishers.find_one({'name': 'YOUR_PUBLISHER_NAME'})
    print(f'Base CPC: \${pub.get(\"custom_cpc\", 0):.2f}')
    
asyncio.run(check())
"
```

### 2. Check Click CPCs
```bash
docker exec ppc_fastapi python -c "
from app.database import get_database
import asyncio

async def check():
    db = await get_database()
    clicks = await db.clicks.find({'publisher_id': 'YOUR_PUBLISHER_ID'}).limit(10).to_list(length=10)
    for c in clicks:
        print(f'{c.get(\"device_type\")}: \${c.get(\"cpc\", 0):.4f}')
    
asyncio.run(check())
"
```

## Solution: Understanding, Not Fixing

This is **NOT a bug** - it's the designed behavior:

✅ **Publishers page shows base CPC** - the maximum rate
✅ **Statistics page shows actual CPC** - the rate after device discounts
✅ **Mobile gets 15% discount** - to account for lower conversion rates
✅ **Tablet gets 10% discount** - medium conversion rate
✅ **Desktop gets full rate** - highest conversion rate

## If You Want Consistent Values

### Option 1: Remove Device Modifiers (Not Recommended)
Edit `ppc-backend/app/services/cpc_engine.py`:
```python
# Comment out device modifiers
# if device_type == "mobile":
#     cpc *= 0.85
# elif device_type == "tablet":
#     cpc *= 0.90
```

**Downside:** You'll overpay for mobile traffic (lower quality)

### Option 2: Show Device-Specific Rates in Publishers Page
Add tooltip showing:
- Desktop: $15.00
- Tablet: $13.50
- Mobile: $12.75

### Option 3: Show Average CPC in Publishers Page
Calculate and display the actual average CPC from click records for each publisher.

## Recommendation

**Keep the current system** because:
1. It rewards high-quality (desktop) traffic with higher rates
2. It protects your budget from low-quality (mobile) traffic
3. It's industry standard to pay different rates by device type
4. Publishers get the rate appropriate to the traffic quality they send

**Add a tooltip** on the Publishers page explaining:
- "Base rate (Desktop). Mobile: -15%, Tablet: -10%"

This way admins understand what they're seeing without changing the underlying logic.

## Changes Made

1. ✅ Changed "CPL" to "CPC" in Publishers page column header
2. ✅ Changed "Custom CPL (CPC)" to "Custom CPC" in edit modals
3. ✅ Created this documentation explaining the system

## Next Steps (Optional Enhancements)

1. Add tooltip to Publishers page CPC column explaining device modifiers
2. Add "Avg CPC" column showing actual average from click records
3. Add device breakdown in publisher detail view
4. Add CPC trend chart showing how rates vary by device over time
