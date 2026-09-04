# Bypass Feature - Quick Reference

## 🎯 What It Does

Controls whether traffic sees a prelander page or goes directly to the campaign URL.

## 🔀 Two Modes

### Bypass OFF (Default)
```
Smartlink → Anchor → Inter → Prelander → Campaign URL
Shows prelander template
```

### Bypass ON
```
Smartlink → Anchor → Inter → Campaign URL
Skips prelander, goes direct
```

## ⚙️ Enable/Disable

### Via API
```bash
# Enable bypass (skip prelander)
PUT /api/campaigns/{campaign_id}
{"direct_redirect_mode": true}

# Disable bypass (show prelander)
PUT /api/campaigns/{campaign_id}
{"direct_redirect_mode": false}
```

### Via Admin Panel
1. Go to Campaigns → Select campaign
2. Toggle "Direct Redirect Mode"
3. Save

## ✅ What Changed

### Modified Files
- `ppc-backend/app/services/traffic_router.py` (routing logic + URL cleaning)

### New Files
- `BYPASS_README.md` - Overview
- `BYPASS_IMPLEMENTATION_SUMMARY.md` - What was implemented
- `BYPASS_TRAFFIC_ROUTING_IMPLEMENTATION.md` - Complete technical docs
- `BYPASS_FLOW_DIAGRAM.md` - Visual diagrams
- `BYPASS_TESTING_GUIDE.md` - Testing procedures
- `URL_CLEANING_FIX.md` - URL cleaning fix documentation
- `tests/test_bypass_simple.py` - 12 passing tests

## 🐛 URL Fix

**Problem:** URLs like `https://domain.cc/https/examplewin.com`  
**Solution:** Automatic cleaning to `https://examplewin.com`

The traffic router now automatically cleans malformed URLs:
- ✅ Removes domain prefixes (`/https/` or `/http/`)
- ✅ Adds missing protocol
- ✅ Handles empty values
- ✅ Logs all cleaning actions

## 📊 Test Results

```
12 tests passing ✅
- 8 bypass logic tests
- 4 URL cleaning tests
```

Run tests:
```bash
cd ppc-backend
.venv-linux/bin/python -m pytest tests/test_bypass_simple.py -v
```

## 🔍 Verify It Works

### Check Logs
```bash
tail -f ppc-backend/fastapi_debug.log | grep -E "ROUTE|BYPASS|URL CLEAN"
```

### Bypass OFF Logs
```
[ROUTE] BYPASS OFF: Building prelander destination
[ROUTE] Final prelander URL: https://prelander.com/d/abc123
```

### Bypass ON Logs
```
[ROUTE] Bypass ON (campaign) — will skip prelander
[URL CLEAN] Removed domain prefix, extracted: https://examplewin.com
[ROUTE] BYPASS MODE: Direct to campaign URL: https://examplewin.com
```

## 🎓 Documentation

### Quick Start
→ Read: `BYPASS_README.md`

### Implementation Details
→ Read: `BYPASS_IMPLEMENTATION_SUMMARY.md`

### Technical Deep Dive
→ Read: `BYPASS_TRAFFIC_ROUTING_IMPLEMENTATION.md`

### Visual Understanding
→ Read: `BYPASS_FLOW_DIAGRAM.md`

### Testing & Debug
→ Read: `BYPASS_TESTING_GUIDE.md`

### URL Fix Details
→ Read: `URL_CLEANING_FIX.md`

## ⚡ Quick Commands

```bash
# Enable bypass
curl -X PUT "http://localhost:8000/api/campaigns/{id}" \
  -H "Content-Type: application/json" \
  -d '{"direct_redirect_mode": true}'

# Check status
curl "http://localhost:8000/api/campaigns/{id}" | jq '.direct_redirect_mode'

# Test click
curl -L "http://localhost:8000/api/click?pub=PUB_ABC&site=SITE_XYZ"

# Run tests
cd ppc-backend && .venv-linux/bin/python -m pytest tests/test_bypass_simple.py -v

# Watch logs
tail -f ppc-backend/fastapi_debug.log | grep BYPASS
```

## 📝 Key Points

✅ Both modes log clicks (logging always happens)  
✅ Both modes run fraud detection  
✅ Both modes apply GEO/device targeting  
✅ URLs are automatically cleaned (removes prefixes)  
✅ Offer-level bypass overrides campaign-level  
✅ Default is bypass OFF (show prelander)  
✅ No breaking changes  
✅ No database migration needed  

## 🚨 Common Issues

### Issue: Prelander still showing (bypass ON)
**Fix:** Check database `direct_redirect_mode` is `true`

### Issue: Malformed URL with domain prefix
**Fix:** Already fixed! URLs auto-cleaned now

### Issue: Clicks not logging
**Fix:** Check `/click` endpoint accessible, DB connected

### Issue: Wrong destination URL
**Fix:** Check logs for `[URL CLEAN]` messages

## 🎉 Summary

**Status:** ✅ Fully implemented and tested  
**Tests:** ✅ 12 passing  
**URL Fix:** ✅ Automatic cleaning  
**Breaking Changes:** ❌ None  
**Ready:** ✅ Production ready  

Two simple modes:
- **Bypass OFF** = Show prelander (default)
- **Bypass ON** = Direct to campaign (fast)

Everything else stays the same! 🚀
