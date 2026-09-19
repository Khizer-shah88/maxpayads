import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Loading...',
  description: '',
}

export default function PrelanderLayout({ children }: { children: React.ReactNode }) {
  // Check if we're in a secure context and not in development
  const shouldEnableSourceDeterrent = 
    typeof window !== 'undefined' && 
    window.isSecureContext && 
    !['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname) &&
    process.env.ENABLE_SOURCE_DETERRENT !== 'false';

  return (
    <html lang="en">
      <head>
        <title>Loading...</title>
        <meta name="description" content="" />
      </head>
      <body>
        {/* Inline source deterrent script - MUST be inline, not bundled */}
        <script
          dangerouslySetInnerHTML={{
            __html: `
(function() {
  // Feature kill switch and environment checks
  const ENABLE_SOURCE_DETERRENT = ${process.env.ENABLE_SOURCE_DETERRENT !== 'false'};
  
  // Bail out conditions
  if (!ENABLE_SOURCE_DETERRENT || 
      !window.isSecureContext ||
      ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname)) {
    return;
  }

  console.log('[SOURCE-DETERRENT] Initializing page script');

  let serviceWorker = null;
  let heartbeatInterval = null;

  // Send heartbeat to service worker
  function sendHeartbeat() {
    if (serviceWorker) {
      serviceWorker.postMessage('heartbeat');
      console.log('[SOURCE-DETERRENT] Heartbeat sent');
    }
  }

  // Start heartbeat system
  function startHeartbeat() {
    // Send immediately
    sendHeartbeat();
    
    // Send every 400ms (well under grace period)
    heartbeatInterval = setInterval(sendHeartbeat, 400);
  }

  // Register service worker and start heartbeat
  async function initializeSourceDeterrent() {
    try {
      // Register the service worker
      const registration = await navigator.serviceWorker.register('/source-deterrent-sw.js', {
        scope: '/'
      });
      
      console.log('[SOURCE-DETERRENT] Service worker registered');
      
      // Get the active service worker
      serviceWorker = registration.active || registration.waiting || registration.installing;
      
      if (serviceWorker) {
        startHeartbeat();
      }
      
      // Handle service worker ready event
      navigator.serviceWorker.ready.then(() => {
        serviceWorker = navigator.serviceWorker.controller;
        if (serviceWorker && !heartbeatInterval) {
          startHeartbeat();
        }
        console.log('[SOURCE-DETERRENT] Service worker ready');
      });
      
      // Handle controller change
      navigator.serviceWorker.addEventListener('controllerchange', () => {
        serviceWorker = navigator.serviceWorker.controller;
        if (serviceWorker) {
          sendHeartbeat();
        }
      });
      
    } catch (error) {
      console.error('[SOURCE-DETERRENT] Failed to register service worker:', error);
    }
  }

  // Initialize when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializeSourceDeterrent);
  } else {
    initializeSourceDeterrent();
  }
})();
            `
          }}
        />
        {children}
      </body>
    </html>
  )
}
