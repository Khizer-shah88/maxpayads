import type { Metadata } from 'next'
import Script from 'next/script'

export const metadata: Metadata = {
  title: 'Download Ready',
  description: 'Your file is ready to download.',
}

export default function PrelanderLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      {/* Security: Block pasted URLs IMMEDIATELY before React even loads */}
      <Script id="prelander-security" strategy="beforeInteractive">
        {`
          (function() {
            try {
              var marker = sessionStorage.getItem('prelander_tab_authorized');
              if (marker === 'denied') {
                // Previously denied - clear immediately
                window.location.replace('about:blank');
                return;
              }
              if (marker === 'granted') {
                // Previously authorized - allow
                return;
              }
              // First visit - check referrer
              var ref = document.referrer;
              var host = window.location.hostname;
              var hasExternal = ref && ref.indexOf(host) === -1;
              
              if (hasExternal) {
                // Legitimate flow - grant access
                sessionStorage.setItem('prelander_tab_authorized', 'granted');
              } else {
                // Pasted URL - deny and clear immediately
                sessionStorage.setItem('prelander_tab_authorized', 'denied');
                window.location.replace('about:blank');
              }
            } catch (e) {
              // Storage blocked - deny by default
              window.location.replace('about:blank');
            }
          })();
        `}
      </Script>
      {children}
    </>
  )
}
