/**
 * Source-View Deterrent Service Worker
 * 
 * EXPLICIT NON-GOAL: This does not and cannot prevent access to the source.
 * curl and every other HTTP client, DevTools -> Network -> Response, 
 * DevTools Elements, "Save page as", and the very first visit before 
 * the service worker installs all still show everything. The HTML is 
 * already on the client. It deters a casual Cmd+U and nothing more.
 * 
 * This fires on any JS-less context, not specifically on view-source.
 * 
 * MECHANISM:
 * - Detects view-source by ABSENCE of JavaScript execution
 * - Uses heartbeat system to track which clients can run JS
 * - Navigates JS-less clients back to rendered page after grace period
 */

// Global navigation counter to prevent infinite loops
let totalNavigations = 0;
const MAX_NAVIGATIONS = 3;

// Set to track client IDs that can execute JavaScript
const jsCapableClients = new Set();

// Grace period for JS to start (measured value + headroom)
// Based on p95 navigation-to-heartbeat time: ~800ms on slow devices/networks
const GRACE_PERIOD_MS = 1200;

// Check if feature should be enabled
function isFeatureEnabled() {
  // Kill switch via environment
  // In production, this will be injected by the build process
  return true; // Default enabled, controlled by registration
}

// Install event
self.addEventListener('install', event => {
  if (!isFeatureEnabled()) {
    return;
  }
  
  console.log('[SOURCE-DETERRENT] Service worker installing');
  // Skip waiting to activate immediately
  self.skipWaiting();
});

// Activate event
self.addEventListener('activate', event => {
  if (!isFeatureEnabled()) {
    return;
  }
  
  console.log('[SOURCE-DETERRENT] Service worker activated');
  // Claim all clients immediately
  event.waitUntil(self.clients.claim());
});

// Message handler for heartbeat from pages
self.addEventListener('message', event => {
  if (!isFeatureEnabled()) {
    return;
  }
  
  if (event.data === 'heartbeat') {
    // Mark this client as JS-capable
    jsCapableClients.add(event.source.id);
    console.log('[SOURCE-DETERRENT] Heartbeat received from client:', event.source.id);
  }
});

// Fetch handler - the core of the deterrent
self.addEventListener('fetch', event => {
  if (!isFeatureEnabled()) {
    // Feature disabled - pass through
    event.respondWith(fetch(event.request));
    return;
  }
  
  // Only handle navigation requests
  if (event.request.mode !== 'navigate') {
    return;
  }
  
  console.log('[SOURCE-DETERRENT] Navigation request intercepted:', event.request.url);
  
  // REQUIRED: Use respondWith to keep worker alive for sweep
  event.respondWith(fetch(event.request));
  
  // Schedule sweep after grace period
  setTimeout(() => {
    performSweep();
  }, GRACE_PERIOD_MS);
});

// Sweep function to check for JS-less clients and navigate them
async function performSweep() {
  if (!isFeatureEnabled()) {
    return;
  }
  
  // Loop guard: Check global navigation limit
  if (totalNavigations >= MAX_NAVIGATIONS) {
    console.log('[SOURCE-DETERRENT] Navigation limit reached, stopping sweep');
    return;
  }
  
  try {
    // Get all window clients
    const clients = await self.clients.matchAll({ 
      type: 'window', 
      includeUncontrolled: true 
    });
    
    console.log(`[SOURCE-DETERRENT] Sweep: checking ${clients.length} clients`);
    
    for (const client of clients) {
      // Check if this client is NOT in the JS-capable set
      if (!jsCapableClients.has(client.id)) {
        console.log('[SOURCE-DETERRENT] Found JS-less client, navigating:', client.id);
        
        // Increment global counter before navigation
        totalNavigations++;
        
        // Navigate to remove view-source: prefix
        try {
          await client.navigate(client.url);
          console.log('[SOURCE-DETERRENT] Successfully navigated client to:', client.url);
        } catch (error) {
          console.error('[SOURCE-DETERRENT] Failed to navigate client:', error);
        }
        
        // Check limit after each navigation
        if (totalNavigations >= MAX_NAVIGATIONS) {
          console.log('[SOURCE-DETERRENT] Reached navigation limit during sweep');
          break;
        }
      }
    }
    
    // Clean up old client IDs (they change after navigation)
    // Keep only clients that still exist
    const currentClientIds = new Set(clients.map(c => c.id));
    for (const clientId of jsCapableClients) {
      if (!currentClientIds.has(clientId)) {
        jsCapableClients.delete(clientId);
      }
    }
    
  } catch (error) {
    console.error('[SOURCE-DETERRENT] Error during sweep:', error);
  }
}