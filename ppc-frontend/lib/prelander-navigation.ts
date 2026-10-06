/** Shared by the page, tab guard and server-denied prelander response. */
export function returnToPreviousPage(): void {
  // Self-contained so the server can inline this before any app UI loads.
  try {
    if (document.referrer) {
      const previous = new URL(document.referrer);
      if ((previous.protocol === 'https:' || previous.protocol === 'http:') &&
          !previous.username && !previous.password &&
          previous.hostname !== window.location.hostname &&
          !previous.pathname.startsWith('/d/') &&
          !previous.pathname.startsWith('/_auth/') &&
          previous.pathname !== '/prelander-fallback') {
        window.location.replace(previous.href);
        return;
      }
    }
  } catch {}

  // No usable referrer: hand off to the server-side fallback route.
  window.location.replace('/prelander-fallback');
}
