import { NextRequest } from 'next/server'

export const dynamic = 'force-dynamic'

// Preserve the browser hostname through the internal proxy. Role decisions
// must never see "fastapi" or trust a client-supplied X-Forwarded-Host.
async function proxy(request: NextRequest) {
  const base = process.env.NEXT_BACKEND_URL || 'http://localhost:8000'
  const url = `${base}${request.nextUrl.pathname.slice(4)}${request.nextUrl.search}`
  const headers = new Headers(request.headers)
  headers.delete('connection')
  headers.delete('content-length')
  headers.delete('x-forwarded-host')
  headers.set('host', request.headers.get('host') || request.nextUrl.host)
  const response = await fetch(url, {
    method: request.method,
    headers,
    body: ['GET', 'HEAD'].includes(request.method) ? undefined : await request.arrayBuffer(),
    redirect: 'manual',
    cache: 'no-store',
  })
  const outgoing = new Headers(response.headers)
  outgoing.delete('content-encoding')
  outgoing.delete('content-length')
  outgoing.delete('set-cookie')
  for (const cookie of response.headers.getSetCookie()) outgoing.append('set-cookie', cookie)
  return new Response(response.body, { status: response.status, headers: outgoing })
}

export { proxy as GET, proxy as POST, proxy as PUT, proxy as PATCH, proxy as DELETE, proxy as OPTIONS, proxy as HEAD }
