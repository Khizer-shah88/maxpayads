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
