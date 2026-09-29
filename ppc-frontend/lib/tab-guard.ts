import { returnToPreviousPage } from '@/lib/prelander-navigation';

/** Shared by the React prelander and the inline clean shell. */
export function createTabGuard(onBlocked: () => void) {
  // Keep this function self-contained: the clean shell inlines its JS body.
  let pending: Promise<'allowed' | 'redirected'> | null = null;

  return function guardTab(): Promise<'allowed' | 'redirected'> {
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
        // A store/proxy outage is not an authorization denial. Navigating
        // back here can reopen a consumed Inter ticket (or its bare 404 root).
        if (response.status !== 401 && response.status !== 403) {
          throw new Error('Prelander temporarily unavailable');
        }
      } catch (error) {
        pending = null;
        throw error;
      }

      // Missing cookies (including incognito), expired sessions and reused
      // arrivals all navigate away without rendering any prelander UI.
      onBlocked();
      return 'redirected' as const;
    })();
    return pending;
  };
}

// Deduplicate React strict-mode effects so a legitimate arrival claims once.
export const guardTab = createTabGuard(returnToPreviousPage);
