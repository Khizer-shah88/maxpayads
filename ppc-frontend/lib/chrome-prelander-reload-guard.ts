/**
 * Stop scripts in custom prelander HTML from starting an automatic download
 * after Chrome reopens the cleaned prelander URL. This is intentionally
 * limited to reload navigations on the prelander document; normal arrivals and
 * redirect-domain hops are untouched.
 * Keep this function self-contained because the clean shell serializes it.
 */
export function installChromePrelanderReloadGuard(): void {
  try {
    const userAgent = navigator.userAgent || '';
    const isChrome = /\bChrome\//.test(userAgent) && !/\b(Edg|OPR|Brave)\//.test(userAgent);
    if (!isChrome) return;

    const navigation = performance.getEntriesByType?.('navigation')?.[0] as PerformanceNavigationTiming | undefined;
    const legacyReload = (performance as Performance & { navigation?: PerformanceNavigation }).navigation?.type === 1;
    if (navigation?.type !== 'reload' && !legacyReload) return;

    const hasUserActivation = () => !!navigator.userActivation?.isActive;

    // A synthetic anchor click is the common way templates start a download on
    // load. Block background clicks even when the anchor has no download
    // attribute: a URL can still return a download response. Preserve clicks
    // made as part of a real user gesture.
    const anchorClick = HTMLAnchorElement.prototype.click;
    HTMLAnchorElement.prototype.click = function guardedAnchorClick(this: HTMLAnchorElement) {
      if (!hasUserActivation()) return;
      return anchorClick.call(this);
    };

    // Ignore background popup attempts, while keeping user-initiated links and
    // the existing redirect flow available after a visitor interacts.
    const open = window.open;
    window.open = function guardedOpen(...args: Parameters<typeof window.open>) {
      if (!hasUserActivation()) return null;
      return open.apply(window, args);
    };

    // Bind to Window so the handlers survive the clean shell's document.open().
    window.addEventListener('click', (event) => {
      if (event.isTrusted || hasUserActivation()) return;
      const target = event.target;
      const anchor = target instanceof Element ? target.closest('a') : null;
      if (anchor) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    }, true);

    window.addEventListener('submit', (event) => {
      if (!hasUserActivation()) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    }, true);
  } catch {
    // A browser API restriction must not interrupt prelander or redirect flow.
  }
}
