'use client'

import { useState, useEffect, Suspense } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { Eye, EyeOff, Zap, ArrowRight, BarChart3, DollarSign, Shield, Globe } from 'lucide-react'
import { toast } from 'sonner'
import { authApi } from '@/lib/api'
import { setPublisherTokens, setPublisherUser } from '@/lib/auth'
import type { AuthUser } from '@/types'
import Link from 'next/link'

const highlights = [
  { icon: <BarChart3 className="w-5 h-5" />, text: 'Real-time analytics dashboard' },
  { icon: <DollarSign className="w-5 h-5" />, text: 'Competitive CPC rates' },
  { icon: <Shield className="w-5 h-5" />, text: 'Advanced fraud protection' },
  { icon: <Globe className="w-5 h-5" />, text: '180+ countries covered' },
]

export default function PublisherAuthPage() {
  return (
    <Suspense fallback={null}>
      <PublisherAuthContent />
    </Suspense>
  )
}

function PublisherAuthContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [tab, setTab] = useState<'login' | 'signup'>('login')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (searchParams.get('tab') === 'signup') setTab('signup')
  }, [searchParams])

  // Login state
  const [loginEmail, setLoginEmail] = useState('')
  const [loginPassword, setLoginPassword] = useState('')

  // Signup state
  const [signupName, setSignupName] = useState('')
  const [signupEmail, setSignupEmail] = useState('')
  const [signupPassword, setSignupPassword] = useState('')
  const [signupConfirm, setSignupConfirm] = useState('')
  const [signupDomain, setSignupDomain] = useState('')

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      const res = await authApi.login({ email: loginEmail, password: loginPassword })
      const data = res.data
      if (data.role === 'admin') {
        toast.error('Access denied. This login is for publishers only.')
        setLoading(false)
        return
      }
      setPublisherTokens(data.access_token, data.refresh_token)
      const user: AuthUser = {
        id: data.publisher_id,
        name: data.name,
        email: data.email,
        role: data.role,
        status: data.status || 'active',
      }
      setPublisherUser(user)
      if (user.status !== 'active') {
        router.push('/publisher/pending')
      } else {
        toast.success('Welcome back!')
        router.push('/publisher/dashboard')
      }
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Invalid credentials')
    } finally {
      setLoading(false)
    }
  }

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault()
    if (signupPassword !== signupConfirm) {
      toast.error('Passwords do not match')
      return
    }
    if (signupPassword.length < 8) {
      toast.error('Password must be at least 8 characters')
      return
    }
    setLoading(true)
    try {
      await authApi.register({
        name: signupName,
        email: signupEmail,
        password: signupPassword,
        website_domain: signupDomain || undefined,
      })
      toast.success('Account created! Awaiting admin approval. Please log in.')
      setTab('login')
      setLoginEmail(signupEmail)
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Registration failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex">
      {/* Left Panel - Branding */}
      <div className="hidden lg:flex lg:w-1/2 relative animated-gradient">
        <div className="absolute inset-0 bg-black/20" />
        <div className="relative z-10 flex flex-col justify-between p-12 w-full">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2.5">
            <div className="w-9 h-9 bg-white rounded-lg flex items-center justify-center">
              <Zap className="w-5 h-5 text-primary" />
            </div>
            <span className="text-xl font-bold text-white">vertexmonetize</span>
          </Link>

          {/* Center content */}
          <div className="max-w-md">
            <h2 className="text-4xl font-bold text-white leading-tight">
              Turn your website traffic into
              <span className="text-red-400"> consistent revenue</span>
            </h2>
            <p className="mt-4 text-gray-300 leading-relaxed">
              Join thousands of publishers earning daily with our premium vertexmonetize advertising platform.
            </p>

            <div className="mt-10 space-y-4">
              {highlights.map((item, i) => (
                <div key={i} className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-white/10 flex items-center justify-center text-red-400 flex-shrink-0">
                    {item.icon}
                  </div>
                  <span className="text-white/90 text-sm font-medium">{item.text}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Bottom testimonial */}
          <div className="glass-dark rounded-xl p-5 max-w-md">
            <p className="text-white/80 text-sm italic leading-relaxed">
              &ldquo;Switched to vertexmonetize 6 months ago and my ad revenue increased by 40%.
              The analytics dashboard is incredible.&rdquo;
            </p>
            <div className="mt-3 flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-red-500/30 flex items-center justify-center text-white text-xs font-bold">
                JD
              </div>
              <div>
                <p className="text-white text-sm font-medium">John Doe</p>
                <p className="text-gray-400 text-xs">Publisher, TechBlog.com</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Right Panel - Auth Form */}
      <div className="w-full lg:w-1/2 flex items-center justify-center px-4 py-12 bg-white">
        <div className="w-full max-w-md animate-fade-in">
          {/* Mobile logo */}
          <div className="lg:hidden mb-8 text-center">
            <Link href="/" className="inline-flex items-center gap-2">
              <div className="w-8 h-8 bg-primary rounded-lg flex items-center justify-center">
                <Zap className="w-4 h-4 text-white" />
              </div>
              <span className="text-lg font-bold text-black">vertexmonetize</span>
            </Link>
          </div>

          <div className="mb-8">
            <h1 className="text-2xl font-bold text-black">
              {tab === 'login' ? 'Welcome back' : 'Create your account'}
            </h1>
            <p className="text-text-secondary mt-1.5">
              {tab === 'login'
                ? 'Sign in to access your publisher dashboard'
                : 'Start monetizing your traffic in minutes'}
            </p>
          </div>

          {/* Tabs */}
          <div className="flex bg-gray-100 rounded-xl p-1 mb-8">
            <button
              onClick={() => setTab('login')}
              className={`flex-1 py-2.5 text-sm font-semibold rounded-lg transition-all ${
                tab === 'login'
                  ? 'bg-white text-black shadow-sm'
                  : 'text-text-muted hover:text-black'
              }`}
            >
              Sign In
            </button>
            <button
              onClick={() => setTab('signup')}
              className={`flex-1 py-2.5 text-sm font-semibold rounded-lg transition-all ${
                tab === 'signup'
                  ? 'bg-white text-black shadow-sm'
                  : 'text-text-muted hover:text-black'
              }`}
            >
              Sign Up
            </button>
          </div>

          {tab === 'login' ? (
            <form onSubmit={handleLogin} className="space-y-5">
              <div>
                <label className="block text-sm font-medium text-black mb-1.5">Email address</label>
                <input
                  type="email"
                  value={loginEmail}
                  onChange={(e) => setLoginEmail(e.target.value)}
                  required
                  className="w-full px-4 py-3 border border-gray-200 rounded-xl text-black bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all placeholder:text-gray-400"
                  placeholder="you@example.com"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-black mb-1.5">Password</label>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={loginPassword}
                    onChange={(e) => setLoginPassword(e.target.value)}
                    required
                    className="w-full px-4 py-3 border border-gray-200 rounded-xl text-black bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all pr-11 placeholder:text-gray-400"
                    placeholder="Enter your password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-black transition-colors"
                  >
                    {showPassword ? <EyeOff className="w-4.5 h-4.5" /> : <Eye className="w-4.5 h-4.5" />}
                  </button>
                </div>
              </div>
              <button
                type="submit"
                disabled={loading}
                className="group w-full flex items-center justify-center gap-2 bg-primary hover:bg-primary-dark text-white font-semibold py-3 rounded-xl transition-all disabled:bg-gray-300 disabled:cursor-not-allowed hover:shadow-glow"
              >
                {loading ? (
                  <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : (
                  <>
                    Sign In
                    <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                  </>
                )}
              </button>
            </form>
          ) : (
            <form onSubmit={handleSignup} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-black mb-1.5">Full name</label>
                <input
                  type="text"
                  value={signupName}
                  onChange={(e) => setSignupName(e.target.value)}
                  required
                  className="w-full px-4 py-3 border border-gray-200 rounded-xl text-black bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all placeholder:text-gray-400"
                  placeholder="John Doe"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-black mb-1.5">Email address</label>
                <input
                  type="email"
                  value={signupEmail}
                  onChange={(e) => setSignupEmail(e.target.value)}
                  required
                  className="w-full px-4 py-3 border border-gray-200 rounded-xl text-black bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all placeholder:text-gray-400"
                  placeholder="you@example.com"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-black mb-1.5">
                  Website domain <span className="text-text-muted font-normal">(optional)</span>
                </label>
                <input
                  type="text"
                  value={signupDomain}
                  onChange={(e) => setSignupDomain(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-200 rounded-xl text-black bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all placeholder:text-gray-400"
                  placeholder="example.com"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-black mb-1.5">Password</label>
                  <input
                    type="password"
                    value={signupPassword}
                    onChange={(e) => setSignupPassword(e.target.value)}
                    required
                    className="w-full px-4 py-3 border border-gray-200 rounded-xl text-black bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all placeholder:text-gray-400"
                    placeholder="Min 6 chars"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-black mb-1.5">Confirm</label>
                  <input
                    type="password"
                    value={signupConfirm}
                    onChange={(e) => setSignupConfirm(e.target.value)}
                    required
                    className="w-full px-4 py-3 border border-gray-200 rounded-xl text-black bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all placeholder:text-gray-400"
                    placeholder="Confirm"
                  />
                </div>
              </div>
              <button
                type="submit"
                disabled={loading}
                className="group w-full flex items-center justify-center gap-2 bg-primary hover:bg-primary-dark text-white font-semibold py-3 rounded-xl transition-all disabled:bg-gray-300 disabled:cursor-not-allowed hover:shadow-glow"
              >
                {loading ? (
                  <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : (
                  <>
                    Create Account
                    <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                  </>
                )}
              </button>
              <p className="text-xs text-text-muted text-center">
                By creating an account, you agree to our Terms of Service and Privacy Policy
              </p>
            </form>
          )}

          <div className="mt-8 text-center">
            <Link href="/" className="text-sm text-text-muted hover:text-primary transition-colors">
              &larr; Back to Home
            </Link>
          </div>
        </div>
      </div>
    </div>
  )
}
