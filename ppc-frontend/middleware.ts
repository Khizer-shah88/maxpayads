/**
 * middleware.ts — Next.js Edge Middleware
 *
 * Responsibilities (in order):
 *  1. Conditional Entry Access Guard  — protects the landing page (/) so that
 *     only visitors who arrive from an allowed referrer (or already hold a valid
 *     session cookie) can see it.  Everyone else is redirected to the configured
 *     fallback URL.
 *  2. Admin route protection          — validates admin_token with the API.
 *  3. Publisher route protection      — requires publisher_token + publisher_user
 *     cookies; enforces account status.
 *
 * Environment variables consumed here (all server-side only):
 *   ALLOWED_ENTRY_DOMAINS   e.g. "https://browsmac.org,https://www.browsmac.org"
 *   ENTRY_FALLBACK_URL      e.g. "https://www.google.com/"
 *   ENTRY_SESSION_TTL       seconds, default 900
 *   ENTRY_SESSION_SECRET    ≥32 random chars, e.g. from `openssl rand -hex 32`
 */

import { NextResponse } from 'next/server';
import { prelanderFallbackResponse, prelanderNoContentResponse, prelanderChromeReloadResponse, sessionUnavailableResponse } from '@/lib/prelander-session';
import type { NextRequest } from 'next/server';
import { evaluateEntryAccess, getAllowedHostnames, getSessionSecret, getSessionTtl, isReferrerAllowed, validateSessionToken } from '@/lib/entry-guard';

// ─── Routes exempt from the entry guard ──────────────────────────────────────
// (auth, pending, and prelander pages must always be reachable so publishers
//  can log in and so prelander slugs work on other domains)
const ENTRY_GUARD_EXEMPT_PATHS: ReadonlyArray<string> = [
  '/publisher/auth',
  '/publisher/pending',
  '/admin/auth',
  '/prelander',
];

// Prefix-based exemptions (all sub-paths also exempt)
const ENTRY_GUARD_EXEMPT_PREFIXES: ReadonlyArray<string> = ['/d/'];

/**
 * Returns true when the request path must be protected by the entry guard.
 * We protect ONLY the root landing page (/) by default.  If you need to
 * protect additional paths, add them to ENTRY_GUARD_PROTECTED_PATHS below.
 */
const ENTRY_GUARD_PROTECTED_PATHS: ReadonlyArray<string> = ['/'];

function requestHostname(request: NextRequest): string {
  // Trust the Host header preserved by nginx and the internal API proxy.
  const raw = request.headers.get('host') || request.nextUrl.host || '';
  return raw.split(':')[0].toLowerCase();
}

function isEntryGuardProtected(pathname: string): boolean {
  // Never guard explicitly exempt paths
  if (ENTRY_GUARD_EXEMPT_PATHS.includes(pathname)) return false;
  for (const prefix of ENTRY_GUARD_EXEMPT_PREFIXES) {
    if (pathname.startsWith(prefix)) return false;
  }
  // Only guard the explicitly protected paths
  return ENTRY_GUARD_PROTECTED_PATHS.includes(pathname);
}

function requestUsesHttps(request: NextRequest): boolean {
  if (request.nextUrl.protocol === 'https:') return true;
  const forwarded = request.headers.get('x-forwarded-proto');
  if (forwarded?.split(',')[0]?.trim().toLowerCase() === 'https') return true;
  const cfVisitor = request.headers.get('cf-visitor');
  if (cfVisitor?.includes('"scheme":"https"')) return true;
  return false;
}

function clientIp(request: NextRequest): string {
  return (
    request.headers.get('cf-connecting-ip') ??
    request.headers.get('x-forwarded-for')?.split(',')[0]?.trim() ??
    'unknown'
  );
}

function referrerHostname(referrer: string | undefined): string {
  if (!referrer) return '(none)';
  try {
    return new URL(referrer).hostname;
  } catch {
    return '(malformed)';
  }
}

