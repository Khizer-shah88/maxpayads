// tab-guard.ts — put in your Next.js prelander app (e.g. lib/tab-guard.ts).
//
// Shows the prelander only in the tab that ARRIVED through the redirect flow.
// A URL pasted into a new tab has no sessionStorage marker and the server-side
// one-time "arrival" flag is already used, so it is sent back using browser
// history or closes the tab - NOT redirected to Google.

const CLAIM_URL = "/api/prelander/claim";
const TAB_KEY = "pl_tab_ok";                    // per-tab (sessionStorage)

// Module-level promise: React strict mode / double effects must NOT claim twice
// (the second claim would fail and wrongly redirect a real visitor).
let pending: Promise<boolean> | null = null;

/**
 * Gets the best URL to redirect to when blocking access.
 * Returns the referrer URL if valid, otherwise null (will use history.back)
 */
function getBlockRedirectUrl(): string | null {
  // If there's a referrer and it's not from our own domain, use it
  if (document.referrer && document.referrer !== window.location.href) {
    try {
      const referrerUrl = new URL(document.referrer);
      const currentUrl = new URL(window.location.href);
      
      // Don't redirect to the same domain (avoid loops)
      if (referrerUrl.hostname !== currentUrl.hostname) {
        return document.referrer;
      }
    } catch {
      // Invalid referrer URL, continue to next option
    }
  }
  
  // No valid referrer - caller should use browser history
  return null;
}

/**
 * Redirects user away from the prelander page.
 * Uses history.back() to return to previous page in browser history.
 */
function blockAccess(): void {
  const redirectUrl = getBlockRedirectUrl();
  
  if (redirectUrl) {
    // We have a valid referrer URL - redirect there
    console.log('[TAB-GUARD] Redirecting to referrer:', redirectUrl);
    window.location.replace(redirectUrl);
  } else {
    // No referrer (pasted in new tab) - use browser back
    console.log('[TAB-GUARD] No referrer - using browser history back');
    
    // Use history.back() to go to the previous page in browser
    if (window.history.length > 1) {
      window.history.back();
      
      // Backup: if history.back() doesn't navigate away within 1 second,
      // close the tab or go to blank page
      setTimeout(() => {
        // Try to close the tab
        window.close();
        
        // If window.close() doesn't work (requires user gesture in most browsers),
        // redirect to about:blank as last resort
        setTimeout(() => {
          if (!document.hidden) {
            window.location.replace('about:blank');
          }
        }, 200);
      }, 1000);
    } else {
      // No browser history available - close tab or blank page
      window.close();
      setTimeout(() => {
        window.location.replace('about:blank');
      }, 200);
    }
  }
}

export function guardTab(): Promise<boolean> {
  if (pending) return pending;
  
  pending = (async () => {
    try {
      // Reload in the same tab: marker already there → allowed.
      if (sessionStorage.getItem(TAB_KEY)) return true;
      
      // First load after the redirect flow: consume the one-time flag.
      const r = await fetch(CLAIM_URL, { credentials: "include", cache: "no-store" });
      if (r.ok) {
        sessionStorage.setItem(TAB_KEY, "1");
        return true;
      }
    } catch {
      /* network / storage error → treat as not allowed */
    }
    
    // Pasted into a new tab (or flag expired / reused) → block access
    blockAccess();
    return false;
  })();
  
  return pending;
}

/* ── How to use it on your prelander page ─────────────────────────────────────
 *
 * useEffect(() => {
 *   (async () => {
 *     // 1) your existing call (slug route or "session"), unchanged
 *     const res = await fetch(`/api/prelander/resolve/${slugOrSession}`, {
 *       credentials: "include",
 *       headers: { "X-Prelander-Host": window.location.hostname },
 *     });
 *     const data = await res.json();
 *
 *     // 2) NEW: claim AFTER resolve (so the cookie-mint fallback path, which
 *     //    sets the arrival flag inside resolve, also works), BEFORE rendering
 *     if (!(await guardTab())) return;      // blocked access, render nothing
 *
 *     // 3) now it is safe to show the content
 *     setData(data);
 *   })();
 * }, []);
 *
 * Keep the page blank (or a neutral loader) until step 3 so a pasted URL never
 * flashes any prelander content before the redirect/close.
 */
