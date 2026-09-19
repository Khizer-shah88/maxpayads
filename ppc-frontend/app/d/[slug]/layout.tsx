import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Loading...',
  description: '',
}

export default function PrelanderLayout({ children }: { children: React.ReactNode }) {
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
  
  // Bail out conditions - check after page loads to access window
  function shouldBailOut() {
    return !ENABLE_SOURCE_DETERRENT || 
           !window.isSecureContext ||
           ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname);
  }

  let serviceWorker = null;
  let heartbeatInterval = null;

  // Send heartbeat to service worker
  function sendHeartbeat() {
    if (serviceWorker) {
      try {
        serviceWorker.postMessage('heartbeat');
        console.log('[SOURCE-DETERRENT] Heartbeat sent');
      } catch (error) {
        console.error('[SOURCE-DETERRENT] Failed to send heartbeat:', error);
      }
    }
  }

  // Start heartbeat system
  function startHeartbeat() {
    // Send immediately
    sendHeartbeat();
    
    // Send every 400ms (well under grace period)
    if (heartbeatInterval) {
      clearInterval(heartbeatInterval);
    }
    heartbeatInterval = setInterval(sendHeartbeat, 400);
  }

  // Register service worker and start heartbeat
  async function initializeSourceDeterrent() {
    // Check bail out conditions now that window is available
    if (shouldBailOut()) {
      console.log('[SOURCE-DETERRENT] Feature disabled or not in secure context');
      return;
    }

    // Check for service worker support
    if (!('serviceWorker' in navigator)) {
      console.log('[SOURCE-DETERRENT] Service worker not supported');
      return;
    }

    try {
      console.log('[SOURCE-DETERRENT] Initializing page script');

      // Register the service worker
      const registration = await navigator.serviceWorker.register('/source-deterrent-sw.js', {
        scope: '/'
      });
      
      console.log('[SOURCE-DETERRENT] Service worker registered:', registration.scope);
      
      // Get the active service worker
      if (registration.active) {
        serviceWorker = registration.active;
        startHeartbeat();
      } else if (registration.waiting) {
        serviceWorker = registration.waiting;
        startHeartbeat();
      } else if (registration.installing) {
        registration.installing.addEventListener('statechange', function() {
          if (this.state === 'activated') {
            serviceWorker = this;
            startHeartbeat();
          }
        });
      }
      
      // Handle service worker ready event - send heartbeat immediately when ready
      navigator.serviceWorker.ready.then((reg) => {
        serviceWorker = navigator.serviceWorker.controller || reg.active;
        if (serviceWorker) {
          startHeartbeat();
          console.log('[SOURCE-DETERRENT] Service worker ready and heartbeat started');
        }
      });
      
      // Handle controller change
      navigator.serviceWorker.addEventListener('controllerchange', () => {
        serviceWorker = navigator.serviceWorker.controller;
        if (serviceWorker) {
          startHeartbeat();
          console.log('[SOURCE-DETERRENT] Controller changed, restarted heartbeat');
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
