# Prelander Security Test Guide

## How to Test the New Security Features

The system now has comprehensive protection against view-source and pasted URLs implemented at multiple levels:

### 1. Next.js Middleware Protection (Primary)
- **Location**: `ppc-frontend/middleware.ts`
- **Function**: Intercepts requests before they reach page components
- **Detects**: View-source requests and pasted URLs based on User-Agent and referrer patterns

### 2. Client-Side Protection (Fallback)
- **Location**: `ppc-frontend/app/d/[slug]/layout.tsx`
- **Function**: JavaScript that runs immediately when page loads
- **Detects**: Additional patterns like `view-source:` protocol

## Test Scenarios

### ✅ **Normal Flow (Should Work)**
1. Start from a publisher site (e.g., Wikipedia)
2. Click an anchor link that goes through the redirect flow
3. Should land on prelander domain and show content normally
4. Page reloads should work fine

### ❌ **View-Source Test (Should Redirect)**
1. Open any website (e.g., Facebook.com)
2. In address bar, type: `view-source:https://your-prelander-domain.com/d/abc123`
3. Press Enter
4. **Expected**: Should immediately redirect back to Facebook.com
5. **Should NOT**: Show page source code

### ❌ **Pasted URL Test (Should Redirect)**
1. Open any website (e.g., Facebook.com) 
2. Copy a prelander URL: `https://your-prelander-domain.com/d/abc123`
3. Paste it in the address bar and press Enter
4. **Expected**: Should immediately redirect back to Facebook.com
5. **Should NOT**: Show prelander content

### ❌ **New Tab Test (Should Redirect)**
1. Have a working prelander page open
2. Copy the URL from address bar
3. Open new tab and paste the URL
4. **Expected**: Should redirect to Google.com (no referrer)
5. **Should NOT**: Show prelander content

## How the Detection Works

### View-Source Detection
- **Middleware**: Checks for `view-source` in User-Agent header
- **Client**: Checks for `view-source:` protocol
- **Redirect**: Goes to original referrer or Google.com

### Pasted URL Detection  
- **No Referrer**: Request has no `referer` header
- **Direct Access**: Request path starts with `/d/` 
- **Browser Request**: Accept header includes `text/html`
- **Redirect**: Goes to Google.com (since no referrer available)

## Redirect Behavior

**When redirecting:**
- If `document.referrer` exists → Redirect to that site
- If no referrer → Redirect to `https://www.google.com`
- This means the URL gets cleared and user goes back to where they were

## Testing Tips

1. **Use Real Domains**: Test with actual prelander domains, not localhost
2. **Check Console**: Browser console shows security log messages
3. **Network Tab**: Check if redirects are happening at network level
4. **Multiple Browsers**: Test in Chrome, Firefox, Safari
5. **Incognito Mode**: Test in private browsing mode

## Expected Results

- **Legitimate users**: See prelander content normally
- **View-source attempts**: Get redirected, never see source code  
- **Pasted URLs**: Get redirected, URL disappears from address bar
- **No content exposure**: Unauthorized requests never see any prelander content

## Troubleshooting

If security isn't working:
1. Check browser console for error messages
2. Verify middleware is running (look for security log messages)
3. Test with network tab open to see redirect responses
4. Try different browsers and private browsing mode

The security works at multiple layers - even if one layer fails, others should catch unauthorized access attempts.