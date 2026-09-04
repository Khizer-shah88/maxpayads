# Direct Link Stats - Complete Implementation Plan

## Current Status vs Requirements

### ❌ Missing Features

1. **Stats Profile Preferences** - NOT implemented
   - Need to configure what stats to show/hide
   - Settings like: Show OS, Show Country, Show Device, Show Clicks, etc.

2. **Unique/Valid Clicks** - NOT implemented  
   - Currently showing raw click counts
   - Need fraud validation logic integration
   - Need to distinguish: Unique Clicks, Valid Clicks, Invalid Clicks

3. **OS-based Statistics** - NOT implemented
   - No breakdown by operating system
   - Need aggregation by Windows, Android, iOS, Linux, macOS

4. **Manual Conversion Entry** - PARTIALLY implemented
   - Has manual override endpoint
   - BUT: Not properly displayed in UI
   - Need date-based conversion history view

### ✅ Existing Features

- ✅ Basic direct link CRUD
- ✅ Click/conversion counting
- ✅ Publisher-specific links
- ✅ White-label stats URL generation
- ✅ Manual conversion override API endpoint

## Implementation Plan

### Phase 1: Backend - Stats Profiles

**New File:** `ppc-backend/app/schemas/stats_profile_schema.py`
```python
class StatsProfilePreferences(BaseModel):
    show_os: bool = True
    show_country: bool = True
    show_device: bool = True
    show_clicks: bool = True
    show_valid_clicks: bool = True
    show_impressions: bool = True
    show_conversions: bool = True
    show_cr: bool = True
    show_invalid_clicks: bool = False
```

**New Endpoint:** POST `/direct-links/stats-profiles`
- Create/update stats profile for a publisher
- Store preferences in `stats_profiles` collection

### Phase 2: Backend - Validated Click Tracking

**Modify:** `ppc-backend/app/routers/direct_link_router.py`
- Update `record_conversion` to apply fraud validation
- Store click validation status (unique, valid, invalid, fraud_score)
- Use existing fraud detection from click_router

**New Fields in direct_link_events:**
```javascript
{
  link_id: "...",
  is_unique: true,      // First click from this IP in time window
  is_valid: true,       // Passed fraud validation  
  is_fraud: false,      // Marked as fraud
  fraud_score: 0.2,     // Fraud probability
  fraud_reason: null,   // If flagged
  device_type: "desktop",
  os: "Windows",
  country_code: "US"
}
```

### Phase 3: Backend - Stats Aggregation Endpoints

**New Endpoints:**

1. GET `/direct-links/stats/publisher/{publisher_id}`
   - Returns aggregated stats with all metrics
   - Respects stats profile preferences
   - Includes OS breakdown, country breakdown, device breakdown

2. GET `/direct-links/stats/link/{link_id}`
   - Stats for specific link
   - Same structure as publisher stats

3. GET `/direct-links/stats/os-breakdown`
   - Returns clicks/conversions by OS
   - For date range and publisher/link filter

### Phase 4: Backend - Manual Conversions Enhancement

**New Collection:** `direct_link_manual_conversions`
```javascript
{
  date: "2026-01-09",        // Date string YYYY-MM-DD
  publisher_id: "...",
  link_id: "..." (optional),
  conversions: 24,
  reason: "Manual entry",
  entered_by: "admin_id",
  entered_at: ISODate(...)
}
```

**New Endpoints:**
- POST `/direct-links/manual-conversions` - Add conversion for specific date
- GET `/direct-links/manual-conversions` - Get history with filters
- PUT `/direct-links/manual-conversions/{id}` - Update existing entry
- DELETE `/direct-links/manual-conversions/{id}` - Delete entry

### Phase 5: Frontend - Stats Profile UI

**Location:** `ppc-frontend/app/admin/direct-link-stats/page.tsx`

Add "Configure Stats" button per publisher that opens modal with checkboxes:
```
☑ Show OS Statistics
☑ Show Country
☑ Show Device
☑ Show Clicks  
☑ Show Valid Clicks
☑ Show Impressions
☑ Show Conversions
☐ Show Invalid Clicks
```

### Phase 6: Frontend - Enhanced Stats Display

**Stats Card Updates:**
```
Publisher: John Doe
─────────────────────
Total Clicks: 1,240
Valid Clicks: 1,180 (95%)
Invalid Clicks: 60 (5%)
Unique Clicks: 980
Conversions: 45
CR: 3.64%

OS Breakdown:
Windows    820 (66%)
Android    280 (23%)
iOS        90 (7%)
Linux      30 (2%)
macOS      20 (2%)
```

