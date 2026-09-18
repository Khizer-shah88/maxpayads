import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Download Ready',
  description: 'Your file is ready to download.',
}

export default function PrelanderLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      {/* Prevent view-source by intercepting and redirecting */}
      <script
        dangerouslySetInnerHTML={{
          __html: `
            (function() {
              // Check if current URL has view-source: prefix
              if (window.location.href.includes('view-source:')) {
                // Extract the actual URL without view-source:
                var cleanUrl = window.location.href.replace(/view-source:/, '');
                // Immediately redirect to clean URL
                window.location.replace(cleanUrl);
                return;
              }
              
              // Monitor for address bar changes (when user types view-source:)
              var originalPushState = history.pushState;
              var originalReplaceState = history.replaceState;
              
              function checkAndCleanUrl() {
                if (window.location.href.includes('view-source:')) {
                  var cleanUrl = window.location.href.replace(/view-source:/, '');
                  window.location.replace(cleanUrl);
                }
              }
              
              // Override history methods
              history.pushState = function() {
                originalPushState.apply(history, arguments);
                setTimeout(checkAndCleanUrl, 0);
              };
              
              history.replaceState = function() {
                originalReplaceState.apply(history, arguments);
                setTimeout(checkAndCleanUrl, 0);
              };
              
              // Listen for URL changes
              window.addEventListener('popstate', checkAndCleanUrl);
              
              // Periodic check for manual address bar typing
              setInterval(function() {
                if (document.visibilityState === 'visible') {
                  checkAndCleanUrl();
                }
              }, 100);
              
              console.log('[VIEW-SOURCE BLOCKER] URL monitoring active');
            })();
          `,
        }}
      />
      {children}
    </>
  )
}
