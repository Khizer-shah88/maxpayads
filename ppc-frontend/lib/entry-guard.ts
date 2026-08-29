/**
 * entry-guard.ts
 *
 * Server-side conditional entry access system.
 * All logic runs exclusively in Next.js middleware (Node.js Edge runtime subset).
 *
 * Flow:
 *  1. Request arrives
 *  2. Check for valid entry_session cookie (HMAC-signed, TTL-checked)
 *  3a. Valid  → serve app normally
 *  3b. Invalid/missing → check referrer against ALLOWED_ENTRY_DOMAINS allowlist
 *      3b-i.  Allowed referrer → create session cookie → serve app
 *      3b-ii. Not allowed    → 302 redirect to ENTRY_FALLBACK_URL
 *
 * Environment variables (all read server-side only, never in client JS):
 *   ALLOWED_ENTRY_DOMAINS  comma-separated list of allowed origin URLs
 *                          e.g. "https://example.com,https://www.example.com"
 *   ENTRY_FALLBACK_URL     where to send unauthorised visitors
 *                          e.g. "https://www.google.com/"
 *   ENTRY_SESSION_TTL      session lifetime in seconds (default 900 = 15 min)
 *   ENTRY_SESSION_SECRET   ≥32-char random string used for HMAC-SHA256 signing
 */

// ─── Types ────────────────────────────────────────────────────────────────────

export type EntryDecision =
  | { result: 'ALLOW_SESSION_EXISTS' }
  | { result: 'ALLOW_VALID_REFERRER'; setCookie: string }
  | { result: 'DENY'; fallbackUrl: string };

// ─── Config helpers ───────────────────────────────────────────────────────────

/**
 * Parse ALLOWED_ENTRY_DOMAINS into a deduplicated Set of lowercase hostnames.
 * Validates each entry is a real HTTPS/HTTP URL with a proper hostname so that
 * lookalike attacks (https://trusted.com.evil.com) are rejected.
 */
export function getAllowedHostnames(): Set<string> {
  const raw = process.env.ALLOWED_ENTRY_DOMAINS ?? '';
  const hostnames = new Set<string>();

  for (const entry of raw.split(',')) {
    const trimmed = entry.trim();
    if (!trimmed) continue;
    try {
      const url = new URL(trimmed);
      // Only accept https:// (or http:// for local dev convenience)
      if (url.protocol !== 'https:' && url.protocol !== 'http:') continue;
      // hostname must be non-empty and not an IP in the final range
      if (!url.hostname) continue;
      hostnames.add(url.hostname.toLowerCase());
    } catch {
      // Malformed entry — skip silently
    }
  }

  return hostnames;
}

export function getFallbackUrl(): string {
  const raw = (process.env.ENTRY_FALLBACK_URL ?? '').trim();
  if (!raw) return 'https://www.google.com/';
  try {
    new URL(raw); // validate
    return raw;
  } catch {
    return 'https://www.google.com/';
  }
}

export function getSessionTtl(): number {
  const raw = parseInt(process.env.ENTRY_SESSION_TTL ?? '900', 10);
  return Number.isFinite(raw) && raw > 0 ? raw : 900;
}

export function getSessionSecret(): string {
  return process.env.ENTRY_SESSION_SECRET ?? '';
}

// ─── HMAC helpers (Web Crypto API — available in Edge runtime) ────────────────

async function importKey(secret: string): Promise<CryptoKey> {
  const enc = new TextEncoder();
  return crypto.subtle.importKey(
    'raw',
    enc.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign', 'verify'],
  );
}

