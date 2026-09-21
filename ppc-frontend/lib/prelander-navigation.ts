/** Shared by the page, tab guard and server-denied prelander response. */
export function returnToPreviousPage(): void {
  // Self-contained so the server can inline this before any app UI loads.
  try {
    if (document.referrer) {
      const previous = new URL(document.referrer);
      if ((previous.protocol === 'https:' || previous.protocol === 'http:') &&
          previous.hostname !== window.location.hostname) {
        window.location.replace(previous.href);
        return;
      }
    }
  } catch {}

  // Address-bar pastes normally have no referrer, but the current tab may
  // still have a previous page (including its browser new-tab page).
  if (window.history.length > 1) {
    window.history.back();
    return;
  }

  // No previous entry exists in a fresh tab/window. Normal and private
  // browsing use the same immediate fallback without closing the tab.
  window.location.replace('about:blank');
}
