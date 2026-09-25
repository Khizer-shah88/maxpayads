'use client'

import PublisherId from '@/components/shared/PublisherId'

import { useState, useEffect, useCallback } from 'react'
import { MousePointer, CheckCircle, Users, DollarSign, TrendingUp, Wallet, Settings2, X, Plus, Trash2, Globe, Link, RefreshCw } from 'lucide-react'
import {
  Chart as ChartJS, ArcElement, Tooltip, Legend,
} from 'chart.js'
import { Doughnut } from 'react-chartjs-2'
import Sidebar from '@/components/shared/Sidebar'
import StatCard from '@/components/shared/StatCard'
import ClicksChart from '@/components/charts/ClicksChart'
import EarningsChart from '@/components/charts/EarningsChart'
import CountriesChart from '@/components/charts/CountriesChart'
import DataTable from '@/components/tables/DataTable'
import { adminApi, analyticsApi } from '@/lib/api'
import { useAuth } from '@/lib/hooks/useAuth'
import type { AdminDashboardStats, ClickTrend, TopCountry } from '@/types'

ChartJS.register(ArcElement, Tooltip, Legend)

export default function AdminDashboard() {
  const { initialize } = useAuth()
  const [stats, setStats] = useState<AdminDashboardStats | null>(null)
  const [trend, setTrend] = useState<ClickTrend[]>([])
  const [countries, setCountries] = useState<TopCountry[]>([])
  const [topPublishers, setTopPublishers] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [timeFilter, setTimeFilter] = useState<'daily' | 'week' | 'month' | 'lifetime'>('daily')
  const [clickFilter, setClickFilter] = useState<'unique' | 'valid'>('unique')

  // Domain setting state
  const [domainModal, setDomainModal] = useState(false)
  const [domainValue, setDomainValue] = useState('')
  const [savedDomain, setSavedDomain] = useState('')
  const [savingDomain, setSavingDomain] = useState(false)

  useEffect(() => { initialize() }, [])

  const filterDays = timeFilter === 'daily' ? 1 : timeFilter === 'week' ? 7 : timeFilter === 'month' ? 30 : undefined
  const trendPeriod = timeFilter === 'daily' ? '1d' : timeFilter === 'week' ? '7d' : timeFilter === 'month' ? '30d' : '90d'

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const dashParams: { days?: number } = {}
      const distParams: { days?: number } = {}
      if (filterDays !== undefined) {
        dashParams.days = filterDays
        distParams.days = filterDays
      }
      const [dashRes, trendRes, countriesRes, pubRes, domainRes, distRes] = await Promise.all([
        adminApi.getDashboard(dashParams),
        analyticsApi.getClicksTrend(trendPeriod),
        analyticsApi.getTopCountries(filterDays || 3650),
        analyticsApi.getTopPublishers(filterDays || 3650),
        adminApi.getDomain(),
        analyticsApi.getDistribution(distParams),
      ])
      setStats(dashRes.data.stats)
      setTrend(trendRes.data.trend)
      setCountries(countriesRes.data.countries)
      setTopPublishers(pubRes.data.publishers)
      setSavedDomain(domainRes.data.domain || '')
      setDomainValue(domainRes.data.domain || '')
      if (distRes.data) {
        setOsItems(distRes.data.os_distribution || [])
        setDeviceItems(distRes.data.device_distribution || [])
      }
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }, [filterDays, trendPeriod])

  useEffect(() => { loadData() }, [loadData])

  const publisherColumns = [
    { key: 'name', label: 'Publisher', render: (r: any) => (
      <div className="flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-lg bg-gray-100 flex items-center justify-center text-xs font-bold text-gray-600">
          {(r.name || '?').charAt(0).toUpperCase()}
        </div>
        <span className="font-medium text-gray-900">{r.name}<PublisherId publicId={r.public_id} publisherId={r.id || r.publisher_id} /></span>
      </div>
    )},
    { key: 'email', label: 'Email', render: (r: any) => <span className="text-gray-500 text-xs">{r.email}</span> },
    { key: 'total_clicks', label: 'Clicks', render: (r: any) => <span className="font-mono font-semibold">{(r.total_clicks ?? 0).toLocaleString()}</span> },
    { key: 'total_earnings', label: 'Earnings', render: (r: any) => <span className="text-emerald-600 font-mono font-bold">${(r.total_earnings ?? 0).toFixed(4)}</span> },
  ]

  // --- Pie Chart Data ---
  const OS_COLORS: Record<string, string> = { Windows: '#3B82F6', Mac: '#6B7280', 'Mac OS X': '#6B7280', macOS: '#6B7280', Android: '#10B981', iOS: '#F97316', Linux: '#8B5CF6' }
  const DEVICE_COLORS_MAP: Record<string, string> = { desktop: '#1E293B', Desktop: '#1E293B', mobile: '#10B981', Mobile: '#10B981', tablet: '#F59E0B', Tablet: '#F59E0B' }
  const [osItems, setOsItems] = useState<{label: string; value: number; color: string}[]>([])
  const [deviceItems, setDeviceItems] = useState<{label: string; value: number; color: string}[]>([])

  const buildChartData = (items: typeof osItems) => ({
    labels: items.map(i => i.label),
    datasets: [{
      data: items.map(i => i.value),
      backgroundColor: items.map(i => i.color),
      borderWidth: 0,
      cutout: '68%',
      hoverOffset: 6,
    }],
  })

  const pieOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'bottom' as const,
        labels: {
          color: '#6B7280',
          font: { size: 12, weight: 500 as const },
          boxWidth: 12,
          boxHeight: 12,
          padding: 16,
          usePointStyle: true,
          pointStyle: 'circle' as const,
        },
      },
      tooltip: {
        backgroundColor: '#111827',
        titleColor: '#fff',
        bodyColor: '#D1D5DB',
        padding: 12,
        cornerRadius: 10,
        displayColors: true,
        boxPadding: 4,
        callbacks: {
          label: (ctx: any) => {
            const value = ctx.raw as number
            const total = (ctx.dataset.data as number[]).reduce((a: number, b: number) => a + b, 0)
            const pct = ((value / total) * 100).toFixed(1)
            return ` ${ctx.label}: ${value.toLocaleString()} (${pct}%)`
          },
        },
      },
    },
  }

  return (
    <div className="flex min-h-screen bg-[#f8f9fb]">
      <Sidebar />
      <div className="flex-1 lg:ml-64 p-6 lg:p-8 min-w-0 overflow-x-hidden">
        {/* Header */}
        <div className="mb-8 pt-12 lg:pt-0 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
            <p className="text-gray-400 text-sm mt-0.5">Platform overview and analytics</p>
          </div>
          <div className="flex items-center gap-2.5">
            <button onClick={() => loadData()}
              className="p-2.5 rounded-xl border border-gray-200 text-gray-400 hover:text-gray-600 hover:bg-white transition-colors" title="Refresh">
              <RefreshCw size={16} />
            </button>
            <button onClick={() => { setDomainValue(savedDomain); setDomainModal(true) }}
              className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium border transition-all ${
                savedDomain
                  ? 'bg-emerald-50 border-emerald-200 text-emerald-700 hover:bg-emerald-100'
                  : 'bg-amber-50 border-amber-200 text-amber-700 hover:bg-amber-100'
              }`}>
              <Link size={14} />
              {savedDomain ? savedDomain.replace(/^https?:\/\//, '') : 'Set Domain'}
            </button>
            <div className="flex bg-gray-100 rounded-xl p-0.5">
              {([['daily', 'Daily'], ['week', 'Week'], ['month', 'Month'], ['lifetime', 'Lifetime']] as const).map(([key, label]) => (
                <button key={key} onClick={() => setTimeFilter(key)}
                  className={`px-4 py-2 rounded-lg text-sm font-semibold transition-all ${
                    timeFilter === key ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
                  }`}>
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Stats Row 1 */}
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 mb-5">
          <StatCard title={`${timeFilter === 'daily' ? "Today's" : timeFilter === 'week' ? 'Weekly' : timeFilter === 'month' ? 'Monthly' : 'Total'} Clicks`} value={stats?.total_clicks || 0} icon={<MousePointer size={20} />} color="primary" loading={loading} />
          <StatCard title={`${timeFilter === 'daily' ? "Today's" : timeFilter === 'week' ? 'Weekly' : timeFilter === 'month' ? 'Monthly' : 'Total'} Valid Clicks`} value={stats?.valid_clicks || 0} icon={<CheckCircle size={20} />} color="success" loading={loading} />
          <StatCard title="Total Publishers" value={stats?.total_publishers || 0} icon={<Users size={20} />} color="secondary" loading={loading} />
          <StatCard title={`${timeFilter === 'daily' ? "Today's" : timeFilter === 'week' ? 'Weekly' : timeFilter === 'month' ? 'Monthly' : 'Total'} Earnings`} value={`$${(stats?.total_earnings || 0).toFixed(2)}`} icon={<DollarSign size={20} />} color="warning" loading={loading} />
        </div>

        {/* Stats Row 2 */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
          <StatCard title="Fraud Rate" value={`${stats?.fraud_rate || 0}%`} icon={<TrendingUp size={20} />} color="success" loading={loading} />
          <StatCard title="Active Publishers" value={stats?.active_publishers || 0} icon={<Users size={20} />} color="primary" loading={loading} />
          <StatCard title="Pending Withdrawals" value={stats?.pending_withdrawals || 0} icon={<Wallet size={20} />} color="warning" loading={loading} />
        </div>

        {/* Click Performance */}
        <div className="bg-white rounded-2xl border border-gray-100 p-6 mb-6">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-base font-semibold text-gray-900">Click Performance</h2>
            <div className="flex bg-gray-100 rounded-xl p-0.5">
              {([['unique', 'Unique'], ['valid', 'Valid']] as const).map(([key, label]) => (
                <button key={key} onClick={() => setClickFilter(key)}
                  className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                    clickFilter === key ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
                  }`}>
                  {label}
                </button>
              ))}
            </div>
          </div>
          <ClicksChart data={trend} loading={loading} filter={clickFilter} />
        </div>

        {/* Charts Row */}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 mb-6">
          <div className="bg-white rounded-2xl border border-gray-100 p-6">
            <h2 className="text-base font-semibold text-gray-900 mb-4">Daily Earnings</h2>
            <EarningsChart data={trend} loading={loading} />
          </div>
          <div className="bg-white rounded-2xl border border-gray-100 p-6">
            <h2 className="text-base font-semibold text-gray-900 mb-4">Traffic by Country</h2>
            <CountriesChart data={countries} loading={loading} />
          </div>
        </div>

        {/* Top Publishers */}
        <div className="bg-white rounded-2xl border border-gray-100 p-6 mb-6">
          <h2 className="text-base font-semibold text-gray-900 mb-4">Top Publishers <span className="text-gray-400 font-normal text-sm">({timeFilter === 'daily' ? 'Today' : timeFilter === 'week' ? '7 days' : timeFilter === 'month' ? '30 days' : 'All time'})</span></h2>
          <DataTable columns={publisherColumns} data={topPublishers} loading={loading} emptyMessage="No publisher data yet" />
        </div>

        {/* Pie Charts */}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          <div className="bg-white rounded-2xl border border-gray-100 p-6">
            <h2 className="text-base font-semibold text-gray-900 mb-6">OS Distribution</h2>
            <div style={{ height: '320px' }}>
              <Doughnut data={buildChartData(osItems)} options={pieOptions} />
            </div>
          </div>
          <div className="bg-white rounded-2xl border border-gray-100 p-6">
            <h2 className="text-base font-semibold text-gray-900 mb-6">Device Type</h2>
            <div style={{ height: '320px' }}>
              <Doughnut data={buildChartData(deviceItems)} options={pieOptions} />
            </div>
          </div>
        </div>

        {/* Domain Setting Modal */}
        {domainModal && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setDomainModal(false)}>
            <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-2xl border border-gray-100" onClick={e => e.stopPropagation()}>
              <div className="flex items-center gap-3 mb-5">
                <div className="w-11 h-11 rounded-xl bg-primary/10 flex items-center justify-center">
                  <Globe size={20} className="text-primary" />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-gray-900">Platform Domain</h3>
                  <p className="text-xs text-gray-400">Used in publisher embed codes & smart links</p>
                </div>
              </div>
              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-700 mb-1.5">Domain URL</label>
                <input
                  value={domainValue}
                  onChange={e => setDomainValue(e.target.value)}
                  placeholder="https://yourdomain.com"
                  className="w-full px-4 py-3 border border-gray-200 rounded-xl text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary text-sm"
                />
                <p className="text-xs text-gray-400 mt-1.5">Include protocol (https://). Leave empty to auto-detect.</p>
              </div>
              {savedDomain && (
                <div className="mb-4 p-3 bg-emerald-50 rounded-xl border border-emerald-200">
                  <p className="text-xs text-emerald-700">Current: <span className="font-mono font-semibold">{savedDomain}</span></p>
                </div>
              )}
              <div className="flex gap-3">
                <button
                  onClick={async () => {
                    setSavingDomain(true)
                    try {
                      const res = await adminApi.setDomain(domainValue)
                      setSavedDomain(res.data.domain)
                      setDomainModal(false)
                    } catch { /* ignore */ }
                    finally { setSavingDomain(false) }
                  }}
                  disabled={savingDomain}
                  className="flex-1 bg-primary hover:bg-primary-dark text-white py-3 rounded-xl text-sm font-semibold flex items-center justify-center disabled:bg-gray-300 transition-colors">
                  {savingDomain ? 'Saving...' : 'Save Domain'}
                </button>
                <button onClick={() => setDomainModal(false)}
                  className="flex-1 py-3 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50 transition-colors">
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
