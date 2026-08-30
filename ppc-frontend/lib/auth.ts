import Cookies from 'js-cookie'
import type { AuthUser } from '@/types'

// ─── ADMIN cookies (admin_token, admin_user) ───────────────────────────────
export function getAdminAccessToken(): string | undefined {
  return Cookies.get('admin_token')
}

export function setAdminTokens(accessToken: string, refreshToken: string) {
  Cookies.set('admin_token', accessToken, { expires: 1 })
  Cookies.set('admin_refresh_token', refreshToken, { expires: 30 })
}

export function setAdminUser(user: AuthUser) {
  Cookies.set('admin_user', JSON.stringify(user), { expires: 1 })
}

export function getAdminUser(): AuthUser | null {
  try {
    const s = Cookies.get('admin_user')
    if (s) return JSON.parse(s)
  } catch {}
  return null
}

export function removeAdminTokens() {
  Cookies.remove('admin_token')
  Cookies.remove('admin_refresh_token')
  Cookies.remove('admin_user')
}

// ─── PUBLISHER cookies (publisher_token, publisher_user) ───────────────────
export function getPublisherAccessToken(): string | undefined {
  return Cookies.get('publisher_token')
}

export function setPublisherTokens(accessToken: string, refreshToken: string) {
  Cookies.set('publisher_token', accessToken, { expires: 1 })
  Cookies.set('publisher_refresh_token', refreshToken, { expires: 30 })
}

export function setPublisherUser(user: AuthUser) {
  Cookies.set('publisher_user', JSON.stringify(user), { expires: 1 })
}

export function getPublisherUser(): AuthUser | null {
  try {
    const s = Cookies.get('publisher_user')
    if (s) return JSON.parse(s)
  } catch {}
  return null
}

export function removePublisherTokens() {
  Cookies.remove('publisher_token')
  Cookies.remove('publisher_refresh_token')
  Cookies.remove('publisher_user')
}

// ─── Generic helpers (used by useAuth / components that don't know the role) ─
// Reads whichever cookie is available based on current path
export function getAccessToken(): string | undefined {
  if (typeof window !== 'undefined' && window.location.pathname.startsWith('/admin')) {
    return getAdminAccessToken()
  }
  return getPublisherAccessToken()
}

export function getUser(): AuthUser | null {
  if (typeof window !== 'undefined' && window.location.pathname.startsWith('/admin')) {
    return getAdminUser()
  }
  return getPublisherUser()
}

// Legacy helpers (kept for backward compat — prefer the role-specific ones)
export function setTokens(_accessToken: string, _refreshToken: string) {
  // no-op: use setAdminTokens / setPublisherTokens directly
}

export function setUser(_user: AuthUser) {
  // no-op: use setAdminUser / setPublisherUser directly
}

export function removeTokens() {
  removeAdminTokens()
  removePublisherTokens()
}

export function isAuthenticated(): boolean {
  return !!getAccessToken()
}

export function isAdmin(): boolean {
  return getAdminUser()?.role === 'admin'
}

export function isPublisher(): boolean {
  return getPublisherUser()?.role === 'publisher'
}

export function logout() {
  removeAdminTokens()
  removePublisherTokens()
  if (typeof window !== 'undefined') {
    const isAdmin = window.location.pathname.startsWith('/admin')
    window.location.href = isAdmin ? '/admin/auth' : '/publisher/auth'
  }
}
