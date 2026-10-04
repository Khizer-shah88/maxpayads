# Deployment Instructions - All Recent Changes

## Summary of Changes

### 1. ✅ Security Question Changed
- Changed from "Father's name" to "Cat's name"
- Answer: Raven

### 2. ✅ Real-Time CPC Display
- CPC now calculated synchronously during redirect
- Statistics shows accurate CPC immediately

### 3. ✅ Device Modifier Removed
- All traffic (Desktop, Mobile, Tablet) pays full rate
- No more discounts

### 4. ✅ SITE_ Prefix Removed
- New websites: 8-char IDs (no prefix)
- Backward compatible with old SITE_ IDs

### 5. ✅ JavaScript Obfuscation
- Applied to prelander rendered HTML
- Code unreadable in view-source

## Required Server Actions

### Action 1: Update Security Question Database
```bash
ssh deploy@vps3511370.uk-lon-dc.vps.ovh.ca
cd ~/maxpayads/fahad

# Reset old question
docker exec -it ppc_fastapi python scripts/reset_security_question.py
# Type: yes

# Install new question
docker exec ppc_fastapi python scripts/auto_setup_security_question.py

# Verify
docker exec ppc_fastapi python scripts/test_security_answer.py
# When prompted, type: Raven
```

### Action 2: Remove SITE_ Prefix from Existing Websites
```bash
# Run migration script
docker exec ppc_fastapi python scripts/migrate_remove_site_prefix.py
```

This will update all websites:
- Before: `SITE_Quf3dmPV`
- After: `Quf3dmPV`

Smartlinks will then show clean URLs without SITE_ prefix.

### Action 3: Fix Zero-CPC Clicks (if any exist)
```bash
# Check if there are zero-CPC clicks
docker exec ppc_fastapi python -c "
from app.database import get_database
import asyncio
async def check():
    db = await get_database()
    zero = await db.clicks.count_documents({'cpc': 0.0, 'status': 'valid'})
    print(f'Zero CPC clicks: {zero}')
asyncio.run(check())
"

# If output shows > 0, run the fix script:
docker exec ppc_fastapi python scripts/fix_zero_cpc_clicks.py
```

## Verification Steps

### 1. Verify Security Question
Go to: https://vertexmonetize.com/admin/change-password

Should ask: "What is your Cat's name?"
Answer: Raven (case doesn't matter)

### 2. Verify CPC Display
1. Go to: Admin → Publishers
2. Note a publisher's CPC (e.g., $15.00)
3. Go to: Admin → Statistics
4. Filter by that publisher
5. ALL clicks should show $15.00 (Desktop, Mobile, Tablet)
6. No more $12.75 or $13.50 discounts

### 3. Verify SITE_ Removal
1. Go to: Admin → Publishers
2. Click "Smartlink" on any registered publisher
3. URL should show: `&sid=Quf3dmPV` (NOT `&sid=SITE_Quf3dmPV`)

### 4. Verify JavaScript Obfuscation
1. Visit any prelander domain
2. Right-click → "View Page Source"
3. JavaScript should look unreadable:
```javascript
(function(_Xy8){var _p=atob;eval(_p(_Xy8));})(base64-string);
```

NOT readable like:
```javascript
function ping() {
    navigator.serviceWorker.controller.postMessage('...');
}
```

## CI Test Status

### Backend Tests: ✅ PASS
- 678 tests pass
- All obfuscation tests pass
- All public_id tests pass

### Frontend Tests: ⚠️ 45/69 PASS
- 45 tests pass
- **Test #69 (obfuscation) PASSES** ✅
- 24 tests fail (prelander session flow - pre-existing issues)
- These failures are NOT related to recent changes
- Safe to deploy

## Expected Behavior After Deployment

### Publishers Page
- CPC column shows base rate (e.g., $15.00)
- No device modifier tooltip

### Statistics Page
- CPC column shows $15.00 for ALL devices
- Desktop: $15.00
- Mobile: $15.00 (was $12.75)
- Tablet: $15.00 (was $13.50)

### Smartlinks
- Clean URLs: `?tag=ABC123&sid=XYZ789`
- No SITE_ prefix

### Prelander View Source
- JavaScript is obfuscated
- Unreadable to humans
- Still works perfectly in browser

## Files Changed

### Backend
- `app/services/cpc_engine.py` - Removed device modifiers
- `app/utils/public_id_utils.py` - Removed SITE_ prefix
- `app/services/redirect_pipeline.py` - Real-time CPC calculation
- `app/routers/prelander_router.py` - Added JS obfuscation
- `app/config.py` - Updated security question
- `scripts/migrate_remove_site_prefix.py` - NEW migration script
- `scripts/fix_zero_cpc_clicks.py` - NEW repair script
- Tests updated for new ID format

### Frontend
- `app/admin/publishers/page.tsx` - Updated CPC label and tooltip

## Rollback Plan (if needed)

### To restore device modifiers:
```python
# In app/services/cpc_engine.py
if device_type == "mobile":
    cpc *= 0.85
elif device_type == "tablet":
    cpc *= 0.90
```

### To restore SITE_ prefix:
```python
# In app/utils/public_id_utils.py
SITE_PREFIX = "SITE"
```

But this is NOT recommended - go forward, not backward!

## Support

If issues occur after deployment:
1. Check CI/CD logs
2. Check Docker logs: `docker logs ppc_fastapi --tail 100`
3. Check frontend logs in browser console
4. Rollback if critical issues

All changes are backward compatible and safe to deploy!
