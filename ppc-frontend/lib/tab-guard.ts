/** Shared by the React prelander and the inline clean shell. */
export function createTabGuard() {
  // Keep this function self-contained: the clean shell inlines its JS body.
  let pending: Promise<'allowed' | 'redirected' | 'denied'> | null = null;

  return function guardTab(): Promise<'allowed' | 'redirected' | 'denied'> {
    if (pending) return pending;
    pending = (async () => {
      try {
        // Storage may be unavailable in private browsing. Still try the
        // server's one-time arrival claim; storage is not authorization.
        try {
          if (sessionStorage.getItem('pl_tab_ok')) return 'allowed' as const;
        } catch {}

        const response = await fetch('/api/prelander/claim', {
          credentials: 'include', cache: 'no-store',
        });
        if (response.ok) {
          try { sessionStorage.setItem('pl_tab_ok', '1'); } catch {}
          return 'allowed' as const;
        }

        // Only a valid session with a consumed arrival may go back. Missing,
        // expired and unavailable sessions show the same message in all modes.
        const result = await response.json().catch(() => null);
        if (response.status !== 403 || result?.reason !== 'arrival_unavailable') {
          return 'denied' as const;
        }

        if (document.referrer) {
          try {
            const previous = new URL(document.referrer);
            if ((previous.protocol === 'https:' || previous.protocol === 'http:') &&
                previous.hostname !== window.location.hostname) {
              window.location.replace(previous.href);
              return 'redirected' as const;
            }
          } catch {}
        }
        if (window.history.length > 1) {
          window.history.back();
          return 'redirected' as const;
        }
      } catch {}

      // A fresh tab has no previous page to return to. Never close it or
      // replace the expiry message with about:blank after a timer.
      return 'denied' as const;
    })();
    return pending;
  };
}

// Deduplicate React strict-mode effects so a legitimate arrival claims once.
export const guardTab = createTabGuard();
