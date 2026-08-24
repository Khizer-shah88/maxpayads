'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { Eye, EyeOff, Shield, Lock } from 'lucide-react'
import { toast } from 'sonner'
import { authApi } from '@/lib/api'
import { setAdminTokens, setAdminUser } from '@/lib/auth'
import type { AuthUser } from '@/types'

export default function AdminAuthPage() {
  const router = useRouter()
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [loginEmail, setLoginEmail] = useState('')
  const [loginPassword, setLoginPassword] = useState('')

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      const res = await authApi.login({ email: loginEmail, password: loginPassword })
      const data = res.data
      if (data.role !== 'admin') {
        toast.error('Access denied. This login is for admins only.')
        setLoading(false)
        return
      }
      setAdminTokens(data.access_token, data.refresh_token)
      const user: AuthUser = {
        id: data.publisher_id,
        name: data.name,
        email: data.email,
        role: data.role,
        status: 'active',
      }
      setAdminUser(user)
      toast.success('Welcome back, Admin!')
      router.push('/admin/dashboard')
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Invalid credentials')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen animated-gradient flex items-center justify-center px-4">
      <div className="w-full max-w-md animate-scale-in">
        <div className="glass-dark rounded-2xl p-8 shadow-2xl">
          {/* Header */}
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-white/10 mb-4">
              <Shield className="w-7 h-7 text-red-400" />
            </div>
            <h1 className="text-xl font-bold text-white">Admin Portal</h1>
            <p className="text-gray-400 mt-1 text-sm flex items-center justify-center gap-1.5">
              <Lock className="w-3.5 h-3.5" />
              Restricted Access
            </p>
          </div>

          <form onSubmit={handleLogin} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1.5">Email</label>
              <input
                type="email"
                value={loginEmail}
                onChange={(e) => setLoginEmail(e.target.value)}
                required
                className="w-full px-4 py-3 border border-white/10 rounded-xl text-white bg-white/5 focus:outline-none focus:ring-2 focus:ring-red-500/30 focus:border-red-500/50 transition-all placeholder:text-gray-600"
                placeholder="admin@maxpayads.com"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1.5">Password</label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={loginPassword}
                  onChange={(e) => setLoginPassword(e.target.value)}
                  required
                  className="w-full px-4 py-3 border border-white/10 rounded-xl text-white bg-white/5 focus:outline-none focus:ring-2 focus:ring-red-500/30 focus:border-red-500/50 transition-all pr-11 placeholder:text-gray-600"
                  placeholder="Enter password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3.5 top-1/2 -translate-y-1/2 text-gray-500 hover:text-white transition-colors"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-red-600 hover:bg-red-700 text-white font-semibold py-3 rounded-xl transition-all disabled:bg-gray-700 disabled:cursor-not-allowed hover:shadow-glow"
            >
              {loading ? (
                <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin mx-auto" />
              ) : (
                'Sign In'
              )}
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
