/**
 * middleware.ts — Next.js Edge Middleware
 *
 * Responsibilities (in order):
 *  1. Conditional Entry Access Guard  — protects the landing page (/) so that
 *     only visitors who arrive from an allowed referrer (or already hold a valid
 *     session cookie) can see it.  Everyone else is redirected to the configured
 *     fallback URL.
 *  2. Admin route protection          — requires admin_token + admin_user cookies.
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

// ─── Portal hostnames ─────────────────────────────────────────────────────────
// The marketing/admin/publisher portal (root landing page, dashboard, etc.) may
// only be served on these hostnames. Redirection domains (Anchor / Inter /
// Prelander) and any other hostname pointing at this server reach the catch-all
// nginx server block; without this check they would all render the
// VertexMonetize landing page. Anything not listed here gets a 404 for
// portal-only pages while infrastructure routes (/d/[slug], /click, /ad.js,
// APIs) keep working on every domain.
const PORTAL_HOSTNAMES: ReadonlyArray<string> = (
  process.env.PORTAL_HOSTNAMES ??
  'maxpayads.com,www.maxpayads.com,vertexmonetize.com,www.vertexmonetize.com,localhost'
)
  .split(',')
  .map(h => h.trim().toLowerCase())
  .filter(Boolean);

function requestHostname(request: NextRequest): string {
  // X-Forwarded-Host survives the nginx proxy; nextUrl.host falls back for
  // direct dev access. Strip any port before comparing.
  const forwarded = request.headers.get('x-forwarded-host');
  const raw = forwarded?.split(',')[0]?.trim() || request.nextUrl.host || '';
  return raw.split(':')[0].toLowerCase();
}

function isPortalHost(hostname: string): boolean {
  return PORTAL_HOSTNAMES.includes(hostname);
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

export async function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Create response first (will be used throughout)
  let response: NextResponse;

  // ════════════════════════════════════════════════════════════════════════════
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
  // browsing session), capture its Set-Cookie, and redirect to the clean root
  // WITH that cookie attached. The slug never touches the address bar: the
  // handoff token travels in the path of this fetch, server-to-server, and
  // the visitor lands directly on https://prelanderdomain.com/.
  if (pathname.startsWith('/_auth/')) {
    const handoff = pathname.slice('/_auth/'.length);
    try {
      const backendUrl = process.env.NEXT_BACKEND_URL || 'http://localhost:8000';
      const exchangeRes = await fetch(`${backendUrl}/prelander/_auth/${encodeURIComponent(handoff)}`, {
        headers: {
          // Pass the visitor's identity headers so the exchange's browser
          // binding (fingerprint check inside consume_handoff) validates.
          cookie: request.headers.get('cookie') || '',
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
        // redirect to the clean root. The visitor is now fully authorized.
        const setCookies = exchangeRes.headers.getSetCookie?.() ?? [];
        const redirectRes = NextResponse.redirect(new URL('/', request.nextUrl.origin), 302);
        for (const cookie of setCookies) {
          redirectRes.headers.append('set-cookie', cookie);
        }
        console.log(
          `[_AUTH_RECOVERY] exchange completed server-side (${setCookies.length} cookies) — redirecting to clean root`,
        );
        return redirectRes;
      }

      // Exchange rejected (replayed/invalid/expired handoff) → the backend
      // already returned the strict 204 / denied response. Mirror it.
      console.log(`[_AUTH_RECOVERY] exchange rejected (${exchangeRes.status}) — mirroring`);
      const body = await exchangeRes.text();
      return new NextResponse(body || null, { status: exchangeRes.status });
    } catch (err) {
      // Backend unreachable — fail CLOSED: strict 204, no content ever.
      console.log(`[_AUTH_RECOVERY] backend unreachable — strict 204`);
      return new NextResponse(null, { status: 204, headers: { 'Content-Length': '0' } });
    }
  }

  // ════════════════════════════════════════════════════════════════════════════
  // 0.  PORTAL HOSTNAME GATE — redirection domains must never serve the portal
  // ════════════════════════════════════════════════════════════════════════════
  // Any hostname pointing at this server (newly added redirection domains hit
  // the nginx catch-all) must not render the VertexMonetize landing page or
  // the dashboards. Infrastructure routes stay reachable on every domain:
  //   /d/[slug]  — prelander pages
  //   /click, /go, /ad.js, /health, /docs — backend endpoints (served by nginx)
  //   /api/*     — API routes (proxied by nginx to FastAPI or rewritten here)
  //   /_next/*   — static assets
  const host = requestHostname(request);
  const isInfraPath =
    pathname.startsWith('/d/') ||
    pathname.startsWith('/api/') ||
    pathname.startsWith('/_next/') ||
    // One-time prelander authorization bootstrap (exchanges the cross-domain
    // handoff for the prelander-domain session cookie — backend route).
    pathname.startsWith('/_auth/') ||
    // White-label public stats share links work on any configured domain
    // (including the optional dedicated stats share domain)
    pathname.startsWith('/public-stats/') ||
    // Public static assets served from prelander domains (video tutorials etc.)
    /\.(mp4|webm|png|jpg|jpeg|gif|ico|svg|txt|xml|webmanifest)$/i.test(pathname) ||
    pathname === '/favicon.ico';

  if (!isPortalHost(host) && !isInfraPath) {
    // ── CLEAN PRELANDER URL + SERVER-SIDE SOURCE SHIELD (spec §3/§7) ──────
    // The bare prelander root is the FINAL prelander page — but the decision
    // of whether this visitor may see ANY page source is made SERVER-SIDE
    // before a single byte of the application shell is served. view-source:
    // on the domain must never reveal the Next.js HTML, script paths, or
    // build metadata to an unauthorized visitor.
    if (pathname === '/') {
      // Ask the backend to validate the browsing-session cookie. The edge
      // middleware can await fetches — this is a true server-side gate,
      // not a frontend trick.
      try {
        const backendUrl = process.env.NEXT_BACKEND_URL || 'http://localhost:8000';
        const cookieHeader = request.headers.get('cookie') || '';
        const checkRes = await fetch(`${backendUrl}/prelander/session-check`, {
          headers: { cookie: cookieHeader },
          redirect: 'manual',
        });

        if (checkRes.status === 200) {
          const check = await checkRes.json().catch(() => null);
          if (check?.authorized) {
            const url = request.nextUrl.clone();
            url.pathname = '/d/session';
            return NextResponse.rewrite(url);
          }
        }
        // UNAUTHORIZED → mirror the backend's HTTP 204 No Content verbatim.
        // Spec: no HTML body, no redirect, no about:blank, no JS navigation,
        // no error page — the browser's NATIVE 204 handling terminates the
        // request. view-source shows nothing: no app shell, no framework
        // code, no metadata.
        return new NextResponse(null, { status: 204, headers: { 'Content-Length': '0' } });
      } catch (err) {
        // Backend unreachable — fail CLOSED with 204 (never expose the shell).
        console.log(`[PRELANDER_SHIELD] backend unreachable — strict 204, no content served`);
        return new NextResponse(null, { status: 204, headers: { 'Content-Length': '0' } });
      }
    }
    console.log(
      `[PORTAL_HOST_BLOCKED] host=${host} path=${pathname} — ` +
        `serving 404 (portal pages only allowed on: ${PORTAL_HOSTNAMES.join(', ')})`,
    );
    return new NextResponse(null, { status: 404 });
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
  // 2.  EXISTING AUTH MIDDLEWARE (unchanged behaviour)
  // ════════════════════════════════════════════════════════════════════════════

  const PUBLIC_PATHS = ['/', '/admin/auth', '/publisher/auth', '/publisher/pending'];

  // Allow public pages without any further checks
  if (PUBLIC_PATHS.includes(pathname)) {
    // Already-logged-in admin hitting /admin/auth → dashboard
    if (pathname === '/admin/auth') {
      const adminToken = request.cookies.get('admin_token')?.value;
      const adminUserCookie = request.cookies.get('admin_user')?.value;
      if (adminToken && adminUserCookie) {
        return NextResponse.redirect(new URL('/admin/dashboard', request.url));
      }
    }
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

  // ── Protect /admin/* routes ────────────────────────────────────────────────
  if (pathname.startsWith('/admin')) {
    const adminToken = request.cookies.get('admin_token')?.value;
    const adminUserCookie = request.cookies.get('admin_user')?.value;

    if (!adminToken || !adminUserCookie) {
      return NextResponse.redirect(new URL('/admin/auth', request.url));
    }

    try {
      const adminUser = JSON.parse(adminUserCookie);
      if (adminUser?.role !== 'admin') {
        return NextResponse.redirect(new URL('/admin/auth', request.url));
      }
    } catch {
      return NextResponse.redirect(new URL('/admin/auth', request.url));
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

  const cspHeader = isPrelander
    ? `
      default-src 'self';
      script-src 'self' 'unsafe-inline' https:;
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
      script-src 'self' 'unsafe-inline';
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
    '/((?!_next/static|_next/image|favicon.ico|robots.txt|sitemap.xml|api).*)',
  ],
};
