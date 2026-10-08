import { returnToPreviousPage } from '@/lib/prelander-navigation';

/** The visible root is not an entry point, even for a browser with a session. */
export function prelanderNoContentResponse(): Response {
  return new Response(null, {
    status: 204,
    headers: {
      // Chrome can treat a service-worker-forwarded response with nosniff
      // and no MIME type as a download, even for 204. Keep it a document.
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store, no-cache, must-revalidate, private',
      'X-Content-Type-Options': 'nosniff',
      'Referrer-Policy': 'no-referrer',
      'X-Robots-Tag': 'noindex, nofollow, noarchive',
    },
  });
}

/** Safe document committed for Chrome reloads of a clean prelander URL. */
export function prelanderChromeReloadResponse(): Response {
  return new Response(`<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow, noarchive">
<title>Page refreshed</title>
<style>
  body { margin: 0; min-height: 100vh; display: grid; place-items: center;
    background: #f0f2f5; color: #111827; font-family: system-ui, sans-serif; }
  main { max-width: 440px; padding: 32px; margin: 24px; border-radius: 16px;
    background: white; box-shadow: 0 8px 24px rgba(0,0,0,.08); }
  h1 { margin: 0 0 12px; font-size: 22px; }
  p { margin: 0; color: #4b5563; line-height: 1.6; }
</style></head><body><main><h1>Page refreshed</h1>
<p>For your security, this page cannot be reopened by refreshing. Return to the page where you started and open a new link.</p>
</main></body></html>`, {
    status: 200,
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'Content-Disposition': 'inline',
      'Cache-Control': 'no-store, no-cache, must-revalidate, private',
      'X-Content-Type-Options': 'nosniff',
      'X-Frame-Options': 'DENY',
      'Referrer-Policy': 'no-referrer',
      'X-Robots-Tag': 'noindex, nofollow, noarchive',
      'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'",
    },
  });
}

export const SESSION_UNAVAILABLE_TITLE = 'Session expired or unavailable';
export const SESSION_UNAVAILABLE_MESSAGE =
  'This link requires an active session. Return to the page where you started and open a new link.';

export const SESSION_UNAVAILABLE_HTML = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${SESSION_UNAVAILABLE_TITLE}</title>
<style>
  body { margin: 0; min-height: 100vh; display: grid; place-items: center;
    background: #f0f2f5; color: #111827; font-family: system-ui, sans-serif; }
  main { max-width: 440px; padding: 32px; margin: 24px; border-radius: 16px; background: white; }
  h1 { font-size: 24px; line-height: 1.3; }
  p { color: #4b5563; line-height: 1.6; }
</style>
</head>
<body><main><h1>${SESSION_UNAVAILABLE_TITLE}</h1><p>${SESSION_UNAVAILABLE_MESSAGE}</p></main></body>
</html>`;

export function sessionUnavailableResponse(status: 403 | 503 = 403): Response {
  return new Response(SESSION_UNAVAILABLE_HTML, {
    status,
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store, private',
      'X-Content-Type-Options': 'nosniff',
      'Referrer-Policy': 'no-referrer',
      'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'",
    },
  });
}

/** Deny content while using the same navigation fallback as a pasted new tab. */
export function prelanderFallbackResponse(status: 403 | 503 = 403): Response {
  return new Response(`<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title></title>
<script>(${returnToPreviousPage.toString()})()</script></head><body></body></html>`, {
    status,
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'Cache-Control': 'no-store, private',
      'X-Content-Type-Options': 'nosniff',
      'X-Frame-Options': 'DENY',
      'Referrer-Policy': 'no-referrer',
      // This document contains only our fixed navigation script, no inputs
      // or protected content. Do not mark it for the source-deterrent worker.
      'Content-Security-Policy': "default-src 'none'; script-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'",
    },
  });
}
