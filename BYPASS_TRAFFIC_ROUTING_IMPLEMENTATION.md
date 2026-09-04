# Bypass Traffic Routing Implementation

## Overview

The bypass feature controls whether traffic goes through the prelander page or directly to the campaign URL. This document explains how the two routing flows work.

## Two Traffic Flows

### Flow 1: Bypass OFF (Default)

When `direct_redirect_mode = False` (bypass is OFF), traffic follows the complete flow through all domains:

```
Publisher Smartlink
    ↓
Anchor Domain (generates session cookies)
    ↓
Inter Domain (validates cookies, logs click)
    ↓
Prelander Domain (last domain - shows template)
    ↓
Campaign URL (final destination)
```

**Key Points:**
- User sees the prelander template page
- All domains in the chain are utilized
- Full session tracking and validation
- Logging happens at the Inter Domain stage
- Prelander can show custom templates, videos, instructions, etc.

### Flow 2: Bypass ON

When `direct_redirect_mode = True` (bypass is ON), the prelander is skipped:

```
Publisher Smartlink
    ↓
Anchor Domain (generates session cookies)
    ↓
Inter Domain (validates cookies, logs click)
    ↓
Direct Campaign URL (skip prelander entirely)
```

**Key Points:**
- User never sees the prelander page
- Goes straight to the campaign/offer URL
- Still passes through Anchor and Inter domains for logging
- Session tracking and click logging still occur
- Faster redirect to final destination

## Implementation Details

### 1. Database Schema

The bypass setting is stored in two collections:

#### Campaigns Collection
```javascript
{
  "_id": ObjectId,
  "name": "Campaign Name",
  "default_offer_url": "https://offer.com",
  "direct_redirect_mode": false,  // false = Bypass OFF, true = Bypass ON
  ...
}
```

#### Offers Collection
```javascript
{
  "_id": ObjectId,
  "campaign_id": ObjectId,
  "offer_url": "https://offer.com",
  "direct_redirect_mode": false,  // Offer-level bypass override
  ...
}
```

### 2. Traffic Router Logic

Location: `ppc-backend/app/services/traffic_router.py`

The `route_click()` function handles the bypass logic:

```python
async def route_click(click_data: dict, db, redis) -> Tuple[str, bool]:
    # Step 1-3: Resolve campaign and targeting rules
    campaign_id = await resolve_campaign_for_click(click_data, db)
    context = ClickContext(...)
    engine = TargetingEngine(db, redis)
    resolved_offer_url, referrer_suppression, metadata = await engine.resolve_destination(context)
    
    # Step 4: Check bypass status
    is_bypass_on = False
    
    # Check campaign-level bypass
    campaign = await db.campaigns.find_one({"_id": campaign_id})
    if campaign and campaign.get("direct_redirect_mode"):
        is_bypass_on = True
    
    # Check offer-level bypass (takes precedence)
    if metadata.get("rule_type") == "offer":
        offer = await db.offers.find_one({"_id": metadata["source_id"]})
        if offer and offer.get("direct_redirect_mode"):
            is_bypass_on = True
    
    # Step 5: Return destination based on bypass status
    if is_bypass_on:
        # BYPASS ON: Return campaign URL directly
        return resolved_offer_url, referrer_suppression
    else:
        # BYPASS OFF: Build prelander URL
        prelander_url = build_prelander_url(campaign_id, ...)
        return prelander_url, referrer_suppression
```

### 3. Click Endpoint Flow

Location: `ppc-backend/app/routers/click_router.py`

The `/click` endpoint is the **Inter Domain** in the chain:

```python
@router.get("/click")
async def track_click(request: Request, pub: str, site: str, ...):
    # 1. Extract metadata (IP, user agent, country, etc.)
    # 2. Fraud detection
    # 3. Log click to database
    # 4. Route traffic (calls route_click)
    destination, referrer_suppression = await route_click(click_data, db, redis)
    # 5. Redirect to destination (prelander or direct URL)
    return build_redirect(destination, referrer_suppression)
```

**This endpoint always runs** regardless of bypass status. It logs the click and then:
- **Bypass OFF**: Redirects to prelander domain (last domain)
- **Bypass ON**: Redirects to campaign URL directly

### 4. Domain Chain Components

#### Anchor Domain
- Entry point for traffic
- Generates session cookies
- Redirects to Inter Domain
- Implementation: `app/middleware/redirect_chain_middleware.py` (if using redirect chains)

#### Inter Domain (Click Endpoint)
- `/click` endpoint at `ppc-backend/app/routers/click_router.py`
- Validates session cookies
- Logs click to database
- Performs fraud detection
- Routes to final destination (prelander or direct)

#### Prelander Domain (Last Domain)
- Only reached when **Bypass OFF**
- Serves prelander template at `/d/{slug}`
- Frontend: `ppc-frontend/app/d/[slug]/page.tsx`
- Shows custom content, then redirects to campaign URL

### 5. Prelander URL Structure

When Bypass OFF, the system generates an encrypted slug URL:

```
Format: https://last-domain.com/d/{encrypted_slug}

Example: https://prelander.example.com/d/Zm9vYmFy

Slug encoding:
- Contains: OS type, timestamp, offer_id, campaign_id, country_code
- Encrypted with XOR cipher + base64url encoding
- Decoded on prelander page to determine what template to show
```

## Configuration

### Setting Bypass Status