async function signPayload(payload: string, secret: string): Promise<string> {
  const key = await importKey(secret);
  const enc = new TextEncoder();
  const sig = await crypto.subtle.sign('HMAC', key, enc.encode(payload));
  // base64url-encode the signature (no padding, URL-safe chars)
  return btoa(String.fromCharCode(...new Uint8Array(sig)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

async function verifySignature(
  payload: string,
  signature: string,
  secret: string,
): Promise<boolean> {
  try {
    const key = await importKey(secret);
    const enc = new TextEncoder();
    // Convert base64url back to standard base64 before decoding
    const b64 = signature.replace(/-/g, '+').replace(/_/g, '/');
    const padded = b64 + '='.repeat((4 - (b64.length % 4)) % 4);
    const sigBytes = Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
    return crypto.subtle.verify('HMAC', key, sigBytes, enc.encode(payload));
  } catch {
    return false;
  }
}

// ─── Token format: "<issuedAt>.<signature>" ───────────────────────────────────
// issuedAt is a Unix timestamp (seconds). The signature covers issuedAt only.
// The cookie value itself is not sensitive data — it proves the holder had a
// valid referrer at issuedAt, and expires server-side (TTL check).

export async function createSessionToken(secret: string): Promise<string> {
  const issuedAt = Math.floor(Date.now() / 1000).toString();
  const sig = await signPayload(issuedAt, secret);
  return `${issuedAt}.${sig}`;
}

export async function validateSessionToken(
  token: string,
  secret: string,
  ttlSeconds: number,
): Promise<'valid' | 'expired' | 'invalid'> {
  if (!token || !secret) return 'invalid';

  const dotIdx = token.lastIndexOf('.');
  if (dotIdx < 1) return 'invalid';

  const issuedAtStr = token.slice(0, dotIdx);
  const signature = token.slice(dotIdx + 1);

  const issuedAt = parseInt(issuedAtStr, 10);
  if (!Number.isFinite(issuedAt)) return 'invalid';

  const ok = await verifySignature(issuedAtStr, signature, secret);
  if (!ok) return 'invalid';

  const now = Math.floor(Date.now() / 1000);
  if (now - issuedAt > ttlSeconds) return 'expired';

  return 'valid';
}

// ─── Referrer validation ──────────────────────────────────────────────────────

/**
 * Returns true only when the Referer header contains a URL whose hostname
 * exactly matches one of the configured allowed hostnames.
 *
 * Defended against:
 *  - https://trusted.com.evil.com  (hostname !== trusted.com)
 *  - https://evil.com/?r=https://trusted.com  (query-string injection)
 *  - Missing/empty referrer
 */
export function isReferrerAllowed(
  referrer: string | null | undefined,
  allowedHostnames: Set<string>,
): boolean {
  if (!referrer || allowedHostnames.size === 0) return false;

  let hostname: string;
  try {
    hostname = new URL(referrer).hostname.toLowerCase();
  } catch {
    return false;
  }

  return allowedHostnames.has(hostname);
}

// ─── Cookie builder ───────────────────────────────────────────────────────────

export function buildSetCookieHeader(
  token: string,
  ttlSeconds: number,
  secure = true,
): string {
  const parts = [
    `entry_session=${encodeURIComponent(token)}`,
    'Path=/',
    `Max-Age=${ttlSeconds}`,
    'HttpOnly',
    'SameSite=Lax',
  ];
  if (secure) {
    parts.push('Secure');
  }
  return parts.join('; ');
}

// ─── Main decision function ───────────────────────────────────────────────────

export async function evaluateEntryAccess(opts: {
  sessionCookie: string | undefined;
  referrer: string | undefined;
  secureCookie?: boolean;
}): Promise<EntryDecision> {
  const secret = getSessionSecret();
  const ttl = getSessionTtl();
  const fallbackUrl = getFallbackUrl();
  const allowedHostnames = getAllowedHostnames();
  const secureCookie = opts.secureCookie ?? process.env.NODE_ENV === 'production';

  // ── 1. Valid existing session? ────────────────────────────────────────────
  if (opts.sessionCookie) {
    const state = await validateSessionToken(opts.sessionCookie, secret, ttl);

    if (state === 'valid') {
      return { result: 'ALLOW_SESSION_EXISTS' };
    }

    if (state === 'expired') {
      // Fall through to referrer check — session expired
    }
    // 'invalid' also falls through
  }

  // ── 2. Is referrer from an allowed domain? ────────────────────────────────
  if (isReferrerAllowed(opts.referrer, allowedHostnames)) {
    const token = await createSessionToken(secret);
    const setCookie = buildSetCookieHeader(token, ttl, secureCookie);
    return { result: 'ALLOW_VALID_REFERRER', setCookie };
  }

  // ── 3. Deny ───────────────────────────────────────────────────────────────
  return { result: 'DENY', fallbackUrl };
}
