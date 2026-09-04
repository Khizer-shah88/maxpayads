# Bypass Feature Testing Guide

## Quick Start Testing

### 1. Check Current Bypass Status

```bash
# Get campaign details
curl -X GET "http://localhost:8000/api/campaigns/{campaign_id}" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Look for this field in response:
{
  "id": "...",
  "name": "Test Campaign",
  "direct_redirect_mode": false,  # ← Current bypass status
  ...
}
```

### 2. Enable Bypass (Skip Prelander)

```bash
# Update campaign to enable bypass
curl -X PUT "http://localhost:8000/api/campaigns/{campaign_id}" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "direct_redirect_mode": true
  }'

# Response:
{
  "success": true,
  "campaign": {
    "id": "...",
    "direct_redirect_mode": true,  # ← Now enabled
    ...
  }
}
```

### 3. Disable Bypass (Show Prelander)

```bash
# Update campaign to disable bypass
curl -X PUT "http://localhost:8000/api/campaigns/{campaign_id}" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "direct_redirect_mode": false
  }'
```

### 4. Test the Flow

```bash
# Click a smartlink
curl -X GET "http://localhost:8000/api/click?pub=PUB_ABC123&site=SITE_XYZ789" \
  -H "User-Agent: Mozilla/5.0" \
  -L  # Follow redirects

# With bypass OFF: Should redirect to prelander domain
# Final URL: https://prelander.example.com/d/{slug}

# With bypass ON: Should redirect to campaign URL directly  
# Final URL: https://offer.com/product
```

---

## Detailed Test Scenarios

### Scenario 1: Default Behavior (Bypass OFF)

**Setup:**
```bash
# Create campaign with bypass OFF (default)
curl -X POST "http://localhost:8000/api/campaigns" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "name": "Test Campaign - Bypass OFF",
    "default_offer_url": "https://example-offer.com/product",
    "direct_redirect_mode": false
  }'
```

**Test:**
1. Get a smartlink for this campaign
2. Click the smartlink
3. Observe browser behavior

**Expected Result:**
```
URL changes: 
  smartlink 
  → anchor domain 
  → inter domain
  → prelander domain (/d/{slug})
  → campaign URL

Final page: Prelander template is visible
Logs show: "[ROUTE] BYPASS OFF: Building prelander destination"
```

**Verify in Database:**
```javascript
db.clicks.find({publisher_id: "..."}).sort({timestamp: -1}).limit(1)

// destination_url should be prelander URL:
{
  "destination_url": "https://prelander.example.com/d/abc123xyz",
  ...
}
```

---

### Scenario 2: Bypass Enabled (Skip Prelander)

**Setup:**
```bash
# Update campaign to enable bypass
curl -X PUT "http://localhost:8000/api/campaigns/{campaign_id}" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "direct_redirect_mode": true
  }'
```

**Test:**
1. Get a smartlink for this campaign
2. Click the smartlink  
3. Observe browser behavior

**Expected Result:**
```
URL changes:
  smartlink
  → anchor domain
  → inter domain
  → campaign URL (DIRECT, no prelander)

Final page: Offer landing page (no prelander shown)
Logs show: "[ROUTE] BYPASS MODE: Direct to campaign URL"
```

**Verify in Database:**
```javascript
db.clicks.find({publisher_id: "..."}).sort({timestamp: -1}).limit(1)

// destination_url should be campaign URL:
{
  "destination_url": "https://example-offer.com/product",
  ...
}
```

---

### Scenario 3: Offer-Level Override

**Setup:**
```bash
# Campaign has bypass OFF
curl -X PUT "http://localhost:8000/api/campaigns/{campaign_id}" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "direct_redirect_mode": false
  }'

# Offer has bypass ON (overrides campaign)
curl -X PUT "http://localhost:8000/api/offers/{offer_id}" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "direct_redirect_mode": true
  }'
```

**Test:**
1. Click smartlink that triggers the specific offer
2. Observe behavior

**Expected Result:**
```
Offer bypass ON overrides campaign bypass OFF
→ Traffic goes DIRECTLY to campaign URL
→ Prelander is SKIPPED

Logs show: "[ROUTE] Bypass ON (offer) — will skip prelander"
```

---

### Scenario 4: GEO Rule with Bypass

**Setup:**
```bash
# Create campaign with GEO rules and bypass ON
curl -X POST "http://localhost:8000/api/campaigns/{campaign_id}/geo-rules" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "country_code": "US",
    "offer_url": "https://us-offer.com/deal",
    "priority": 10
  }'

# Enable bypass
curl -X PUT "http://localhost:8000/api/campaigns/{campaign_id}" \
  -H "Content-Type: application/json" \
  -d '{
    "direct_redirect_mode": true
  }'
```