function isChromePrelanderReload(request: NextRequest): boolean {
  const userAgent = request.headers.get('user-agent') || '';
  const isChrome = /\bChrome\//.test(userAgent) && !/\b(Edg|OPR|Brave)\//.test(userAgent);
  const isDocumentNavigation =
    request.headers.get('sec-fetch-mode') === 'navigate' &&
    request.headers.get('sec-fetch-dest') === 'document';
  // Chrome marks a toolbar reload as `none` (browser-initiated) in current
  // versions, while some versions report `same-origin`.
  const fetchSite = request.headers.get('sec-fetch-site');
  const isReloadNavigation = fetchSite === 'same-origin' || fetchSite === 'none';
  const wasUserInitiated = request.headers.get('sec-fetch-user') === '?1';
  const cacheControl = request.headers.get('cache-control') || '';
  const isReload = /(?:max-age\s*=\s*0|no-cache)/i.test(cacheControl);

  return isChrome && isDocumentNavigation && isReloadNavigation && wasUserInitiated && isReload;
}

function viewSourceRedirectTarget(request: NextRequest): URL | null {
  const candidates = [
    request.nextUrl.href,
    request.url,
    request.nextUrl.pathname,
    request.headers.get('referer') || '',
  ].filter((value): value is string => !!value);

  for (const candidate of candidates) {
    const normalized = candidate.replace(/^view-source:(?:\/\/)?/i, '');
    if (!/^https?:\/\//i.test(normalized)) continue;
    try {
      return new URL(normalized);
    } catch {
      continue;
    }
  }

  return null;
}

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const host = requestHostname(request);

  // Public exit for denied prelander visits. Read runtime configuration here
  // so the clean shell, React page and cookie-less response use one fallback.
  // No database/session dependency or source-deterrent worker is needed.
  if (pathname === '/prelander-fallback') {
    const response = NextResponse.redirect('https://www.google.com/', 302);
    response.headers.set('Cache-Control', 'no-store, private');
    response.headers.set('Referrer-Policy', 'no-referrer');
    return response;
  }

  // Both containers receive the same explicit PORTAL_HOSTNAMES setting.
  // Portal host assignments are configuration, not mutable database roles.
  // Ordinary portal pages/assets can avoid a network probe on every request;
  // traffic/stats URLs still use the complete API policy even on a portal host.
  const configuredPortals = (process.env.PORTAL_HOSTNAMES || '').split(',').map(value => value.trim().toLowerCase());
  const configuredPortalPage = configuredPortals.includes(host) && (
    pathname === '/admin' || pathname.startsWith('/admin/') ||
    pathname === '/publisher' || pathname.startsWith('/publisher/') || pathname.startsWith('/_next/')
  );

  // The API owns dynamic domain roles. DNS pointing here does not grant access.
  let role: string;
  if (configuredPortalPage) {
    role = 'portal';
  } else {
    try {
      const backendUrl = process.env.NEXT_BACKEND_URL || 'http://localhost:8000';
      const check = await fetch(`${backendUrl}/domain-access?path=${encodeURIComponent(pathname)}`, {
        headers: { host: request.headers.get('host') || host },
        cache: 'no-store',
        redirect: 'manual',
      });
      if (!check.ok) return new NextResponse(null, { status: check.status >= 500 ? 503 : 404 });
      role = (await check.json()).role;
    } catch {
      return new NextResponse(null, { status: 503 });
    }
  }

  if (role === 'prelander' && request.nextUrl.protocol === 'view-source:') {
    const target = viewSourceRedirectTarget(request);
    if (target) {
      const response = NextResponse.redirect(target, 301);
      response.headers.set('Cache-Control', 'no-store, private');
      response.headers.set('Referrer-Policy', 'no-referrer');
      return response;
    }
  }
  // A smartlink typed/bookmarked on the Anchor retains Sec-Fetch-Site: none
  // through its HTTP redirect to Inter. That header cannot distinguish this
  // valid arrival from a pasted URL. Let the opaque Inter ticket reach its
  // POST exchange, which checks host, browser, expiry and single-use status.
  const isInterTicket = role === 'inter' && pathname.startsWith('/d/h_');
  // An HTTP handoff can also retain Sec-Fetch-Site: none. The session entry
  // uses the server session gate and one-time arrival claim below instead.
  const isPrelanderEntry = role === 'prelander' && (pathname === '/d/session' || pathname === '/clean-shell');
  if (pathname.startsWith('/d/') && !isInterTicket && !isPrelanderEntry && request.headers.get('sec-fetch-site') === 'none') {
    return prelanderFallbackResponse();
  }
  if (role === 'anchor' && pathname === '/') {
    if (!request.nextUrl.search) return new NextResponse(null, { status: 404 });
    const click = request.nextUrl.clone();
    click.pathname = '/click';
    return NextResponse.redirect(click, 302);
  }

  // ════════════════════════════════════════════════════════════════════════════
  // Authorization uses server-side sessions for all browser navigations.

  // 0a. /_auth/* RECOVERY — the exchange must complete or the flow dead-ends
  // ════════════════════════════════════════════════════════════════════════════
  // /_auth/{handoff} is a FastAPI route (nginx rewrites it to
  // /prelander/_auth/…). If the request arrives HERE, the domain's nginx block
  // is missing the /_auth/ location. The OLD recovery (redirect to /) caused a
  // deadlock: the clean root requires the mpa_pls session cookie, the cookie
  // is minted BY the exchange — which never ran → session-check returned 204
  // → the browser stayed on the Inter "Redirecting…" loader forever.
  //
  // FIX: perform the exchange SERVER-SIDE right here — fetch the backend's
  // /prelander/_auth/{handoff} (consuming the one-time handoff, minting the
  // browsing session), capture its Set-Cookie, and redirect to /d/session
  // WITH that cookie attached. The slug never touches the address bar: the
  // handoff token travels in the path of this fetch, server-to-server, and
  // the rendered entry later cleans the address bar to the domain root.
  if (pathname.startsWith('/_auth/')) {
    const handoff = pathname.slice('/_auth/'.length);
    try {
      const backendUrl = process.env.NEXT_BACKEND_URL || 'http://localhost:8000';
      const exchangeRes = await fetch(`${backendUrl}/prelander/_auth/${encodeURIComponent(handoff)}`, {
        headers: {
          // Pass the visitor's identity headers so the exchange's browser
          // binding (fingerprint check inside consume_handoff) validates.
          cookie: request.headers.get('cookie') || '',
          'x-real-ip': request.headers.get('x-real-ip') || '',
          'user-agent': request.headers.get('user-agent') || '',
          'x-forwarded-for': request.headers.get('x-forwarded-for') || '',
          // The exchange validates the requesting host (handoff target
          // binding) — forward the host the visitor actually used.
          host: request.headers.get('host') || '',
        },
        redirect: 'manual',
      });

      if (exchangeRes.status === 302) {
        // Exchange succeeded: capture the mpa_pls (and tab-bootstrap)
        // Set-Cookie headers from the backend and replay them on our own
        // redirect to /d/session (clean URL flow). The prelander entry
        // will rewrite to /clean-shell and JavaScript will clean URL to /.
        const setCookies = exchangeRes.headers.getSetCookie?.() ?? [];
        const redirectRes = NextResponse.redirect(new URL('/d/session', request.nextUrl.origin), 302);
        redirectRes.headers.set('Cache-Control', 'no-store, private');
        redirectRes.headers.set('Referrer-Policy', 'no-referrer');
        for (const cookie of setCookies) {
          redirectRes.headers.append('set-cookie', cookie);
        }
        console.log(
          `[_AUTH_RECOVERY] exchange completed server-side (${setCookies.length} cookies) — redirecting to /d/session`,
        );
        return redirectRes;
      }

      return sessionUnavailableResponse(exchangeRes.status >= 500 ? 503 : 403);
    } catch (err) {
      return sessionUnavailableResponse(503);
    }
  }

  // ════════════════════════════════════════════════════════════════════════════
  // 0.  PORTAL HOSTNAME GATE — redirection domains must never serve the portal
  // ════════════════════════════════════════════════════════════════════════════
  // Only the registered Prelander role uses the clean-root/arrival policy.
  if (role === 'prelander' && pathname === '/') {
    // Chrome can replay download actions from arbitrary admin-authored HTML
    // when the visible clean URL is refreshed. Commit a script-free page for
    // same-origin Chrome reloads; other browsers and view-source keep the
    // existing no-content behavior. Never authorize this root using the cookie.
    if (isChromePrelanderReload(request)) return prelanderChromeReloadResponse();
    return prelanderNoContentResponse();
  }

  if (isPrelanderEntry) {
      // Only the handoff's session entry can render the prelander shell.
      if (!request.cookies.get('mpa_pls')?.value) {
        return prelanderFallbackResponse();
      }
      // Ask the backend to validate the browsing-session cookie. The edge
      // middleware can await fetches — this is a true server-side gate,
      // not a frontend trick.
      try {
        const backendUrl = process.env.NEXT_BACKEND_URL || 'http://localhost:8000';
        const cookieHeader = request.headers.get('cookie') || '';
        const checkRes = await fetch(`${backendUrl}/prelander/session-check`, {
          headers: { cookie: cookieHeader, host: request.headers.get('host') || host, 'x-real-ip': request.headers.get('x-real-ip') || '' },
          redirect: 'manual',
          cache: 'no-store',
        });

        if (checkRes.status === 200) {
          const check = await checkRes.json().catch(() => null);
          if (check?.authorized) {
            // Content is fetched by the page with a second session check.
            const url = request.nextUrl.clone();
            url.pathname = '/clean-shell';
            // The rewrite can re-enter middleware at its destination. Do not
            // rewrite /clean-shell to itself or Next can loop indefinitely.
            const page = pathname === '/clean-shell' ? NextResponse.next() : NextResponse.rewrite(url);
            addSecurityHeaders(page, '/d/shell');
            // This flow uses HTTP 204 at the clean root. A legacy worker must
            // not replay the arrival document based on missing heartbeats.
            page.headers.delete('x-sd');
            page.headers.set('Cache-Control', 'no-store, private');
            return page;
          }
        }
        return checkRes.status >= 500 ? sessionUnavailableResponse(503) : prelanderFallbackResponse();
      } catch (err) {
        return sessionUnavailableResponse(503);
      }
  }

  // Inter domains never serve the portal shell at their root. A direct paste
  // or fresh tab should still go through the same fallback path as a denied
  // prelander visit: previous page when available, otherwise Google.
  if (role === 'inter' && pathname === '/') {
    return prelanderFallbackResponse();
  }

  // ════════════════════════════════════════════════════════════════════════════
  // 1.  ENTRY GUARD — only active when ENTRY_SESSION_SECRET is configured
  // ════════════════════════════════════════════════════════════════════════════
  if (isEntryGuardProtected(pathname) && process.env.ENTRY_SESSION_SECRET) {
    const sessionCookie = request.cookies.get('entry_session')?.value;
    const referrer = request.headers.get('referer') ?? undefined;
    const secret = getSessionSecret();
    const ttl = getSessionTtl();
    const ip = clientIp(request);

    if (sessionCookie) {
      const sessionState = await validateSessionToken(sessionCookie, secret, ttl);
      if (sessionState === 'expired') {
        console.log(
          `[ENTRY_SESSION_EXPIRED] path=${pathname} ip=${ip}`,
        );
      }
    }

    const decision = await evaluateEntryAccess({
      sessionCookie,
      referrer,
      secureCookie: requestUsesHttps(request),
    });

    if (decision.result === 'DENY') {
      if (referrer && !isReferrerAllowed(referrer, getAllowedHostnames())) {
        console.log(
          `[ENTRY_INVALID_REFERRER] path=${pathname} referrer=${referrerHostname(referrer)} ip=${ip}`,
        );
      }

      console.log(
        `[ENTRY_ACCESS_DENIED] path=${pathname} ` +
          `referrer=${referrerHostname(referrer)} ` +
          `session=${sessionCookie ? 'present_but_invalid' : 'absent'} ` +
          `ip=${ip}`,
      );

      // Redirect — make sure we never redirect to ourselves (loop guard)
      const fallbackUrl = decision.fallbackUrl;
      const requestHost = request.nextUrl.hostname.toLowerCase();
      try {
        const fallbackHost = new URL(fallbackUrl).hostname.toLowerCase();
        if (fallbackHost === requestHost) {
          // Misconfigured fallback points at ourselves — serve 403 instead
          return new NextResponse('Forbidden', { status: 403 });
        }
      } catch {
        return new NextResponse('Forbidden', { status: 403 });
      }

      return NextResponse.redirect(fallbackUrl, { status: 302 });
    }

    if (decision.result === 'ALLOW_VALID_REFERRER') {
      console.log(
        `[ENTRY_SESSION_CREATED] path=${pathname} referrer=${referrerHostname(referrer)} ip=${ip}`,
      );

      const response = NextResponse.next();
      // Set the HttpOnly session cookie on the response
      response.headers.set('Set-Cookie', decision.setCookie);
      return addSecurityHeaders(response, pathname);
    }

    // ALLOW_SESSION_EXISTS
    console.log(
      `[ENTRY_ACCESS_GRANTED] path=${pathname} reason=valid_session ip=${ip}`,
    );
    // Fall through — let existing auth middleware logic run below
  }

  // ════════════════════════════════════════════════════════════════════════════
  // 2.  PORTAL AUTHENTICATION
  // ════════════════════════════════════════════════════════════════════════════

  if (pathname === '/admin' || pathname.startsWith('/admin/')) {
    const isLogin = ['/admin/auth', '/admin/login', '/admin/a7b9c2d4e8f1g3h5'].includes(pathname);
    const adminToken = request.cookies.get('admin_token')?.value;
    let authenticated = false;

    // Cookie metadata is only for display. Use the backend's current user
    // and role for both login-page redirects and protected-page access.
    if (adminToken) {
      try {
        const backendUrl = process.env.NEXT_BACKEND_URL || 'http://localhost:8000';
        const session = await fetch(`${backendUrl}/auth/me`, {
          headers: {
            host: request.headers.get('host') || host,
            authorization: `Bearer ${adminToken}`,
            'x-real-ip': request.headers.get('x-real-ip') || '',
          },
          cache: 'no-store',
          redirect: 'manual',
        });
        if (session.ok) {
          const data = await session.json();
          authenticated = data.user?.role === 'admin';
        } else if (session.status !== 401 && session.status !== 403) {
          throw new Error('Session service unavailable');
        }
      } catch {
        // Preserve the session during outages instead of turning a temporary
        // backend failure into a logout or a redirect loop.
        return new NextResponse('Unable to verify your session. Please reload to try again.', {
          status: 503, headers: { 'Cache-Control': 'no-store', 'Retry-After': '5' },
        });
      }
    }

    const response = authenticated
      ? (isLogin ? NextResponse.redirect(new URL('/admin/dashboard', request.url)) : NextResponse.next())
      : (isLogin ? NextResponse.next() : NextResponse.redirect(new URL('/admin/auth', request.url)));
    if (!authenticated) {
      for (const name of ['admin_token', 'admin_refresh_token', 'admin_user']) {
        response.cookies.delete(name);
      }
    }
    response.headers.set('Cache-Control', 'no-store, private');
    return response.headers.has('location') ? response : addSecurityHeaders(response, pathname);
  }

  const PUBLIC_PATHS = ['/', '/publisher/auth', '/publisher/pending'];

  // Allow public pages without any further checks
  if (PUBLIC_PATHS.includes(pathname)) {
    // Already-logged-in publisher hitting /publisher/auth → appropriate page
    if (pathname === '/publisher/auth') {
      const publisherToken = request.cookies.get('publisher_token')?.value;
      const publisherUserCookie = request.cookies.get('publisher_user')?.value;
      if (publisherToken && publisherUserCookie) {
        try {
          const pu = JSON.parse(publisherUserCookie);
          if (pu?.status === 'active') {
            return NextResponse.redirect(new URL('/publisher/dashboard', request.url));
          } else {
            return NextResponse.redirect(new URL('/publisher/pending', request.url));
          }
        } catch {
          return NextResponse.redirect(new URL('/publisher/dashboard', request.url));
        }
      }
    }
    // Logged-in active publisher on /publisher/pending → dashboard
    if (pathname === '/publisher/pending') {
      const publisherToken = request.cookies.get('publisher_token')?.value;
      const publisherUserCookie = request.cookies.get('publisher_user')?.value;
      if (publisherToken && publisherUserCookie) {
        try {
          const pu = JSON.parse(publisherUserCookie);
          if (pu?.status === 'active') {
            return NextResponse.redirect(new URL('/publisher/dashboard', request.url));
          }
        } catch {}
      } else {
        return NextResponse.redirect(new URL('/publisher/auth', request.url));
      }
    }
    return addSecurityHeaders(NextResponse.next(), pathname);
  }

  // ── Protect /publisher/* routes ────────────────────────────────────────────
  if (pathname.startsWith('/publisher')) {
    const publisherToken = request.cookies.get('publisher_token')?.value;
    const publisherUserCookie = request.cookies.get('publisher_user')?.value;

    if (!publisherToken || !publisherUserCookie) {
      return NextResponse.redirect(new URL('/publisher/auth', request.url));
    }

    try {
      const publisherUser = JSON.parse(publisherUserCookie);
      if (publisherUser?.role === 'admin') {
        return NextResponse.redirect(new URL('/admin/auth', request.url));
      }
      if (publisherUser?.status && publisherUser.status !== 'active') {
        return NextResponse.redirect(new URL('/publisher/pending', request.url));
      }
    } catch {
      return NextResponse.redirect(new URL('/publisher/auth', request.url));
    }

    return addSecurityHeaders(NextResponse.next(), pathname);
  }

  return addSecurityHeaders(NextResponse.next(), pathname);
}

