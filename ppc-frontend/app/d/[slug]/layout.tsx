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
        <style>{`
          body { margin: 0; padding: 20px; font-family: Arial, sans-serif; }
          .loading { text-align: center; margin-top: 50px; }
        `}</style>
      </head>
      <body>
        <div className="loading">
          <div>Loading...</div>
        </div>
        <div style={{ display: 'none' }}>
          {children}
        </div>
        
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (function() {
                // Immediately check for authorization and show content
                try {
                  var marker = sessionStorage.getItem('prelander_tab_authorized');
                  var referrer = document.referrer;
                  var historyLength = window.history.length;
                  
                  // If this is a view-source request, keep minimal content
                  if (navigator.userAgent && navigator.userAgent.toLowerCase().includes('view-source')) {
                    document.body.innerHTML = '<div style="text-align:center;margin-top:50px;"><div>Loading...</div></div>';
                    return;
                  }
                  
                  // Check authorization
                  var isAuthorized = false;
                  
                  if (marker === 'granted') {
                    isAuthorized = true;
                  } else if (marker === 'denied') {
                    if (window.history.length > 1) {
                      window.history.back();
                    } else {
                      window.location.replace('https://www.google.com');
                    }
                    return;
                  } else {
                    // First visit - check referrer
                    if (!referrer && historyLength === 1) {
                      // Pasted URL - deny
                      sessionStorage.setItem('prelander_tab_authorized', 'denied');
                      window.location.replace('https://www.google.com');
                      return;
                    } else {
                      // Has referrer or history - likely legitimate
                      isAuthorized = true;
                    }
                  }
                  
                  if (isAuthorized) {
                    // Show the actual content
                    var contentDiv = document.querySelector('div[style*="display: none"]');
                    if (contentDiv) {
                      contentDiv.style.display = 'block';
                      document.querySelector('.loading').style.display = 'none';
                    }
                  }
                } catch (e) {
                  // If anything fails, show minimal content
                  document.body.innerHTML = '<div style="text-align:center;margin-top:50px;"><div>Loading...</div></div>';
                }
              })();
            `,
          }}
        />
      </body>
    </html>
  )
}
