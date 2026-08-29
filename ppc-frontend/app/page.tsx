'use client'

import Link from 'next/link'
import { BarChart3, DollarSign, Globe, Shield, Zap, TrendingUp, Users, MousePointer, ArrowRight, CheckCircle } from 'lucide-react'

const stats = [
  { label: 'Active Publishers', value: '2,500+', icon: <Users className="w-5 h-5" /> },
  { label: 'Countries Covered', value: '180+', icon: <Globe className="w-5 h-5" /> },
  { label: 'Clicks Processed', value: '50M+', icon: <MousePointer className="w-5 h-5" /> },
  { label: 'Revenue Paid', value: '$2M+', icon: <DollarSign className="w-5 h-5" /> },
]

const features = [
  {
    icon: <DollarSign className="w-6 h-6" />,
    title: 'High CPC Rates',
    description: 'Earn competitive rates per click with our premium advertiser network. Maximize your revenue potential.',
  },
  {
    icon: <Shield className="w-6 h-6" />,
    title: 'Fraud Protection',
    description: 'Advanced ML-powered fraud detection ensures only valid clicks count. Your earnings stay protected.',
  },
  {
    icon: <BarChart3 className="w-6 h-6" />,
    title: 'Real-Time Analytics',
    description: 'Track clicks, earnings, and performance in real-time with detailed country and device breakdowns.',
  },
  {
    icon: <Zap className="w-6 h-6" />,
    title: 'Instant Integration',
    description: 'Add a single script tag to your site. Our ad units auto-optimize for your audience and layout.',
  },
  {
    icon: <Globe className="w-6 h-6" />,
    title: 'Global Coverage',
    description: 'Geo-targeted campaigns across 180+ countries with localized CPC rates for maximum relevance.',
  },
  {
    icon: <TrendingUp className="w-6 h-6" />,
    title: 'Fast Payouts',
    description: 'Low minimum withdrawal threshold with multiple payment methods. Get paid quickly and reliably.',
  },
]

const steps = [
  { step: '01', title: 'Create Account', description: 'Sign up in seconds with your email and website details.' },
  { step: '02', title: 'Add Your Website', description: 'Register your website and get approved by our team.' },
  { step: '03', title: 'Embed Ad Code', description: 'Copy and paste a simple script tag into your site.' },
  { step: '04', title: 'Start Earning', description: 'Watch your earnings grow as visitors click on ads.' },
]

