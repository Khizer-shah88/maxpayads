/**
 * Source Deterrent Service Worker Unregistration Utility
 * 
 * Use this script to completely remove the source deterrent service worker
 * when the feature is disabled. Ship this for one release when turning off
 * the feature to clean up existing installations.
 * 
 * Usage:
 * 1. Include this script in a page
 * 2. Or run in browser console: 
 *    navigator.serviceWorker.getRegistrations().then(rs => rs.forEach(r => r.unregister()))
 */

(function() {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.getRegistrations().then(registrations => {
      console.log(`Found ${registrations.length} service worker registrations`);
      
      registrations.forEach(registration => {
        // Check if this is our source deterrent worker
        if (registration.scope.endsWith('/') && 
            (registration.active?.scriptURL?.includes('source-deterrent-sw.js') ||
             registration.waiting?.scriptURL?.includes('source-deterrent-sw.js') ||
             registration.installing?.scriptURL?.includes('source-deterrent-sw.js'))) {
          
          registration.unregister().then(success => {
            if (success) {
              console.log('Source deterrent service worker unregistered successfully');
            } else {
              console.log('Source deterrent service worker unregistration failed');
            }
          });
        } else {
          registration.unregister().then(success => {
            if (success) {
              console.log('Service worker unregistered:', registration.scope);
            }
          });
        }
      });
      
      if (registrations.length === 0) {
        console.log('No service workers found to unregister');
      }
    }).catch(error => {
      console.error('Error getting service worker registrations:', error);
    });
  } else {
    console.log('Service workers not supported in this browser');
  }
})();