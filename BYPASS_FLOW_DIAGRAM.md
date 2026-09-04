# Traffic Routing Flow Diagrams

## Visual Comparison: Bypass OFF vs Bypass ON

### Flow 1: Bypass OFF (Default - Show Prelander)

```
┌─────────────────────┐
│ Publisher Smartlink │  User clicks affiliate link
│   (Entry Point)     │  Example: https://click.example.com/?pub=ABC&site=XYZ
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   Anchor Domain     │  Generates session cookies
│ (Link Domain Type)  │  Sets tracking parameters
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   Inter Domain      │  ✅ Click logging happens HERE
│  (/click endpoint)  │  ✅ Fraud detection runs HERE
│ (Intermediate Type) │  ✅ GEO/Device targeting HERE
└──────────┬──────────┘  ✅ Campaign selection HERE
           │
           │ route_click() returns: "https://prelander.com/d/abc123"
           ▼
┌─────────────────────┐
│  Prelander Domain   │  Shows template page
│   (Last Domain)     │  User sees: instructions, video, countdown, etc.
│   /d/{slug}         │  Prelander decodes slug to get campaign info
└──────────┬──────────┘
           │
           │ User clicks button or auto-redirect after delay
           ▼
┌─────────────────────┐
│   Campaign URL      │  Final destination
│  (Offer Landing)    │  Example: https://offer.com/product?aff=123
└─────────────────────┘
```

**Total Hops:** 4 redirects
**Time:** ~1-3 seconds (includes prelander page load)
**Use Case:** When you want to show branded content, collect info, or present instructions

---

### Flow 2: Bypass ON (Direct - Skip Prelander)

```
┌─────────────────────┐
│ Publisher Smartlink │  User clicks affiliate link
│   (Entry Point)     │  Example: https://click.example.com/?pub=ABC&site=XYZ
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   Anchor Domain     │  Generates session cookies
│ (Link Domain Type)  │  Sets tracking parameters
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   Inter Domain      │  ✅ Click logging happens HERE (same as bypass OFF)
│  (/click endpoint)  │  ✅ Fraud detection runs HERE (same as bypass OFF)
│ (Intermediate Type) │  ✅ GEO/Device targeting HERE (same as bypass OFF)
└──────────┬──────────┘  ✅ Campaign selection HERE (same as bypass OFF)
           │
           │ route_click() returns: "https://offer.com/product?aff=123"
           │ (SKIPS prelander domain entirely)
           ▼
┌─────────────────────┐
│   Campaign URL      │  Final destination (direct)
│  (Offer Landing)    │  Example: https://offer.com/product?aff=123
└─────────────────────┘  No prelander page shown
```

**Total Hops:** 3 redirects
**Time:** ~500ms-1s (no prelander page load)
**Use Case:** When speed is critical or prelander not needed

---

## Key Differences

| Aspect | Bypass OFF | Bypass ON |
|--------|------------|-----------|
| **Final Destination** | Prelander Domain → Campaign URL | Direct to Campaign URL |
| **User Sees Prelander** | ✅ Yes | ❌ No |
| **Total Redirects** | 4 hops | 3 hops |
| **Speed** | Slower (+prelander load) | Faster |
| **Anchor Domain** | ✅ Used | ✅ Used |
| **Inter Domain (Logging)** | ✅ Used | ✅ Used |
| **Click Logged** | ✅ Yes | ✅ Yes |
| **Fraud Detection** | ✅ Yes | ✅ Yes |
| **Session Tracking** | ✅ Yes | ✅ Yes |

---

## Code Flow in traffic_router.py

