'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { Clock, Shield, Mail, LogOut, RefreshCw, Zap, CheckCircle2, ArrowRight } from 'lucide-react'
import { getPublisherUser, removePublisherTokens } from '@/lib/auth'
import { authApi } from '@/lib/api'
import type { AuthUser } from '@/types'
import Link from 'next/link'

export default function PendingApprovalPage() {
  const router = useRouter()
  const [user, setUser] = useState<AuthUser | null>(null)
  const [checking, setChecking] = useState(false)

  useEffect(() => {
    const u = getPublisherUser()
    if (!u) {
      router.push('/publisher/auth')
      return
    }
    if (u.status === 'active') {
      router.push('/publisher/dashboard')
      return
    }
    setUser(u)
  }, [router])

  const checkStatus = async () => {
    setChecking(true)
    try {
      const res = await authApi.me()
      const data = res.data
      if (data.status === 'active') {
        // Update stored user with new status
        const u = getPublisherUser()
        if (u) {
          u.status = 'active'
          // Re-store user cookie with updated status
          document.cookie = `publisher_user=${encodeURIComponent(JSON.stringify(u))};path=/;max-age=86400`
        }
        router.push('/publisher/dashboard')
      } else {
        setUser(prev => prev ? { ...prev, status: data.status } : prev)
      }
    } catch {
      // Token might be expired
    } finally {
      setChecking(false)
    }
  }

  const handleLogout = () => {
    removePublisherTokens()
    router.push('/publisher/auth')
  }

  if (!user) return null

  const isSuspended = user.status === 'suspended'

  return (
    <div className="min-h-screen bg-[#f8f9fb] flex">
      {/* Left decorative panel */}
      <div className="hidden lg:flex lg:w-[45%] relative animated-gradient">
        <div className="absolute inset-0 bg-black/20" />
        <div className="relative z-10 flex flex-col justify-between p-12 w-full">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="w-9 h-9 bg-white rounded-lg flex items-center justify-center">
              <Zap className="w-5 h-5 text-primary" />
            </div>
            <span className="text-xl font-bold text-white">Max Pay Ads</span>
          </Link>

          <div className="max-w-md">
            <h2 className="text-3xl font-bold text-white leading-tight">
              Your account is being
              <span className="text-red-400"> reviewed</span>
            </h2>
            <p className="mt-4 text-gray-300 leading-relaxed">
              Our team carefully reviews every publisher application to ensure quality and security for our advertising network.
            </p>

            <div className="mt-10 space-y-5">
              <div className="flex items-start gap-4">
                <div className="w-10 h-10 rounded-xl bg-white/10 flex items-center justify-center text-emerald-400 flex-shrink-0 mt-0.5">
                  <CheckCircle2 className="w-5 h-5" />
                </div>
                <div>
                  <p className="text-white font-medium text-sm">Account Created</p>
                  <p className="text-gray-400 text-xs mt-0.5">Your registration is complete</p>
                </div>
              </div>
              <div className="flex items-start gap-4">
                <div className="w-10 h-10 rounded-xl bg-white/10 flex items-center justify-center text-amber-400 flex-shrink-0 mt-0.5 ring-2 ring-amber-400/30">
                  <Clock className="w-5 h-5" />
                </div>
                <div>
                  <p className="text-white font-medium text-sm">Under Review</p>
                  <p className="text-gray-400 text-xs mt-0.5">Admin is reviewing your application</p>
                </div>
              </div>
              <div className="flex items-start gap-4">
                <div className="w-10 h-10 rounded-xl bg-white/10 flex items-center justify-center text-gray-500 flex-shrink-0 mt-0.5">
                  <ArrowRight className="w-5 h-5" />
                </div>
                <div>
                  <p className="text-gray-400 font-medium text-sm">Access Granted</p>
                  <p className="text-gray-500 text-xs mt-0.5">Full dashboard access once approved</p>
                </div>
              </div>
            </div>
          </div>

          <div className="glass-dark rounded-xl p-5 max-w-md">
            <p className="text-white/80 text-sm leading-relaxed">
              Most applications are reviewed within 24 hours. You&apos;ll get full access to analytics, ad management, and earnings once approved.
            </p>
          </div>
        </div>
      </div>

      {/* Right content */}
      <div className="w-full lg:w-[55%] flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-lg animate-fade-in">
          {/* Mobile logo */}
          <div className="lg:hidden mb-10 text-center">
            <Link href="/" className="inline-flex items-center gap-2">
              <div className="w-8 h-8 bg-primary rounded-lg flex items-center justify-center">
                <Zap className="w-4 h-4 text-white" />
              </div>
              <span className="text-lg font-bold text-gray-900">Max Pay Ads</span>
            </Link>
          </div>

          {/* Status card */}
          <div className="bg-white rounded-2xl border border-gray-100 overflow-hidden">
            {/* Header */}
            <div className={`px-8 py-6 ${isSuspended ? 'bg-red-50 border-b border-red-100' : 'bg-amber-50 border-b border-amber-100'}`}>
              <div className="flex items-center gap-4">
                <div className={`w-14 h-14 rounded-2xl flex items-center justify-center ${isSuspended ? 'bg-red-100' : 'bg-amber-100'}`}>
                  {isSuspended
                    ? <Shield className={`w-7 h-7 text-red-500`} />
                    : <Clock className={`w-7 h-7 text-amber-500`} />
                  }
                </div>
                <div>
                  <h1 className={`text-xl font-bold ${isSuspended ? 'text-red-900' : 'text-amber-900'}`}>
                    {isSuspended ? 'Account Suspended' : 'Awaiting Approval'}
                  </h1>
                  <p className={`text-sm mt-0.5 ${isSuspended ? 'text-red-600' : 'text-amber-600'}`}>
                    {isSuspended
                      ? 'Your account has been suspended by an administrator'
                      : 'Your account is currently under review'
                    }
                  </p>
                </div>
              </div>
            </div>

            {/* Body */}
            <div className="px-8 py-6 space-y-5">
              {/* User info */}
              <div className="flex items-center gap-3 p-4 bg-gray-50 rounded-xl">
                <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold text-sm">
                  {user.name?.charAt(0)?.toUpperCase() || 'P'}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-gray-900 truncate">{user.name}</p>
                  <p className="text-xs text-gray-500 truncate">{user.email}</p>
                </div>
                <span className={`px-2.5 py-1 rounded-lg text-xs font-semibold ${
                  isSuspended ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'
                }`}>
                  {isSuspended ? 'Suspended' : 'Pending'}
                </span>
              </div>

              {/* Message */}
              {isSuspended ? (
                <div className="space-y-3">
                  <p className="text-sm text-gray-600 leading-relaxed">
                    Your publisher account has been suspended. This may be due to a policy violation or unusual activity.
                    Please contact the administrator for more information.
                  </p>
                  <div className="flex items-center gap-3 p-3.5 bg-red-50 rounded-xl border border-red-100">
                    <Mail className="w-5 h-5 text-red-400 flex-shrink-0" />
                    <p className="text-sm text-red-700">
                      Contact support to resolve this issue and restore your account access.
                    </p>
                  </div>
                </div>
              ) : (
                <div className="space-y-3">
                  <p className="text-sm text-gray-600 leading-relaxed">
                    Thank you for registering! An administrator will review your application shortly.
                    Once approved, you&apos;ll have full access to your publisher dashboard.
                  </p>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div className="flex items-center gap-2.5 p-3 bg-blue-50 rounded-xl">
                      <Shield className="w-4 h-4 text-blue-500 flex-shrink-0" />
                      <span className="text-xs font-medium text-blue-700">Identity check</span>
                    </div>
                    <div className="flex items-center gap-2.5 p-3 bg-purple-50 rounded-xl">
                      <Mail className="w-4 h-4 text-purple-500 flex-shrink-0" />
                      <span className="text-xs font-medium text-purple-700">Email verified</span>
                    </div>
                    <div className="flex items-center gap-2.5 p-3 bg-emerald-50 rounded-xl">
                      <CheckCircle2 className="w-4 h-4 text-emerald-500 flex-shrink-0" />
                      <span className="text-xs font-medium text-emerald-700">Quality review</span>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Actions */}
            <div className="px-8 py-5 border-t border-gray-100 bg-gray-50/50 flex flex-col sm:flex-row gap-3">
              {!isSuspended && (
                <button
                  onClick={checkStatus}
                  disabled={checking}
                  className="flex-1 flex items-center justify-center gap-2 px-5 py-2.5 bg-primary hover:bg-primary-dark text-white font-semibold rounded-xl transition-all disabled:opacity-60 text-sm"
                >
                  {checking ? (
                    <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  ) : (
                    <RefreshCw className="w-4 h-4" />
                  )}
                  {checking ? 'Checking...' : 'Check Status'}
                </button>
              )}
              <button
                onClick={handleLogout}
                className="flex-1 flex items-center justify-center gap-2 px-5 py-2.5 border border-gray-200 text-gray-700 hover:bg-gray-100 font-semibold rounded-xl transition-all text-sm"
              >
                <LogOut className="w-4 h-4" />
                Sign Out
              </button>
            </div>
          </div>

          {/* Bottom link */}
          <div className="mt-6 text-center">
            <Link href="/" className="text-sm text-gray-400 hover:text-primary transition-colors">
              &larr; Back to Home
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}