**Test:**
1. Click smartlink from US IP
2. Observe routing

**Expected Result:**
```
GEO targeting works FIRST (selects US offer)
Then bypass logic applies
→ Goes directly to US offer URL (skips prelander)

Logs show:
  "[ROUTE] Targeting resolved: url=https://us-offer.com/deal, rule_type=geo"
  "[ROUTE] BYPASS MODE: Direct to campaign URL: https://us-offer.com/deal"
```

---

## Testing Checklist

### Functional Tests

- [ ] **Bypass OFF**: Prelander page loads correctly
- [ ] **Bypass ON**: Redirects directly to offer (no prelander)
- [ ] **Campaign Bypass**: Campaign-level setting works
- [ ] **Offer Bypass**: Offer-level setting overrides campaign
- [ ] **No Domains**: Falls back to campaign URL gracefully
- [ ] **GEO + Bypass**: GEO targeting works with both bypass modes
- [ ] **Device + Bypass**: Device rules work with both bypass modes

### Data Integrity Tests

- [ ] **Click Logging**: Clicks logged in both modes
- [ ] **Destination URL**: Correct URL stored in database
- [ ] **Fraud Detection**: Runs in both modes
- [ ] **Session Cookies**: Generated in both modes
- [ ] **Timestamps**: Accurate in both modes

### Performance Tests

- [ ] **Bypass OFF Speed**: Measure redirect time with prelander
- [ ] **Bypass ON Speed**: Measure redirect time without prelander
- [ ] **Load Test**: Both modes handle high traffic

---

## Manual UI Testing

### Admin Panel Flow

1. **Navigate to Campaigns**
   - Go to Admin → Campaigns
   - Select a campaign

2. **Toggle Bypass Setting**
   - Find "Direct Redirect Mode" toggle
   - Click to enable/disable
   - Save changes

3. **Verify in UI**
   - Setting should show as ON/OFF
   - Color indicator changes

4. **Test User Flow**
   - Open smartlink in incognito window
   - Verify correct behavior (prelander vs direct)

---

## Automated Test Suite

### Run All Tests

```bash
cd ppc-backend

# Run bypass-specific tests
.venv-linux/bin/python -m pytest tests/test_bypass_simple.py -v

# Run all traffic router tests
.venv-linux/bin/python -m pytest tests/test_traffic_router.py -v

# Run with coverage
.venv-linux/bin/python -m pytest tests/test_bypass_simple.py --cov=app.services.traffic_router
```

### Expected Output

```
tests/test_bypass_simple.py::test_bypass_field_exists_in_campaign_schema PASSED
tests/test_bypass_simple.py::test_bypass_logic_determination PASSED
tests/test_bypass_simple.py::test_prelander_url_structure PASSED
tests/test_bypass_simple.py::test_campaign_url_structure PASSED
tests/test_bypass_simple.py::test_bypass_override_priority PASSED
tests/test_bypass_simple.py::test_traffic_flow_documentation PASSED
tests/test_bypass_simple.py::test_domain_types PASSED
tests/test_bypass_simple.py::test_bypass_default_value PASSED

8 passed ✅
```

---

## Debugging

### Check Logs

```bash
# Watch live logs
tail -f ppc-backend/fastapi_debug.log | grep ROUTE

# Search for bypass-related entries
grep "BYPASS" ppc-backend/fastapi_debug.log

# Expected patterns:
# Bypass OFF: "[ROUTE] BYPASS OFF: Building prelander destination"
# Bypass ON:  "[ROUTE] BYPASS MODE: Direct to campaign URL"
```

### Common Issues

#### Issue: Prelander still showing with bypass ON

**Debug:**
```bash
# Check campaign setting
db.campaigns.findOne({_id: ObjectId("...")}, {direct_redirect_mode: 1})

# Expected: {direct_redirect_mode: true}
# If false, update it
```

**Fix:**
```bash
curl -X PUT "http://localhost:8000/api/campaigns/{id}" \
  -d '{"direct_redirect_mode": true}'
```

#### Issue: Click not being logged

**Debug:**
```bash
# Check recent clicks
db.clicks.find().sort({timestamp: -1}).limit(5).pretty()

# Check logs
grep "track_click" ppc-backend/fastapi_debug.log
```

**Verify:**
- `/click` endpoint is accessible
- Database connection is active
- Redis is running

#### Issue: Wrong URL in destination_url field

**Debug:**
```javascript
// Check last 10 clicks
db.clicks.find(
  {publisher_id: "YOUR_PUB_ID"},
  {destination_url: 1, timestamp: 1}
).sort({timestamp: -1}).limit(10)

// Compare destination_url values:
// Bypass OFF: Should contain "/d/" (prelander)
// Bypass ON:  Should be direct offer URL
```