// Helper to add security headers to any response
//
// STEP 13 — two policies, built on what the pages actually load:
//  - PORTAL pages (admin/publisher/marketing): strict CSP (self + Google
//    Fonts only). Nothing on the portal needs external scripts.
//  - PRELANDER pages (/d/[slug]): the page document.writes admin-authored
//    full-HTML templates, which legitimately embed external ad scripts,
//    styles, images and videos (video_url template feature). Their CSP keeps
//    object-src 'none' + frame-ancestors 'none' (nothing may frame us) but
//    allows https: resources so required lander functionality never breaks.
function addSecurityHeaders(response: NextResponse, pathname?: string): NextResponse {
  const isPrelander = !!pathname && pathname.startsWith('/d/');

  // Next's dev-mode Fast Refresh runtime (react-refresh) evaluates strings, so
  // `next dev` genuinely requires 'unsafe-eval' — without it the HMR runtime
  // throws EvalError on every portal page and Fast Refresh silently dies.
  // Added in development ONLY: 'unsafe-eval' is a real XSS amplifier and a
  // production bundle has no need for it. NODE_ENV is set by next dev/next
  // build themselves, so this cannot be flipped on by a stray env var.
  const devEval = process.env.NODE_ENV === 'development' ? " 'unsafe-eval'" : '';

  const cspHeader = isPrelander
    ? `
      default-src 'self';
      script-src 'self' 'unsafe-inline'${devEval} https:;
      style-src 'self' 'unsafe-inline' https:;
      img-src 'self' data: blob: https:;
      font-src 'self' data: https:;
      connect-src 'self' https:;
      frame-src 'self' https:;
      media-src 'self' https:;
      object-src 'none';
      base-uri 'self';
      form-action 'self';
      frame-ancestors 'none';
    `.replace(/\s{2,}/g, ' ').trim()
    : `
      default-src 'self';
      script-src 'self' 'unsafe-inline'${devEval};
      style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;
      img-src 'self' data: blob: https:;
      font-src 'self' data: https://fonts.gstatic.com;
      connect-src 'self' https:;
      frame-src 'self';
      base-uri 'self';
      form-action 'self';
      frame-ancestors 'none';
    `.replace(/\s{2,}/g, ' ').trim();

  response.headers.set('Content-Security-Policy', cspHeader);

  // Only prelander pages carry the source-deterrent marker. Redirect domains
  // and portal pages must not be treated as prelander content.
  if (process.env.ENABLE_SOURCE_DETERRENT === 'true' && pathname?.startsWith('/d/') && !pathname.startsWith('/d/h_')) {
    response.headers.set('x-sd', '1');
  }

  // Anti-framing + hardening on every middleware-served response (STEP 13).
  // X-Frame-Options covers legacy browsers; frame-ancestors 'none' above is
  // the modern guarantee.
  response.headers.set('X-Frame-Options', 'DENY');
  response.headers.set('X-Content-Type-Options', 'nosniff');
  // Explicit (spec): never leak the anchor/inter/prelander chain referrer.
  response.headers.set('Referrer-Policy', 'strict-origin-when-cross-origin');
  response.headers.set('Permissions-Policy', 'geolocation=(), microphone=(), camera=(), payment=(), usb=()');

  return response;
}

export const config = {
  matcher: [
    /*
     * Run middleware on all routes except static assets, API proxy, and SEO files.
     * Entry guard only protects `/` — other matched paths use auth middleware only.
     */
    '/:path*',
  ],
};
