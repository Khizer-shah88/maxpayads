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

  // If the browser has a real previous page, try to go back to it. When there
  // is no usable history entry, fall back to Google instead of the site root.
  if (window.history.length > 1) {
    const currentUrl = window.location.href;
    window.history.back();
    window.setTimeout(() => {
      if (window.location.href === currentUrl) {
        window.location.replace('https://www.google.com/');
      }
    }, 250);
    return;
  }

  window.location.replace('https://www.google.com/');
}