---

## Performance Benchmarks

### Expected Timings

#### Bypass OFF (with prelander)
```
Smartlink → Result: ~1-3 seconds
  - Anchor domain: ~50-100ms
  - Inter domain: ~100-200ms
  - Prelander load: ~500-1000ms
  - Campaign URL: ~500-1000ms
Total: ~1150-2300ms
```

#### Bypass ON (direct)
```
Smartlink → Result: ~500ms-1s
  - Anchor domain: ~50-100ms
  - Inter domain: ~100-200ms
  - Campaign URL: ~500-1000ms
Total: ~650-1300ms

Speed improvement: ~40-50% faster
```

### Run Performance Test

```bash
# Test bypass OFF
time curl -L "http://localhost:8000/api/click?pub=PUB_ABC&site=SITE_XYZ"

# Test bypass ON (after enabling)
time curl -L "http://localhost:8000/api/click?pub=PUB_ABC&site=SITE_XYZ"

# Compare times
```

---

## Database Queries for Verification

### Check Campaign Bypass Status

```javascript
// Single campaign
db.campaigns.findOne(
  {_id: ObjectId("YOUR_CAMPAIGN_ID")},
  {name: 1, direct_redirect_mode: 1}
)

// All campaigns with bypass ON
db.campaigns.find(
  {direct_redirect_mode: true},
  {name: 1, created_at: 1}
).pretty()

// Count by bypass status
db.campaigns.aggregate([
  {$group: {
    _id: "$direct_redirect_mode",
    count: {$sum: 1}
  }}
])
```

### Analyze Click Destinations

```javascript
// Clicks with prelander URLs (bypass OFF)
db.clicks.find({
  destination_url: {$regex: "/d/"}
}).count()

// Clicks with direct URLs (bypass ON)
db.clicks.find({
  destination_url: {$not: {$regex: "/d/"}}
}).count()

// Recent clicks by destination type
db.clicks.aggregate([
  {$match: {
    timestamp: {$gte: new Date(Date.now() - 24*60*60*1000)}
  }},
  {$project: {
    hasPrelanderPath: {$regexMatch: {
      input: "$destination_url",
      regex: "/d/"
    }}
  }},
  {$group: {
    _id: "$hasPrelanderPath",
    count: {$sum: 1}
  }}
])
```

---

## Load Testing

### Using Apache Bench

```bash
# Test 100 requests, 10 concurrent (bypass OFF)
ab -n 100 -c 10 "http://localhost:8000/api/click?pub=PUB_ABC&site=SITE_XYZ"

# Enable bypass and test again
ab -n 100 -c 10 "http://localhost:8000/api/click?pub=PUB_ABC&site=SITE_XYZ"

# Compare:
# - Requests per second
# - Mean response time
# - 95th percentile
```

### Expected Load Test Results

```
Bypass OFF:
  Requests/sec: ~20-30
  Mean time: ~150-200ms
  95th percentile: ~300-400ms

Bypass ON:
  Requests/sec: ~30-40 (better)
  Mean time: ~100-150ms (faster)
  95th percentile: ~200-300ms (faster)
```

---

## Production Readiness Checklist

Before deploying to production:

- [ ] All tests passing
- [ ] Manual testing complete
- [ ] Performance benchmarks acceptable
- [ ] Logging working correctly
- [ ] Database indexes created
- [ ] Monitoring alerts configured
- [ ] Rollback plan prepared
- [ ] Documentation reviewed
- [ ] Team trained on bypass feature

---

## Quick Reference

### Enable Bypass
```bash
curl -X PUT "http://localhost:8000/api/campaigns/{id}" \
  -H "Content-Type: application/json" \
  -d '{"direct_redirect_mode": true}'
```

### Disable Bypass
```bash
curl -X PUT "http://localhost:8000/api/campaigns/{id}" \
  -H "Content-Type: application/json" \
  -d '{"direct_redirect_mode": false}'
```

### Check Status
```bash
curl "http://localhost:8000/api/campaigns/{id}" | jq '.direct_redirect_mode'
```

### Test Flow
```bash
curl -L "http://localhost:8000/api/click?pub=PUB_ABC&site=SITE_XYZ"
```

### Watch Logs
```bash
tail -f ppc-backend/fastapi_debug.log | grep -E "ROUTE|BYPASS"
```

---

## Support

For issues during testing:

1. **Check logs first**: `tail -f ppc-backend/fastapi_debug.log`
2. **Verify database**: Check `direct_redirect_mode` field
3. **Clear cache**: Restart Redis if needed
4. **Run tests**: `pytest tests/test_bypass_simple.py -v`
5. **Review docs**: See `BYPASS_TRAFFIC_ROUTING_IMPLEMENTATION.md`

Happy testing! 🚀
