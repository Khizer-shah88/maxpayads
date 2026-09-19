# 🧪 Source-View Deterrent Acceptance Testing

## **ACCEPTANCE TESTS - RUN EACH IN REAL BROWSER**

### **Test 1: View-Source with Installed Worker**
1. **Open Chrome/Chromium browser**
2. **Visit**: `http://localhost:3000/d/test123` (normal navigation)
3. **Wait 2 seconds** for service worker to install
4. **Press Ctrl+U** (or Cmd+U on Mac)
5. **Expected Result**: ✅ Lands on rendered page, NOT source text

### **Test 2: Fresh Profile (Worker Not Installed)**
1. **Open fresh browser profile** (Incognito or new profile)
2. **Press Ctrl+U** immediately on `http://localhost:3000/d/test123`
3. **Expected Result**: ✅ Shows source text (expected - worker not yet installed)

### **Test 3: JavaScript Disabled**
1. **Disable JavaScript** in browser settings
2. **Visit**: `http://localhost:3000/d/test123`
3. **Check network requests** (should be max 3 navigations)
4. **Expected Result**: ✅ Page readable, NO reload loop, stops at navigation limit

### **Test 4: cURL Unaffected**
```bash
curl -s http://localhost:3000/d/test123
```
**Expected Result**: ✅ Full HTML returned, completely unaffected

### **Test 5: Normal Navigation Latency**
1. **Measure before**: Time to load `http://localhost:3000/d/test123`
2. **Clear cache**, visit again to install worker
3. **Measure after**: Time to load same URL  
4. **Expected Result**: ✅ <5ms additional latency

### **Test 6: Kill Switch**
1. **Set environment**: `ENABLE_SOURCE_DETERRENT=false`
2. **Rebuild and restart** container
3. **Try Ctrl+U** on prelander page
4. **Expected Result**: ✅ Shows source (feature disabled)

### **Test 7: Service Worker Logs**
1. **Open DevTools** → Console
2. **Visit**: `http://localhost:3000/d/test123`
3. **Check for logs**: `[SOURCE-DETERRENT]` messages
4. **Expected Result**: ✅ Service worker registration and heartbeat logs visible

---

## **MANUAL TESTING INSTRUCTIONS**

### **Quick Test Command:**
```bash
# Test basic functionality
curl -I http://localhost:3000/source-deterrent-sw.js
# Should return: 200 OK with JavaScript Content-Type

# Test unregistration utility
curl -s http://localhost:3000/unregister-source-deterrent.js | head -10
# Should return: JavaScript unregistration code
```

### **Browser Console Test:**
```javascript
// Run in browser console on prelander page
navigator.serviceWorker.getRegistrations().then(regs => {
  console.log('Registered workers:', regs.length);
  regs.forEach(reg => console.log('Scope:', reg.scope));
});
```

### **Grace Period Measurement:**
```javascript
// Run in browser console to measure navigation-to-heartbeat time
const startTime = performance.now();
window.addEventListener('load', () => {
  const loadTime = performance.now() - startTime;
  console.log('Navigation to load:', loadTime + 'ms');
});
```

---

## **EXPECTED BROWSER BEHAVIOR**

### **Chrome/Chromium** ✅
- Service worker registers correctly
- Heartbeat system works
- View-source navigation redirects
- Grace period timing is accurate

### **Firefox** ❓
- **UNTESTED** - Service worker may not observe view-source navigation
- May not support `client.navigate()` method  
- Feature should be absent, not broken

### **Safari** ❓  
- **UNTESTED** - Service worker support varies
- May have different navigation behavior
- Feature should be absent, not broken

---

## **TROUBLESHOOTING GUIDE**

### **Service Worker Not Registering:**
```javascript
// Check in browser console
console.log('SW support:', 'serviceWorker' in navigator);
console.log('Secure context:', window.isSecureContext);
console.log('Hostname:', location.hostname);
```

### **No Heartbeat Messages:**
1. Check inline script is present in page source
2. Verify no JavaScript errors in console
3. Confirm service worker is active: `navigator.serviceWorker.controller`

### **View-Source Still Shows Source:**
1. Verify service worker installed: `navigator.serviceWorker.ready`
2. Check grace period hasn't expired
3. Confirm feature is enabled via environment variable

### **Infinite Reload Loop:**
1. Check navigation counter in service worker logs
2. Verify loop guard is active (max 3 navigations)
3. May indicate JavaScript execution issues

---

## **PERFORMANCE MEASUREMENTS**

### **Expected Latency Impact:**
- **Service Worker Registration**: One-time ~100ms  
- **Navigation Interception**: ~2-5ms per request
- **Heartbeat Overhead**: ~0.1ms every 400ms
- **Grace Period**: 1200ms (doesn't block page load)

### **Memory Usage:**
- **Service Worker**: ~50KB resident memory
- **Heartbeat Interval**: Minimal CPU impact
- **Client Set**: ~100 bytes per active tab

---

## **TESTING RESULTS LOG**

Record actual results for each test:

| Test | Expected | Actual | Status | Notes |
|------|----------|---------|---------|--------|
| 1. View-Source (Installed) | Rendered page | | | |
| 2. Fresh Profile | Source text | | | |
| 3. JS Disabled | No loop, max 3 req | | | |
| 4. cURL | Full HTML | | | |
| 5. Latency | <5ms added | | | |
| 6. Kill Switch | Feature disabled | | | |
| 7. Worker Logs | Console messages | | | |

---

## **SECURITY DISCLAIMERS**

### **⚠️ WHAT THIS DOES NOT STOP:**
- **DevTools Network tab** - Shows full HTML response
- **DevTools Elements tab** - Shows rendered DOM
- **"Save page as"** - Saves complete HTML
- **cURL/wget/any HTTP client** - Gets raw HTML
- **First visit** - Before service worker installs
- **Shared links** - HTML already downloaded

### **🎯 WHAT THIS DETERS:**
- **Casual Ctrl+U / Cmd+U** - Redirects to rendered page
- **View-source: URL scheme** - Shows page instead of source

### **📝 NOT A SECURITY CONTROL:**
This is a **deterrent only**. The HTML source code remains fully accessible through multiple methods. Do not present this as security or protection.

**This fires on any JS-less context, not specifically on view-source.**