```python
async def route_click(click_data: dict, db, redis):
    # Step 1-3: Common for both modes
    campaign_id = await resolve_campaign_for_click(click_data, db)
    context = ClickContext(...)
    engine = TargetingEngine(db, redis)
    campaign_url, referrer_suppression, metadata = await engine.resolve_destination(context)
    
    # Step 4: Check bypass status
    is_bypass_on = False
    
    campaign = await db.campaigns.find_one({"_id": campaign_id})
    if campaign.get("direct_redirect_mode"):
        is_bypass_on = True
    
    # Step 5: Return appropriate destination
    if is_bypass_on:
        # BYPASS ON: Return campaign URL directly
        return campaign_url, referrer_suppression
    else:
        # BYPASS OFF: Build prelander URL
        prelander_url = build_prelander_url(...)
        return prelander_url, referrer_suppression
```

---

## URL Examples

### Bypass OFF - Returns Prelander URL
```
Input:  Click on https://click.example.com/?pub=PUB_ABC&site=SITE_XYZ
Output: https://prelander.example.com/d/Zm9vYmFyMTIz

User journey:
1. Click smartlink
2. → Anchor domain (cookie set)
3. → Inter domain (click logged) 
4. → Prelander page (template shown)
5. → Campaign URL (final destination)
```

### Bypass ON - Returns Campaign URL
```
Input:  Click on https://click.example.com/?pub=PUB_ABC&site=SITE_XYZ
Output: https://offer.com/product?aff=123

User journey:
1. Click smartlink
2. → Anchor domain (cookie set)
3. → Inter domain (click logged)
4. → Campaign URL (final destination, no prelander)
```

---

## Database Configuration

### Campaign Document
```javascript
{
  "_id": ObjectId("..."),
  "name": "My Campaign",
  "default_offer_url": "https://offer.com/product",
  "direct_redirect_mode": false,  // ← Controls bypass
  // false = Bypass OFF (show prelander)
  // true  = Bypass ON (skip prelander)
  ...
}
```

### Offer Document (Overrides Campaign)
```javascript
{
  "_id": ObjectId("..."),
  "campaign_id": ObjectId("..."),
  "offer_url": "https://special-offer.com/deal",
  "direct_redirect_mode": true,  // ← Overrides campaign setting
  ...
}
```

---

## Decision Tree

```
Start: User clicks smartlink
    ↓
Anchor Domain (session cookie)
    ↓
Inter Domain (/click endpoint)
    ↓
    ├─ Log click to database
    ├─ Run fraud detection
    ├─ Apply GEO/device rules
    └─ Select campaign
        ↓
    Check: direct_redirect_mode?
        ↓
    ┌───────────┴───────────┐
    │                       │
Is Bypass ON?         Is Bypass OFF?
(true)                (false - default)
    │                       │
    ↓                       ↓
Return                Return
campaign_url          prelander_url
    │                       │
    ↓                       ↓
User sees             User sees
offer page            prelander page
directly                  │
                          ↓
                     Then redirects to
                     campaign_url
```

---

## Logging Output

### Bypass OFF Logs
```
[ROUTE] Matched campaign_id: 507f1f77bcf86cd799439011
[ROUTE] Targeting resolved: url=https://offer.com, rule_type=default, priority=0
[ROUTE] BYPASS OFF: Building prelander destination
[ROUTE] Prelander domain (last): https://prelander.example.com
[ROUTE] Final prelander URL: https://prelander.example.com/d/Zm9vYmFy
```

### Bypass ON Logs
```
[ROUTE] Matched campaign_id: 507f1f77bcf86cd799439011
[ROUTE] Targeting resolved: url=https://offer.com, rule_type=default, priority=0
[ROUTE] Bypass ON (campaign) — will skip prelander, go direct to campaign URL
[ROUTE] BYPASS MODE: Direct to campaign URL: https://offer.com
```

---

## Summary

**Both flows maintain:**
- ✅ Anchor domain (session cookies)
- ✅ Inter domain (click logging)
- ✅ Fraud detection
- ✅ GEO/device targeting
- ✅ Campaign selection

**The ONLY difference:**
- Bypass OFF → Final destination is prelander URL
- Bypass ON → Final destination is campaign URL

**The choice is controlled by:**
- Campaign-level: `campaign.direct_redirect_mode`
- Offer-level: `offer.direct_redirect_mode` (overrides campaign)
