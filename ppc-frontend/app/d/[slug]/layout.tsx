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
              // Immediate security check before any content loads
              (function() {
                try {
                  // Additional view-source detection
                  if (window.location.protocol === 'view-source:') {
                    window.location.replace(document.referrer || 'https://www.google.com');
                    return;
                  }
                  
                  // Check if this looks like a pasted URL
                  var referrer = document.referrer;
                  var currentPath = window.location.pathname;
                  
                  // If no referrer and this is a /d/ page, likely pasted
                  if (!referrer && currentPath.startsWith('/d/')) {
                    console.log('[CLIENT-SECURITY] Pasted URL detected - redirecting');
                    window.location.replace('https://www.google.com');
                    return;
                  }
                } catch (e) {
                  // If security check fails, redirect as precaution
                  try {
                    window.location.replace('https://www.google.com');
                  } catch (e2) {
                    // Last resort
                    document.body.innerHTML = '';
                  }
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