export default function HomePage() {
  return (
    <div className="min-h-screen bg-white">
      {/* Navigation */}
      <nav className="fixed top-0 left-0 right-0 z-50 glass">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 bg-primary rounded-lg flex items-center justify-center">
                <Zap className="w-4 h-4 text-white" />
              </div>
              <span className="text-lg font-bold text-black">Vertex Monetize</span>
            </div>
            <div className="hidden md:flex items-center gap-8">
              <a href="#features" className="text-sm text-text-secondary hover:text-black transition-colors">Features</a>
              <a href="#how-it-works" className="text-sm text-text-secondary hover:text-black transition-colors">How It Works</a>
              <a href="#stats" className="text-sm text-text-secondary hover:text-black transition-colors">Stats</a>
            </div>
            <div className="flex items-center gap-3">
              <Link
                href="/publisher/auth"
                className="text-sm font-medium text-text-secondary hover:text-black transition-colors"
              >
                Sign In
              </Link>
              <Link
                href="/publisher/auth?tab=signup"
                className="text-sm font-semibold bg-primary hover:bg-primary-dark text-white px-5 py-2 rounded-lg transition-all hover:shadow-glow"
              >
                Get Started
              </Link>
            </div>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="relative pt-32 pb-20 lg:pt-40 lg:pb-32 overflow-hidden">
        {/* Background decorations */}
        <div className="absolute top-20 left-10 w-72 h-72 bg-red-100 rounded-full mix-blend-multiply filter blur-3xl opacity-30 animate-float" />
        <div className="absolute top-40 right-10 w-72 h-72 bg-orange-100 rounded-full mix-blend-multiply filter blur-3xl opacity-30 animate-float-delay" />
        <div className="absolute -bottom-10 left-1/2 w-96 h-96 bg-red-50 rounded-full mix-blend-multiply filter blur-3xl opacity-20" />

        <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-4xl mx-auto">
            <div className="animate-fade-in-up">
              <span className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-red-50 text-primary text-sm font-medium mb-6">
                <span className="w-2 h-2 bg-primary rounded-full animate-pulse" />
                Trusted by 2,500+ Publishers Worldwide
              </span>
            </div>

            <h1 className="animate-fade-in-up-delay-1 text-4xl sm:text-5xl lg:text-7xl font-extrabold text-black leading-tight tracking-tight">
              Monetize Your Traffic
              <br />
              <span className="gradient-text">With Every Click</span>
            </h1>

            <p className="animate-fade-in-up-delay-2 mt-6 text-lg sm:text-xl text-text-secondary max-w-2xl mx-auto leading-relaxed">
              Join the premium vertexmonetize advertising network. Embed our high-converting ad units,
              track performance in real-time, and earn competitive rates from global advertisers.
            </p>

            <div className="animate-fade-in-up-delay-3 mt-10 flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link
                href="/publisher/auth?tab=signup"
                className="group w-full sm:w-auto flex items-center justify-center gap-2 bg-primary hover:bg-primary-dark text-white font-semibold px-8 py-4 rounded-xl transition-all hover:shadow-glow-lg text-lg"
              >
                Start Earning Today
                <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
              </Link>
              <Link
                href="/publisher/auth"
                className="w-full sm:w-auto flex items-center justify-center gap-2 bg-white border-2 border-gray-200 hover:border-primary text-black font-semibold px-8 py-4 rounded-xl transition-all text-lg"
              >
                Publisher Login
              </Link>
            </div>

            <div className="animate-fade-in-up-delay-4 mt-8 flex items-center justify-center gap-6 text-sm text-text-muted">
              <span className="flex items-center gap-1.5"><CheckCircle className="w-4 h-4 text-green-500" /> Free to join</span>
              <span className="flex items-center gap-1.5"><CheckCircle className="w-4 h-4 text-green-500" /> No hidden fees</span>
              <span className="flex items-center gap-1.5"><CheckCircle className="w-4 h-4 text-green-500" /> Fast payouts</span>
            </div>
          </div>

          {/* Dashboard preview */}
          <div className="mt-16 animate-fade-in-up-delay-4">
            <div className="relative max-w-5xl mx-auto">
              <div className="absolute inset-0 bg-gradient-to-t from-white via-transparent to-transparent z-10 pointer-events-none" />
              <div className="bg-gray-900 rounded-2xl shadow-2xl p-1 ring-1 ring-gray-800">
                <div className="flex items-center gap-1.5 px-4 py-3">
                  <div className="w-3 h-3 rounded-full bg-red-500" />
                  <div className="w-3 h-3 rounded-full bg-yellow-500" />
                  <div className="w-3 h-3 rounded-full bg-green-500" />
                  <span className="ml-3 text-xs text-gray-500">publisher.vertexmonetize.com/dashboard</span>
                </div>
                <div className="bg-gray-50 rounded-xl p-6 m-1">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                    {[
                      { label: "Today's Clicks", val: '1,284', color: 'text-black' },
                      { label: "Today's Earnings", val: '$64.20', color: 'text-primary' },
                      { label: 'Valid Clicks', val: '1,198', color: 'text-green-600' },
                      { label: 'Balance', val: '$847.50', color: 'text-primary' },
                    ].map((item, i) => (
                      <div key={i} className="bg-white rounded-lg p-4 border border-gray-100">
                        <p className="text-xs text-text-muted font-medium uppercase tracking-wider">{item.label}</p>
                        <p className={`text-2xl font-bold mt-1 ${item.color}`}>{item.val}</p>
                      </div>
                    ))}
                  </div>
                  <div className="bg-white rounded-lg border border-gray-100 p-4 h-40 flex items-end gap-1">
                    {[35, 50, 42, 65, 58, 75, 68, 82, 70, 90, 85, 95, 88, 78, 92, 86, 94, 98, 88, 93].map((h, i) => (
                      <div key={i} className="flex-1 bg-red-100 rounded-t" style={{ height: `${h}%` }}>
                        <div className="w-full bg-primary rounded-t h-full opacity-80" style={{ height: `${Math.min(100, h + 10)}%` }} />
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Stats Bar */}
      <section id="stats" className="py-12 bg-gray-900">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
            {stats.map((stat, i) => (
              <div key={i} className="text-center">
                <div className="inline-flex items-center justify-center w-10 h-10 rounded-lg bg-white/10 text-red-400 mb-3">
                  {stat.icon}
                </div>
                <div className="text-3xl font-bold text-white">{stat.value}</div>
                <div className="text-sm text-gray-400 mt-1">{stat.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="py-20 lg:py-28 bg-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <span className="text-sm font-semibold text-primary uppercase tracking-wider">Why Choose Us</span>
            <h2 className="mt-3 text-3xl sm:text-4xl font-bold text-black">
              Everything you need to <span className="gradient-text">maximize revenue</span>
            </h2>
            <p className="mt-4 text-text-secondary max-w-2xl mx-auto">
              Our platform provides powerful tools and features designed to help publishers
              earn more from their traffic.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {features.map((feature, i) => (
              <div
                key={i}
                className="group p-6 rounded-2xl border border-gray-100 hover:border-red-100 bg-white hover:bg-red-50/30 transition-all duration-300 hover:shadow-card-hover"
              >
                <div className="w-12 h-12 rounded-xl bg-red-50 group-hover:bg-primary text-primary group-hover:text-white flex items-center justify-center transition-all duration-300">
                  {feature.icon}
                </div>
                <h3 className="mt-4 text-lg font-semibold text-black">{feature.title}</h3>
                <p className="mt-2 text-text-secondary text-sm leading-relaxed">{feature.description}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section id="how-it-works" className="py-20 lg:py-28 bg-gray-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center mb-16">
            <span className="text-sm font-semibold text-primary uppercase tracking-wider">Get Started</span>
            <h2 className="mt-3 text-3xl sm:text-4xl font-bold text-black">
              Start earning in <span className="gradient-text">4 simple steps</span>
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
            {steps.map((step, i) => (
              <div key={i} className="relative">
                {i < steps.length - 1 && (
                  <div className="hidden lg:block absolute top-8 left-full w-full h-[2px] bg-gradient-to-r from-red-200 to-transparent" />
                )}
                <div className="text-5xl font-black text-red-100 mb-3">{step.step}</div>
                <h3 className="text-lg font-semibold text-black mb-2">{step.title}</h3>
                <p className="text-sm text-text-secondary leading-relaxed">{step.description}</p>
              </div>
            ))}
          </div>

          <div className="mt-16 text-center">
            <Link
              href="/publisher/auth?tab=signup"
              className="group inline-flex items-center gap-2 bg-primary hover:bg-primary-dark text-white font-semibold px-8 py-4 rounded-xl transition-all hover:shadow-glow-lg text-lg"
            >
              Create Free Account
              <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
            </Link>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 lg:py-28 animated-gradient">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
          <h2 className="text-3xl sm:text-4xl lg:text-5xl font-bold text-white leading-tight">
            Ready to turn your traffic
            <br />
            into revenue?
          </h2>
          <p className="mt-6 text-lg text-gray-300 max-w-2xl mx-auto">
            Join thousands of publishers already earning with vertexmonetize.
            Setup takes less than 5 minutes.
          </p>
          <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link
              href="/publisher/auth?tab=signup"
              className="group w-full sm:w-auto flex items-center justify-center gap-2 bg-white hover:bg-gray-100 text-black font-semibold px-8 py-4 rounded-xl transition-all text-lg"
            >
              Get Started Free
              <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
            </Link>
            <Link
              href="/publisher/auth"
              className="w-full sm:w-auto flex items-center justify-center gap-2 border-2 border-white/20 hover:border-white/50 text-white font-semibold px-8 py-4 rounded-xl transition-all text-lg"
            >
              Sign In
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 bg-gray-900 border-t border-gray-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 bg-primary rounded-lg flex items-center justify-center">
                <Zap className="w-3.5 h-3.5 text-white" />
              </div>
              <span className="text-sm font-semibold text-white">vertexmonetize</span>
            </div>
            <p className="text-sm text-gray-500">&copy; {new Date().getFullYear()} vertexmonetize. All rights reserved.</p>
            <div className="flex items-center gap-6">
              <a href="#features" className="text-sm text-gray-400 hover:text-white transition-colors">Features</a>
              <a href="#how-it-works" className="text-sm text-gray-400 hover:text-white transition-colors">How It Works</a>
              <Link href="/publisher/auth" className="text-sm text-gray-400 hover:text-white transition-colors">Publisher Login</Link>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}
