'use client'

import { useState, useEffect, useCallback } from 'react'
import { MousePointer, DollarSign, CheckCircle, Wallet, TrendingUp, BarChart3, RefreshCw } from 'lucide-react'
import Link from 'next/link'
import PublisherSidebar from '@/components/shared/PublisherSidebar'
import StatCard from '@/components/shared/StatCard'
import ClicksChart from '@/components/charts/ClicksChart'
import { publisherApi } from '@/lib/api'
import { getUser } from '@/lib/auth'
import { useAuth } from '@/lib/hooks/useAuth'
import type { PublisherDashboardStats, ClickTrend } from '@/types'

const AUTO_REFRESH_INTERVAL = 30_000

export default function PublisherDashboard() {
  const { initialize } = useAuth()
  const [stats, setStats] = useState<PublisherDashboardStats | null>(null)
  const [trend, setTrend] = useState<ClickTrend[]>([])
  const [publisher, setPublisher] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)
  const user = getUser()

  useEffect(() => { initialize() }, [])

  const fetchData = useCallback(async (showLoader = false) => {
    if (showLoader) setLoading(true)
    try {
      const [dashRes, trendRes] = await Promise.all([
        publisherApi.getDashboard(),
        publisherApi.getClicksTrend('7d'),
      ])
      setStats(dashRes.data.stats)
      setPublisher(dashRes.data.publisher)
      setTrend(trendRes.data.trend)
      setLastRefresh(new Date())
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }, [user?.id])

  useEffect(() => { fetchData(true) }, [fetchData])

  useEffect(() => {
    if (!autoRefresh) return
    const interval = setInterval(() => fetchData(false), AUTO_REFRESH_INTERVAL)
    return () => clearInterval(interval)
  }, [autoRefresh, fetchData])

  return (
    <div className="flex min-h-screen bg-[#f8f9fb]">
      <PublisherSidebar />
      <div className="flex-1 lg:ml-64 p-6 lg:p-8">
        {/* Pending approval banner */}
        {publisher?.status === 'pending' && (
          <div className="mb-6 p-4 rounded-2xl border border-amber-200 bg-amber-50 flex items-center gap-3">
            <span className="text-amber-600 text-xl">&#9203;</span>
            <div>
              <p className="text-amber-800 font-semibold">Account pending approval</p>
              <p className="text-amber-700 text-sm">Your account is under review. Ad serving and earnings will begin once approved by an admin.</p>
            </div>
          </div>
        )}

        <div className="mb-8 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pt-12 lg:pt-0">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              Welcome back, <span className="text-primary">{publisher?.name || user?.name || 'Publisher'}</span>!
            </h1>
            <p className="text-gray-400 text-sm mt-0.5">Here&apos;s your performance overview</p>
          </div>
          <div className="flex items-center gap-2.5">
            <button onClick={() => fetchData(false)}
              className="p-2.5 rounded-xl border border-gray-200 text-gray-400 hover:text-gray-600 hover:bg-white transition-colors" title="Refresh now">
              <RefreshCw className="w-4 h-4" />
            </button>
            <button onClick={() => setAutoRefresh(!autoRefresh)}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-medium transition-all ${
                autoRefresh ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'border border-gray-200 text-gray-500 hover:bg-white'
              }`}>
              <span className={`w-1.5 h-1.5 rounded-full ${autoRefresh ? 'bg-emerald-500 animate-pulse' : 'bg-gray-300'}`} />
              Auto-refresh {autoRefresh ? 'ON' : 'OFF'}
            </button>
            {lastRefresh && (
              <span className="text-xs text-gray-400">{lastRefresh.toLocaleTimeString()}</span>
            )}
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 mb-5">
          <StatCard title="Today's Clicks" value={stats?.today_clicks || 0} icon={<MousePointer size={20} />} color="secondary" loading={loading} />
          <StatCard title="Today's Earnings" value={`$${(stats?.today_earnings || 0).toFixed(4)}`} icon={<DollarSign size={20} />} color="primary" loading={loading} />
          <StatCard title="Total Clicks" value={stats?.total_clicks || 0} icon={<TrendingUp size={20} />} color="secondary" loading={loading} />
          <StatCard title="Available Balance" value={`$${(stats?.balance || 0).toFixed(2)}`} icon={<Wallet size={20} />} color="warning" loading={loading} />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
          <StatCard title="Valid Clicks" value={stats?.valid_clicks || 0} icon={<CheckCircle size={20} />} color="success" loading={loading} />
          <StatCard title="This Month Clicks" value={stats?.this_month_clicks || 0} icon={<BarChart3 size={20} />} color="secondary" loading={loading} />
          <StatCard title="Total Earnings" value={`$${(stats?.total_earnings || 0).toFixed(2)}`} icon={<DollarSign size={20} />} color="success" loading={loading} />
        </div>

        {/* Quick Actions */}
        <div className="flex gap-3 mb-6">
          <Link href="/publisher/withdrawals"
            className="bg-primary hover:bg-primary-dark text-white px-6 py-3 rounded-xl text-sm font-semibold flex items-center gap-2 transition-colors">
            <Wallet size={16} /> Request Withdrawal
          </Link>
          <Link href="/publisher/ad-units"
            className="px-6 py-3 rounded-xl text-sm font-medium flex items-center gap-2 border border-gray-200 text-gray-700 hover:bg-white transition-colors">
            Get Embed Code
          </Link>
        </div>

        {/* Chart */}
        <div className="bg-white rounded-2xl border border-gray-100 p-6">
          <h2 className="text-base font-semibold text-gray-900 mb-4">Click Performance (Last 7 Days)</h2>
          <ClicksChart data={trend} loading={loading} />
        </div>
      </div>
    </div>
  )
}
