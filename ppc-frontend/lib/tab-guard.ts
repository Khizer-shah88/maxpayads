// tab-guard.ts — put in your Next.js prelander app (e.g. lib/tab-guard.ts).
//
// Shows the prelander only in the tab that ARRIVED through the redirect flow.
// A URL pasted into a new tab has no sessionStorage marker and the server-side
// one-time "arrival" flag is already used, so it is sent to BLOCK_URL and no
// content is rendered.

const CLAIM_URL = "/api/prelander/claim";
const TAB_KEY = "pl_tab_ok";                    // per-tab (sessionStorage)
const BLOCK_URL = "https://www.google.com";     // any domain you like

// Module-level promise: React strict mode / double effects must NOT claim twice
// (the second claim would fail and wrongly redirect a real visitor).
let pending: Promise<boolean> | null = null;

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
    
    // Pasted into a new tab (or flag expired / reused) → leave, show nothing.
    window.location.replace(BLOCK_URL);
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
 *     if (!(await guardTab())) return;      // redirected to google, render nothing
 *
 *     // 3) now it is safe to show the content
 *     setData(data);
 *   })();
 * }, []);
 *
 * Keep the page blank (or a neutral loader) until step 3 so a pasted URL never
 * flashes any prelander content before the redirect.
 */