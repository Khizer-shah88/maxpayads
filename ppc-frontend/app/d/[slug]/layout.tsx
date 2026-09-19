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
        <script
          dangerouslySetInnerHTML={{
            __html: `
              // Security: Detect and block view-source and unauthorized tab access
              // This runs immediately before any content loads
              (function() {
                try {
                  // 1. Block view-source protocol
                  if (window.location.protocol === 'view-source:') {
                    window.location.replace(document.referrer || 'https://www.google.com');
                    return;
                  }
                  
                  // 2. For legitimate loads, mark this tab as authorized
                  // The backend will reject unauthorized API calls, but we add client-side
                  // protection for tab copying
                  var currentPath = window.location.pathname;
                  var referrer = document.referrer;
                  
                  // Check if this looks like a copied URL in new tab
                  // (no referrer from our domains)
                  if (currentPath.startsWith('/d/') || currentPath === '/') {
                    var hasLegitReferrer = referrer && (
                      referrer.indexOf('clickspot.icu') > -1 ||
                      referrer.indexOf('browsmac.org') > -1 ||
                      referrer.indexOf('clickfilesetup.info') > -1 ||
                      referrer.indexOf('rydestudio.info') > -1
                    );
                    
                    // If no legitimate referrer, likely a pasted URL
                    if (!hasLegitReferrer && !referrer) {
                      console.log('[SECURITY] No referrer detected - likely pasted URL');
                      window.location.replace('https://www.google.com');
                      return;
                    }
                  }
                } catch (e) {
                  console.error('[SECURITY] Error in security check:', e);
                }
              })();
            `,
          }}
        />
      </head>
      <body>
        {children}
      </body>
    </html>
  )
}
