# Smartlink Structure System - Quick Start Guide

## 🚀 Quick Access

**Admin Panel:** `http://localhost/admin` → **Smartlink Structures**

---

## 📋 Default Structures (Auto-Seeded)

| Name | Publisher Param | Website Param | Example |
|------|----------------|---------------|---------|
| **Standard** (Default) | `pub` | `site` | `?pub=PUB_XXX&site=SITE_YYY` |
| **Tag + SID** | `tag` | `sid` | `?tag=PUB_XXX&sid=SITE_YYY` |
| **Tag Only** | `tag` | None | `?tag=PUB_XXX` |

---

## ⚡ Quick Actions

### Generate a Smartlink (Admin Panel)
1. Go to **Smartlink Structures** page
2. Scroll to **"Smartlink Generator"**
3. Select structure (or use default)
4. Enter **Publisher ID**: `PUB_LUKLLIZW`
5. Enter **Site ID** (optional): `SITE_2PRBE5E1`
6. Click **"Generate Smartlink"**
7. **Copy** the generated link

### Create Custom Structure (Admin Panel)
1. Click **"Add Structure"**
2. Enter **Name**: e.g., "Affiliate Tracker"
3. **Publisher Parameter**: e.g., `aff`
4. **Website Parameter**: e.g., `placement`
5. Toggle **"Include website parameter"**
6. Add **Extra Static Parameters** (optional):
   - Key: `utm_source`, Value: `network`
7. Set **Status**: Active
8. Check **"Set as default"** (optional)
9. Preview shows: `https://{DOMAIN}/?aff={PUB}&placement={SITE}&utm_source=network`
10. Click **"Create Structure"**

---

## 🔗 Link Examples

### Standard Structure
```
https://trustedcloudmedia.com/?pub=PUB_LUKLLIZW&site=SITE_2PRBE5E1
```

### Tag + SID Structure
```
https://trustedcloudmedia.com/?tag=PUB_LUKLLIZW&sid=SITE_2PRBE5E1
```

### Tag Only Structure
```
https://trustedcloudmedia.com/?tag=PUB_LUKLLIZW
```

### Custom Structure with Extra Params
```
https://trustedcloudmedia.com/?aff=PUB_XXX&placement=SITE_YYY&utm_source=network&utm_medium=cpc
```

---

## 🧪 Quick Test

### Test in Browser
```
http://localhost:8000/click?pub=PUB_TEST123&site=SITE_TEST456
http://localhost:8000/click?tag=PUB_TEST123&sid=SITE_TEST456
http://localhost:8000/click?tag=PUB_TEST123
```

### Check Which Structure Matched
```bash
docker logs ppc_fastapi | grep "Smartlink Parser"
```

Expected output:
```
[Smartlink Parser] Matched structure 'Standard' (pub=PUB_TEST123, site=SITE_TEST456)
```

---

## 🛠️ API Quick Reference

### Generate Smartlink via API
```bash
curl -X POST http://localhost:8000/admin/smartlink-structures/generate \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "publisher_id": "PUB_LUKLLIZW",
    "site_id": "SITE_2PRBE5E1"
  }'
```

### Create Structure via API
```bash
curl -X POST http://localhost:8000/admin/smartlink-structures \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Structure",
    "publisher_param": "aff",
    "website_param": "src",
    "include_website": true,
    "extra_params": [],
    "is_default": false,
    "status": "active"
  }'
```

### List All Structures
```bash
curl http://localhost:8000/admin/smartlink-structures \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## 🔍 Troubleshooting

### Issue: No structures found
**Solution:**
```bash
# Check if seeding completed
docker exec -it ppc_mongodb mongosh
use ppc_network
db.smartlink_structures.find().pretty()

# If empty, run seed manually:
docker exec -it ppc_fastapi python app/seed/seed_smartlink_structures.py
```

### Issue: Link not working
**Solution:**
1. Check logs: `docker logs ppc_fastapi | grep "Smartlink Parser"`
2. Verify structure is active: Admin Panel → Smartlink Structures
3. Try legacy format: `?pub=XXX&site=YYY` (always works)

### Issue: Can't access admin panel
**Solution:**
```bash
# Default credentials:
Email: admin@maxpayads.com
Password: Admin@123456

# Or check .env file for ADMIN_EMAIL and ADMIN_PASSWORD
```

---

## 📚 Full Documentation

See **SMARTLINK_STRUCTURE_SYSTEM.md** for complete documentation.

---

## ✅ Checklist After Deployment

- [ ] Login to admin panel
- [ ] Navigate to Smartlink Structures
- [ ] Verify 3 default structures exist
- [ ] Generate a test smartlink
- [ ] Click the test link and verify redirect works
- [ ] Check logs for structure matching

---

**Need Help?** Check the full documentation in `SMARTLINK_STRUCTURE_SYSTEM.md`
