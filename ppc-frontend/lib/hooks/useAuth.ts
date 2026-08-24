'use client'
import { create } from 'zustand'
import {
  getAdminUser, getAdminAccessToken, setAdminTokens, setAdminUser, removeAdminTokens,
  getPublisherUser, getPublisherAccessToken, setPublisherTokens, setPublisherUser, removePublisherTokens,
} from '@/lib/auth'
import { authApi } from '@/lib/api'
import type { AuthUser } from '@/types'

interface AuthState {
  user: AuthUser | null
  isAuthenticated: boolean
  isLoading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  initialize: () => void
}

function isAdminPath(): boolean {
  if (typeof window === 'undefined') return false
  return window.location.pathname.startsWith('/admin')
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  isLoading: true,

  initialize: () => {
    const user = isAdminPath() ? getAdminUser() : getPublisherUser()
    const token = isAdminPath() ? getAdminAccessToken() : getPublisherAccessToken()
    set({ user, isAuthenticated: !!token && !!user, isLoading: false })
  },

  login: async (email: string, password: string) => {
    const response = await authApi.login({ email, password })
    const data = response.data
    const user: AuthUser = {
      id: data.publisher_id,
      name: data.name,
      email: data.email,
      role: data.role,
      status: data.status || 'active',
    }
    if (isAdminPath()) {
      setAdminTokens(data.access_token, data.refresh_token)
      setAdminUser(user)
    } else {
      setPublisherTokens(data.access_token, data.refresh_token)
      setPublisherUser(user)
    }
    set({ user, isAuthenticated: true })
  },

  logout: () => {
    try { authApi.logout() } catch {}
    if (isAdminPath()) {
      removeAdminTokens()
      window.location.href = '/admin/auth'
    } else {
      removePublisherTokens()
      window.location.href = '/publisher/auth'
    }
    set({ user: null, isAuthenticated: false })
  },
}))
