'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  LayoutDashboard, User, BarChart3, Globe, Code2, CreditCard, Wallet, FolderOpen, LogOut, ChevronLeft, Menu, Zap,
} from 'lucide-react'
import { removePublisherTokens, getPublisherUser } from '@/lib/auth'
import type { AuthUser } from '@/types'

const navItems = [
  { label: 'Dashboard', href: '/publisher/dashboard', icon: LayoutDashboard },
  { label: 'Profile', href: '/publisher/profile', icon: User },
  { label: 'Statistics', href: '/publisher/statistics', icon: BarChart3 },
  { label: 'Websites', href: '/publisher/websites', icon: Globe },
  { label: 'Ad Units / Ad Code', href: '/publisher/ad-units', icon: Code2 },
  { label: 'Resources', href: '/publisher/videos', icon: FolderOpen },
  { label: 'Payment Methods', href: '/publisher/payment-methods', icon: Wallet },
  { label: 'Withdrawals', href: '/publisher/withdrawals', icon: CreditCard },
]

export default function PublisherSidebar() {
  const pathname = usePathname()
  const [user, setUser] = useState<AuthUser | null>(null)
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  useEffect(() => { setUser(getPublisherUser()) }, [])
  useEffect(() => { setMobileOpen(false) }, [pathname])

  const logout = () => { removePublisherTokens(); window.location.href = '/publisher/auth' }

  return (
    <>
      <button
        onClick={() => setMobileOpen(true)}
        className="lg:hidden fixed top-4 left-4 z-50 p-2.5 bg-gray-900 text-white rounded-xl shadow-lg"
      >
        <Menu className="w-5 h-5" />
      </button>

      {mobileOpen && (
        <div className="lg:hidden fixed inset-0 bg-black/40 backdrop-blur-sm z-40" onClick={() => setMobileOpen(false)} />
      )}

      <aside className={`fixed left-0 top-0 h-full bg-gray-900 z-50 flex flex-col transition-all duration-300 ${
        collapsed ? 'w-[72px]' : 'w-64'
      } ${mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}>

        {/* Logo */}
        <div className={`flex items-center ${collapsed ? 'justify-center' : 'justify-between'} p-4 h-16`}>
          {!collapsed && (
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 bg-primary rounded-lg flex items-center justify-center">
                <Zap className="w-4 h-4 text-white" />
              </div>
              <span className="text-base font-bold text-white">Publisher</span>
            </div>
          )}
          {collapsed && (
            <div className="w-8 h-8 bg-primary rounded-lg flex items-center justify-center">
              <Zap className="w-4 h-4 text-white" />
            </div>
          )}
          <button
            onClick={() => setCollapsed(!collapsed)}
            className="p-1.5 rounded-lg hover:bg-white/10 transition-colors hidden lg:block"
          >
            <ChevronLeft className={`w-4 h-4 text-gray-400 transition-transform ${collapsed ? 'rotate-180' : ''}`} />
          </button>
          <button onClick={() => setMobileOpen(false)} className="p-1.5 rounded-lg hover:bg-white/10 transition-colors lg:hidden">
            <ChevronLeft className="w-4 h-4 text-gray-400" />
          </button>
        </div>

        <div className="mx-3 h-px bg-white/10" />

        <nav className="flex-1 py-3 px-2 overflow-y-auto space-y-0.5">
          {navItems.map((item) => {
            const isActive = pathname === item.href || pathname.startsWith(item.href + '/')
            return (
              <Link
                key={item.href}
                href={item.href}
                title={collapsed ? item.label : undefined}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13px] font-medium transition-all ${
                  isActive
                    ? 'bg-primary text-white shadow-lg shadow-red-600/20'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                } ${collapsed ? 'justify-center' : ''}`}
              >
                <item.icon className="w-[18px] h-[18px] flex-shrink-0" />
                {!collapsed && <span>{item.label}</span>}
              </Link>
            )
          })}
        </nav>

        <div className="mx-3 h-px bg-white/10" />
        <div className="p-3">
          {!collapsed && user && (
            <div className="mb-2.5 px-2">
              <div className="flex items-center gap-2.5 mb-1">
                <div className="w-8 h-8 rounded-lg bg-white/10 flex items-center justify-center text-xs font-bold text-white">
                  {user.name?.charAt(0)?.toUpperCase() || 'P'}
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-white truncate">{user.name}</p>
                  <p className="text-[11px] text-gray-500 truncate">{user.email}</p>
                </div>
              </div>
            </div>
          )}
          <button
            onClick={logout}
            title="Sign Out"
            className={`flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-[13px] font-medium text-gray-400 hover:text-red-400 hover:bg-red-500/10 transition-all ${collapsed ? 'justify-center' : ''}`}
          >
            <LogOut className="w-[18px] h-[18px] flex-shrink-0" />
            {!collapsed && <span>Sign Out</span>}
          </button>
        </div>
      </aside>
    </>
  )
}