#### Via Admin Panel
1. Go to **Campaigns** → Select campaign
2. Toggle **Direct Redirect Mode** switch
3. ON = Bypass (skip prelander)
4. OFF = Normal flow (show prelander)

#### Via API
```bash
# Update campaign
PUT /api/campaigns/{campaign_id}
{
  "direct_redirect_mode": true  // or false
}

# Update offer
PUT /api/offers/{offer_id}
{
  "direct_redirect_mode": true  // or false
}
```

### Domain Configuration

Domains must be configured for the flow to work:

1. **Link Domain** (Anchor Domain): Entry point for smartlinks
   - Example: `click.example.com`
   - Used in publisher smartlinks

2. **Intermediate Domain** (Inter Domain): Click processing
   - Example: `track.example.com`
   - Hosts the `/click` endpoint

3. **Last Domain** (Prelander Domain): Template hosting
   - Example: `prelander.example.com`
   - Only used when Bypass OFF
   - Serves prelander templates

Configure in: **Admin → Domains**

## Testing

### Test Bypass OFF (Default Flow)

1. Create a campaign with `direct_redirect_mode = false`
2. Generate a smartlink
3. Click the link
4. Expected flow:
   - Click endpoint logs the visit
   - Redirects to prelander domain `/d/{slug}`
   - Prelander page loads (shows template)
   - After delay or button click → redirects to campaign URL

**Verify:**
- Check database: `db.clicks` has a record
- Log shows: `[ROUTE] BYPASS OFF: Building prelander destination`
- Browser URL changes to prelander domain
- Prelander template is visible

### Test Bypass ON (Direct Flow)

1. Update campaign: `direct_redirect_mode = true`
2. Generate a smartlink
3. Click the link
4. Expected flow:
   - Click endpoint logs the visit
   - Redirects directly to campaign URL (no prelander)

**Verify:**
- Check database: `db.clicks` has a record
- Log shows: `[ROUTE] BYPASS MODE: Direct to campaign URL`
- Browser URL changes directly to campaign URL
- No prelander page is shown

### Logging

Check logs for routing decisions:

```bash
# Bypass OFF
[ROUTE] BYPASS OFF: Building prelander destination
[ROUTE] Prelander domain (last): https://prelander.example.com
[ROUTE] Final prelander URL: https://prelander.example.com/d/Zm9vYmFy

# Bypass ON
[ROUTE] Bypass ON (campaign) — will skip prelander, go direct to campaign URL
[ROUTE] BYPASS MODE: Direct to campaign URL: https://offer.com
```

## Performance Considerations

### Bypass OFF (Prelander Flow)
- **Redirects**: 2-3 (anchor → inter → prelander → campaign)
- **Load time**: Slower (additional prelander page load)
- **User experience**: Can show branded content, instructions, countdown
- **Use case**: When you want to show custom content or collect user info

### Bypass ON (Direct Flow)
- **Redirects**: 1-2 (anchor → inter → campaign)
- **Load time**: Faster (skips prelander page)
- **User experience**: Quickest path to destination
- **Use case**: When speed is critical or prelander not needed

## Security

Both flows maintain security:

1. **Session Validation**: Anchor domain sets cookies, Inter validates them
2. **Fraud Detection**: Runs at click endpoint regardless of bypass status
3. **Click Logging**: All clicks are logged for tracking and billing
4. **Encrypted Slugs**: Prelander slugs are encrypted and time-limited

## Troubleshooting

### Prelander Not Showing (Bypass OFF)
1. Check `direct_redirect_mode` is `false` in database
2. Verify "last" domain is configured in Admin → Domains
3. Check logs for `[ROUTE] BYPASS OFF` message
4. Ensure prelander templates exist

### Still Showing Prelander (Bypass ON)
1. Verify `direct_redirect_mode` is `true` in database
2. Clear cache (Redis + browser)
3. Check logs for `[ROUTE] BYPASS MODE` message
4. Test with fresh smartlink (not cached)

### Clicks Not Logging
1. Check `/click` endpoint is accessible
2. Verify database connection
3. Check fraud detection isn't blocking all traffic
4. Review click_router.py logs

## API Reference

### Get Campaign Details
```bash
GET /api/campaigns/{campaign_id}

Response:
{
  "id": "...",
  "name": "Campaign Name",
  "direct_redirect_mode": false,
  ...
}
```

### Update Bypass Setting
```bash
PUT /api/campaigns/{campaign_id}
{
  "direct_redirect_mode": true
}

Response:
{
  "success": true,
  "campaign": {...}
}
```

### Check Click Stats
```bash
GET /api/clicks?publisher_id={pub_id}&date_from=2024-01-01

Response:
{
  "clicks": [
    {
      "id": "...",
      "destination_url": "https://prelander.com/d/abc",  // or direct URL
      "status": "valid",
      ...
    }
  ]
}
```

## Summary

The bypass feature provides flexible traffic routing:

- **Bypass OFF**: Full flow with prelander (more control, slower)
- **Bypass ON**: Direct to campaign (faster, less control)

Both flows maintain:
- Click logging at Inter Domain
- Fraud detection
- Session tracking
- Security validation

The key difference is the **final destination** returned by `route_click()`:
- Bypass OFF → Returns prelander URL
- Bypass ON → Returns campaign URL directly

All other components (anchor, inter domain, logging) remain in the flow regardless of bypass status.
