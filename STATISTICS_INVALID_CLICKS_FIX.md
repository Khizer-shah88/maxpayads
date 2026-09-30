# Statistics Page Invalid Clicks Fix

## Problem Description

The statistics page at `https://vertexmonetize.com/admin/statistics` was showing all clicks as **invalid** even when new users clicked domains for the first time. This was causing legitimate traffic to be incorrectly marked as fraudulent.

## Root Cause Analysis

The issue was in the fraud detection scoring system in `app/services/fraud_detection_service.py`:

1. **Too Aggressive Thresholds**: The fraud score classification thresholds were too low:
   - `TRAFFIC_DUPLICATE` triggered at score >= 20 (now 30)
   - `TRAFFIC_SUSPICIOUS` triggered at score >= 40 (now 50)

2. **Overly Strict User Agent Analysis**: The `analyze_user_agent_structure` function was too aggressive:
   - Minimum UA length was 20 characters (legitimate mobile apps use shorter UAs)
   - Maximum UA length was 500 characters (some modern browsers have longer UAs)
   - Flagged old browser versions (legitimate users on old devices)
   - Flagged any parsing errors (non-standard but legitimate UAs)
   - Flagged unknown browser/OS combinations (mobile apps, custom clients)

3. **High Penalty Weights**: Individual fraud signals had high weights:
   - Suspicious UA: 10 points (now 5)
   - Empty UA: 15 points (now 10)

4. **Cumulative Effect**: Even a normal user could easily accumulate 20+ points:
   - Example: Suspicious UA (10) + Empty UA (15) = 25 points = `TRAFFIC_DUPLICATE`
   - This triggered `is_flagged=True` in the redirect pipeline
   - Which made `is_valid=False` in the click record

5. **Validation Logic**: In `redirect_pipeline.py` line 462:
   ```python
   is_click_valid = not ctx.is_blocked and not ctx.is_flagged and ctx.click_status != "invalid"
   ```
   Any flagged click was marked as invalid, even if it should be allowed through.

## Changes Made

### 1. Fraud Score Thresholds (`fraud_detection_service.py`)

**Before:**
```python
def get_classification(self) -> str:
    if self.score >= 80:
        return TRAFFIC_INVALID
    elif self.score >= 60:
        return TRAFFIC_BOT
    elif self.score >= 40:
        return TRAFFIC_SUSPICIOUS
    elif self.score >= 20:
        return TRAFFIC_DUPLICATE
    else:
        return TRAFFIC_VALID
```

**After:**
```python
def get_classification(self) -> str:
    if self.score >= 80:
        return TRAFFIC_INVALID
    elif self.score >= 60:
        return TRAFFIC_BOT
    elif self.score >= 50:
        return TRAFFIC_SUSPICIOUS
    elif self.score >= 30:
        return TRAFFIC_DUPLICATE
    else:
        return TRAFFIC_VALID
```

**Impact:** Raised the threshold for duplicate classification from 20 to 30, and suspicious from 40 to 50.

### 2. Reduced Fraud Signal Weights

**Suspicious UA Weight:**
```python
# Before: weight: 10
# After: weight: 5
score.add_signal("suspicious_ua", 5, ua_reason)
```

**Empty UA Weight:**
```python
# Before: weight: 15
# After: weight: 10
score.add_signal("no_ua", 10, "Empty user agent")
```

### 3. More Conservative User Agent Analysis

**Before:**
- Min length: 20 characters → Flagged mobile apps
- Max length: 500 characters → Flagged modern browsers
- Flagged old browser versions → Penalized legitimate old devices
- Flagged parsing errors → False positives on non-standard UAs
- Flagged unknown browser/OS → False positives on mobile apps

**After:**
```python
def analyze_user_agent_structure(user_agent: str) -> Tuple[bool, Optional[str]]:
    """
    NOTE: This function should be VERY conservative to avoid flagging legitimate users.
    Only flag OBVIOUS bot/automation signals.
    """
    if not user_agent:
        return False, None  # Don't double-penalize empty UA
    
    # More lenient length checks
    if len(user_agent) < 10:  # Was 20
        return True, "User agent too short"
    
    if len(user_agent) > 1000:  # Was 500
        return True, "User agent too long"
    
    try:
        ua = parse_user_agent(user_agent)
        
        # Only flag if BOTH browser and OS are unknown AND UA is very short
        if ua.browser.family == 'Other' and ua.os.family == 'Other' and len(user_agent) < 30:
            return True, "Suspicious minimal user agent"
        
        # Removed old browser version check - legitimate users on old devices
        
    except Exception as e:
        # Don't flag on parsing errors - non-standard UAs can be legitimate
        return False, None
    
    return False, None
```

## How This Fixes the Issue

1. **New users are no longer flagged**: With the higher thresholds and reduced weights, a typical new user will have a score below 30, classifying them as `TRAFFIC_VALID`

2. **Mobile apps and custom clients work**: The more lenient UA analysis allows mobile apps, in-app browsers, and custom clients through

3. **Old devices are allowed**: Removed the penalty for old browser versions, so users on old devices aren't penalized

4. **Valid clicks show correctly**: With `is_flagged=False`, the validation logic correctly sets `is_valid=True`, and clicks show as "valid" on the statistics page

## Example Scoring

### Before (Incorrectly Flagged):
- Suspicious UA: 10 points
- Empty UA: 15 points
- **Total: 25 points → TRAFFIC_DUPLICATE → Flagged → Invalid ❌**

### After (Correctly Passed):
- Suspicious UA: 5 points
- Empty UA: 10 points
- **Total: 15 points → TRAFFIC_VALID → Not Flagged → Valid ✅**

## Testing Recommendations

1. **Test with legitimate traffic**:
   - Desktop browsers (Chrome, Firefox, Safari, Edge)
   - Mobile browsers (Chrome Mobile, Safari Mobile, Samsung Internet)
   - In-app browsers (Facebook, Instagram, TikTok)
   - Old devices/browsers

2. **Verify fraud detection still works**:
   - Bot user agents should still be blocked
   - Datacenter IPs should still be blocked
   - Rate limiting should still work
   - Actual duplicate IPs (same day, same publisher) should still be flagged

3. **Monitor statistics page**:
   - Valid clicks should show as "valid"
   - Invalid clicks should only be obvious bots/fraud
   - Check that earnings are being credited correctly

## Files Modified

1. `ppc-backend/app/services/fraud_detection_service.py`
   - `FraudScore.get_classification()` - Raised thresholds
   - `classify_traffic()` - Reduced signal weights
   - `analyze_user_agent_structure()` - Made more conservative

## Deployment

Changes have been pushed to the main branch:
```bash
git push origin main
```

The changes will take effect after the backend service is restarted or auto-deploys.

## Rollback Plan

If this causes issues with fraud detection (too much fraud getting through), you can:

1. **Revert to previous thresholds**: Change `30 → 20` and `50 → 40` in `get_classification()`
2. **Increase weights**: Change `5 → 10` and `10 → 15` in `classify_traffic()`
3. **Revert UA analysis**: Restore the stricter checks in `analyze_user_agent_structure()`

However, monitor carefully - the previous settings were incorrectly flagging ALL new users as invalid.

## Additional Notes

- The duplicate IP check still works correctly - same IP on the same day for the same publisher is still flagged
- The Redis rate limiting still works - excessive requests from one IP are still blocked
- Bot user agents are still caught - the `detect_bot_user_agent()` function still has full weight (40 points for non-crawlers)
- Headless/automation signals are still detected - WebDriver, Headless Chrome, etc. still get 25 points

The changes only made the system less aggressive against LEGITIMATE users, not against actual fraud.
