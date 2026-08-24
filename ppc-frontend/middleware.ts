import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

const PUBLIC_PATHS = ['/', '/admin/auth', '/publisher/auth', '/publisher/pending']

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl

  // Allow public pages without any checks
  if (PUBLIC_PATHS.includes(pathname)) {
    // If already logged in as admin and hitting /admin/auth, redirect to dashboard
    if (pathname === '/admin/auth') {
      const adminToken = request.cookies.get('admin_token')?.value
      const adminUserCookie = request.cookies.get('admin_user')?.value
      if (adminToken && adminUserCookie) {
        return NextResponse.redirect(new URL('/admin/dashboard', request.url))
      }
    }
    // If already logged in as publisher and hitting /publisher/auth, redirect appropriately
    if (pathname === '/publisher/auth') {
      const publisherToken = request.cookies.get('publisher_token')?.value
      const publisherUserCookie = request.cookies.get('publisher_user')?.value
      if (publisherToken && publisherUserCookie) {
        try {
          const pu = JSON.parse(publisherUserCookie)
          if (pu?.status === 'active') {
            return NextResponse.redirect(new URL('/publisher/dashboard', request.url))
          } else {
            return NextResponse.redirect(new URL('/publisher/pending', request.url))
          }
        } catch {
          return NextResponse.redirect(new URL('/publisher/dashboard', request.url))
        }
      }
    }
    // If logged-in publisher hitting /publisher/pending and already active, send to dashboard
    if (pathname === '/publisher/pending') {
      const publisherToken = request.cookies.get('publisher_token')?.value
      const publisherUserCookie = request.cookies.get('publisher_user')?.value
      if (publisherToken && publisherUserCookie) {
        try {
          const pu = JSON.parse(publisherUserCookie)
          if (pu?.status === 'active') {
            return NextResponse.redirect(new URL('/publisher/dashboard', request.url))
          }
        } catch {}
      } else {
        return NextResponse.redirect(new URL('/publisher/auth', request.url))
      }
    }
    return NextResponse.next()
  }

  // ── Protect /admin/* routes ──────────────────────────────────────────────
  if (pathname.startsWith('/admin')) {
    const adminToken = request.cookies.get('admin_token')?.value
    const adminUserCookie = request.cookies.get('admin_user')?.value

    if (!adminToken || !adminUserCookie) {
      return NextResponse.redirect(new URL('/admin/auth', request.url))
    }

    try {
      const adminUser = JSON.parse(adminUserCookie)
      if (adminUser?.role !== 'admin') {
        return NextResponse.redirect(new URL('/admin/auth', request.url))
      }
    } catch {
      return NextResponse.redirect(new URL('/admin/auth', request.url))
    }

    return NextResponse.next()
  }

  // ── Protect /publisher/* routes ──────────────────────────────────────────
  if (pathname.startsWith('/publisher')) {
    const publisherToken = request.cookies.get('publisher_token')?.value
    const publisherUserCookie = request.cookies.get('publisher_user')?.value

    if (!publisherToken || !publisherUserCookie) {
      return NextResponse.redirect(new URL('/publisher/auth', request.url))
    }

    try {
      const publisherUser = JSON.parse(publisherUserCookie)
      if (publisherUser?.role === 'admin') {
        // Admin accidentally hitting publisher route → go to admin auth
        return NextResponse.redirect(new URL('/admin/auth', request.url))
      }
      // Block non-active publishers from accessing the portal
      if (publisherUser?.status && publisherUser.status !== 'active') {
        return NextResponse.redirect(new URL('/publisher/pending', request.url))
      }
    } catch {
      return NextResponse.redirect(new URL('/publisher/auth', request.url))
    }

    return NextResponse.next()
  }

  return NextResponse.next()
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|api).*)'],
}