### Phase 7: Frontend - Manual Conversions UI

Add "Manual Conversions" tab/section with:
- Calendar date picker
- Input for conversion count
- Reason text field
- History table showing all manual entries
- Edit/delete buttons

**Table View:**
```
Date         | Link    | Conversions | Reason         | By    | Actions
─────────────────────────────────────────────────────────────────────
2026-01-09   | All     | 24          | Manual entry   | Admin | Edit Delete
2026-01-08   | Link #1 | 18          | API down       | Admin | Edit Delete
2026-01-07   | All     | 31          | Bulk import    | Admin | Edit Delete
```

## Database Schema Changes

### New Collections

1. **stats_profiles**
```javascript
{
  _id: ObjectId,
  publisher_id: "...",
  preferences: {
    show_os: true,
    show_country: true,
    show_device: true,
    show_clicks: true,
    show_valid_clicks: true,
    show_impressions: true,
    show_conversions: true,
    show_cr: true,
    show_invalid_clicks: false
  },
  created_at: ISODate,
  updated_at: ISODate
}
```

2. **direct_link_manual_conversions**
```javascript
{
  _id: ObjectId,
  date: "2026-01-09",
  publisher_id: "...",
  link_id: "..." | null,
  conversions: 24,
  reason: "Manual adjustment",
  entered_by: "admin_id",
  entered_at: ISODate,
  updated_at: ISODate
}
```

### Modified Collections

**direct_link_events** - Add fields:
```javascript
{
  // existing fields...
  is_unique: true,
  is_valid: true,
  is_fraud: false,
  fraud_score: 0.15,
  fraud_reason: null,
  device_type: "desktop",
  os: "Windows",
  country_code: "US",
  browser: "Chrome"
}
```

## API Endpoints Summary

### New Endpoints

```
Stats Profiles:
POST   /api/direct-links/stats-profiles
GET    /api/direct-links/stats-profiles/{publisher_id}
PUT    /api/direct-links/stats-profiles/{publisher_id}

Stats Aggregation:
GET    /api/direct-links/stats/publisher/{publisher_id}
GET    /api/direct-links/stats/link/{link_id}
GET    /api/direct-links/stats/os-breakdown
GET    /api/direct-links/stats/country-breakdown
GET    /api/direct-links/stats/device-breakdown

Manual Conversions:
POST   /api/direct-links/manual-conversions
GET    /api/direct-links/manual-conversions
PUT    /api/direct-links/manual-conversions/{id}
DELETE /api/direct-links/manual-conversions/{id}
```

### Modified Endpoints

```
POST /api/direct-links/conversions
  - Add fraud validation
  - Add OS/device/country detection
  - Store validation status
```

## Implementation Steps

1. ✅ Create implementation plan (this document)
2. ⏳ Create stats profile schema
3. ⏳ Add fraud validation to direct link clicks
4. ⏳ Create stats aggregation endpoints  
5. ⏳ Create manual conversions endpoints
6. ⏳ Update frontend stats display
7. ⏳ Add stats profile configuration UI
8. ⏳ Add manual conversions UI
9. ⏳ Test all features
10. ⏳ Push code

## Testing Checklist

- [ ] Stats profile CRUD works
- [ ] Fraud validation applied to direct link clicks
- [ ] OS breakdown shows correct data
- [ ] Country breakdown shows correct data
- [ ] Device breakdown shows correct data
- [ ] Manual conversions can be added/edited/deleted
- [ ] Manual conversion history displays correctly
- [ ] Stats respect profile preferences (show/hide fields)
- [ ] Unique clicks calculated correctly
- [ ] Valid clicks calculated correctly
- [ ] Invalid clicks shown when enabled

## Notes

- Fraud validation uses existing logic from `app/routers/click_router.py`
- OS/device/country detection uses existing utils
- Stats profiles are per-publisher (not per-link)
- Manual conversions can be link-specific or publisher-wide (link_id optional)
- All stats endpoints support date range filtering
- Historical data needs backfill for OS/device/country if not stored

## Time Estimate

- Backend implementation: ~4-6 hours
- Frontend implementation: ~3-4 hours
- Testing & bug fixes: ~2-3 hours
- **Total: ~9-13 hours**

This is a significant feature addition that will greatly enhance the Direct Link Stats functionality.
