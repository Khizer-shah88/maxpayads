'use client'

import { useState, useEffect, useCallback, useMemo } from 'react'
import { Download, MousePointer, CheckCircle, XCircle, DollarSign, BarChart3 } from 'lucide-react'
import { toast } from 'sonner'
import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement,
  BarElement, ArcElement, Title, Tooltip, Legend, Filler,
} from 'chart.js'
import { Bar, Pie, Doughnut } from 'react-chartjs-2'
import Sidebar from '@/components/shared/Sidebar'
import DataTable from '@/components/tables/DataTable'
import { StatusBadge } from '@/components/ui/badge'
import { clickApi, adminApi, analyticsApi, downloadBlob } from '@/lib/api'
import { useAuth } from '@/lib/hooks/useAuth'
import type { Click } from '@/types'
import { format } from 'date-fns'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, BarElement, ArcElement, Title, Tooltip, Legend, Filler)

export default function StatisticsPage() {
  const { initialize } = useAuth()
  const [clicks, setClicks] = useState<Click[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [publishers, setPublishers] = useState<{id: string; name: string; email: string}[]>([])
  const [websites, setWebsites] = useState<{id: string; domain: string; publisher_id: string}[]>([])
  const [showCharts, setShowCharts] = useState(true)
  const [filtersReady, setFiltersReady] = useState(false)
  const [aggStats, setAggStats] = useState<{total: number; valid: number; invalid: number; earnings: number} | null>(null)
  const [aggTrend, setAggTrend] = useState<{labels: string[]; valid: number[]; invalid: number[]; earnings: number[]}>({labels: [], valid: [], invalid: [], earnings: []})
  const [aggDist, setAggDist] = useState<{devices?: {name: string; value: number}[]; os?: {name: string; value: number}[]; browsers?: {name: string; value: number}[]; countries?: {name: string; value: number}[]} | null>(null)
  const [filters, setFilters] = useState({
    status: '', country_code: '', device_type: '', os: '', browser: '',
    publisher_id: '', website_id: '',
    date_from: '', date_to: '',
  })

  useEffect(() => {
    // Default: show today's stats (date_to = today, backend makes it inclusive of full day)
    const today = new Date().toISOString().split('T')[0]
    setFilters(f => ({ ...f, date_from: today, date_to: today }))
    setFiltersReady(true)
  }, [])

  useEffect(() => { initialize() }, [])

  useEffect(() => {
    const loadOptions = async () => {
      try {
        const [pubRes, webRes] = await Promise.all([
          adminApi.getPublishers({ limit: 200 }),
          adminApi.getWebsites(),
        ])
        setPublishers(pubRes.data.publishers?.map((p: any) => ({ id: p.id, name: p.name, email: p.email })) || [])
        setWebsites(webRes.data.websites?.map((w: any) => ({ id: w.id, domain: w.domain, publisher_id: w.publisher_id })) || [])
      } catch {}
    }
    loadOptions()
  }, [])

  const loadClicks = useCallback(async () => {
    if (!filtersReady) return
    setLoading(true)
    try {
      const params: any = { page, limit: 50 }
      if (filters.publisher_id) params.publisher_id = filters.publisher_id
      if (filters.website_id) params.website_id = filters.website_id
      if (filters.status) params.status = filters.status
      if (filters.country_code) params.country_code = filters.country_code
      if (filters.device_type) params.device_type = filters.device_type
      if (filters.os) params.os = filters.os
      if (filters.browser) params.browser = filters.browser
      if (filters.date_from) params.date_from = filters.date_from
      if (filters.date_to) params.date_to = filters.date_to
      const [res, aggRes] = await Promise.all([
        clickApi.getClicks(params),
        analyticsApi.getClickStats(params).catch(() => null),
      ])
      setClicks(res.data.clicks)
      setTotal(res.data.total)
      if (aggRes?.data) {
        setAggStats(aggRes.data.totals)
        const trend = aggRes.data.daily_trend || []
        setAggTrend({
          labels: trend.map((t: any) => t.date),
          valid: trend.map((t: any) => t.valid),
          invalid: trend.map((t: any) => t.invalid),
          earnings: trend.map((t: any) => t.earnings),
        })
        setAggDist(aggRes.data.distribution || null)
      } else {
        setAggDist(null)
      }
    } catch { toast.error('Failed to load statistics') }
    finally { setLoading(false) }
  }, [page, filters, filtersReady])

  useEffect(() => { loadClicks() }, [loadClicks])

  const handleExport = async () => {
    try {
      const res = await clickApi.exportCSV(filters)
      downloadBlob(res.data, `statistics_${Date.now()}.csv`)
      toast.success('CSV exported')
    } catch { toast.error('Export failed') }
  }

  const columns = [
    { key: 'timestamp', label: 'Time', render: (c: Click) => <span className="text-[11px] font-mono text-gray-600">{format(new Date(c.timestamp), 'MM/dd HH:mm')}</span> },
    { key: 'publisher_id', label: 'Publisher', render: (c: Click) => {
      const pub = publishers.find(p => p.id === c.publisher_id)
      return <span className="text-[11px] font-medium text-gray-600">{pub ? pub.name : c.publisher_id.slice(-8)}</span>
    }},
    { key: 'website', label: 'Website', render: (c: Click) => {
      const domain = (c as any).website_domain || c.website_id
      return domain ? <span className="text-[11px] text-blue-600 font-medium truncate max-w-[100px] block">{domain}</span> : <span className="text-gray-300 text-[11px]">—</span>
    }},
    { key: 'referrer', label: 'Referrer', render: (c: Click) => {
      if (!c.referrer) return <span className="text-gray-300 text-[11px]">—</span>
      try {
        const url = new URL(c.referrer)
        return <a href={c.referrer} target="_blank" rel="noreferrer" className="text-[11px] text-blue-500 hover:underline truncate max-w-[100px] block" title={c.referrer}>{url.hostname}</a>
      } catch {
        return <span className="text-[11px] text-gray-500 truncate max-w-[100px] block" title={c.referrer}>{c.referrer}</span>
      }
    }},
    { key: 'ip_address', label: 'IP', render: (c: Click) => <span className="font-mono text-[11px] text-gray-600">{c.ip_address}</span> },
    { key: 'country_code', label: 'Country', render: (c: Click) => <span className="text-[11px]">{c.country_code || '—'}</span> },
    { key: 'device_type', label: 'Device', render: (c: Click) => <span className="text-[11px]">{c.device_type}</span> },
    { key: 'os', label: 'OS', render: (c: Click) => <span className="text-[11px] text-gray-500">{c.os || '—'}</span> },
    { key: 'browser', label: 'Browser', render: (c: Click) => <span className="text-[11px] text-gray-500">{c.browser || '—'}</span> },
    { key: 'cpc', label: 'CPC', render: (c: Click) => <span className="font-mono text-[11px]">${c.cpc.toFixed(4)}</span> },
    { key: 'earnings', label: 'Earnings', render: (c: Click) => <span className="font-mono text-[11px] text-red-600 font-semibold">${c.earnings.toFixed(4)}</span> },
    { key: 'status', label: 'Status', render: (c: Click) => <span className={`text-[11px] font-medium ${c.status === 'valid' ? 'text-emerald-600' : c.status === 'invalid' ? 'text-red-500' : 'text-amber-500'}`}>{c.status}</span> },
    { key: 'fraud_reason', label: 'Reason', render: (c: Click) => c.fraud_reason ? <span className="text-red-500 text-[11px]">{c.fraud_reason}</span> : <span className="text-gray-300 text-[11px]">—</span> },
  ]

  // --- Stats (use aggregate data from backend) ---
  const stats = useMemo(() => {
    if (aggStats) {
      return { valid: aggStats.valid, invalid: aggStats.invalid, pending: aggStats.total - aggStats.valid - aggStats.invalid, earnings: aggStats.earnings }
    }
    const v = clicks.filter(c => c.status === 'valid').length
    const inv = clicks.filter(c => c.status === 'invalid').length
    const p = clicks.filter(c => c.status === 'pending').length
    const e = clicks.reduce((s, c) => s + c.earnings, 0)
    return { valid: v, invalid: inv, pending: p, earnings: e }
  }, [clicks, aggStats])

  // --- Daily trend (use aggregate data from backend) ---
  const dailyTrend = useMemo(() => {
    if (aggTrend.labels.length > 0) return aggTrend
    const map: Record<string, { valid: number; invalid: number; earnings: number }> = {}
    clicks.forEach(c => {
      const d = format(new Date(c.timestamp), 'MM/dd')
      if (!map[d]) map[d] = { valid: 0, invalid: 0, earnings: 0 }
      if (c.status === 'valid') map[d].valid++
      if (c.status === 'invalid') map[d].invalid++
      map[d].earnings += c.earnings
    })
    const sorted = Object.entries(map).sort((a, b) => a[0].localeCompare(b[0]))
    return { labels: sorted.map(([d]) => d), valid: sorted.map(([, v]) => v.valid), invalid: sorted.map(([, v]) => v.invalid), earnings: sorted.map(([, v]) => v.earnings) }
  }, [clicks, aggTrend])

  // --- Pie data helpers ---
  const cap = (s: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s)

  const buildPie = (map: Record<string, number>, colors: string[]) => {
    const entries = Object.entries(map).sort((a, b) => b[1] - a[1]).slice(0, 6)
    return {
      labels: entries.map(([k]) => k),
      datasets: [{ data: entries.map(([, v]) => v), backgroundColor: colors.slice(0, entries.length), borderColor: '#fff', borderWidth: 2 }],
    }
  }

  // Build a pie from the backend's full-set distribution list ([{name, value}]).
  const buildPieFromList = (list: { name: string; value: number }[] | undefined, colors: string[], capitalize = false) => {
    const entries = (list || []).slice(0, colors.length)
    return {
      labels: entries.map(e => (capitalize ? cap(e.name) : e.name)),
      datasets: [{ data: entries.map(e => e.value), backgroundColor: colors.slice(0, entries.length), borderColor: '#fff', borderWidth: 2 }],
    }
  }

  const statusPie = useMemo(() => buildPie(
    { Valid: stats.valid, Invalid: stats.invalid, Pending: stats.pending },
    ['#16A34A', '#DC2626', '#F59E0B']
  ), [stats])

  // The four distribution pies prefer the backend aggregate (full filtered set);
  // they fall back to per-page counts only if the aggregate call failed.
  const devicePie = useMemo(() => {
    const colors = ['#1E293B', '#10B981', '#F59E0B', '#3B82F6', '#D1D5DB']
    if (aggDist?.devices?.length) return buildPieFromList(aggDist.devices, colors, true)
    const m: Record<string, number> = {}
    clicks.forEach(c => { const d = c.device_type || 'unknown'; m[cap(d)] = (m[cap(d)] || 0) + 1 })
    return buildPie(m, colors)
  }, [clicks, aggDist])

  const osPie = useMemo(() => {
    const colors = ['#3B82F6', '#6B7280', '#10B981', '#F97316', '#8B5CF6', '#D1D5DB']
    if (aggDist?.os?.length) return buildPieFromList(aggDist.os, colors)
    const m: Record<string, number> = {}
    clicks.forEach(c => { const o = c.os || 'Unknown'; m[o] = (m[o] || 0) + 1 })
    return buildPie(m, colors)
  }, [clicks, aggDist])

  const browserPie = useMemo(() => {
    const colors = ['#DC2626', '#3B82F6', '#F59E0B', '#10B981', '#8B5CF6', '#D1D5DB']
    if (aggDist?.browsers?.length) return buildPieFromList(aggDist.browsers, colors)
    const m: Record<string, number> = {}
    clicks.forEach(c => { const b = c.browser || 'Unknown'; m[b] = (m[b] || 0) + 1 })
    return buildPie(m, colors)
  }, [clicks, aggDist])

  const countryPie = useMemo(() => {
    const colors = ['#3B82F6', '#10B981', '#F59E0B', '#DC2626', '#8B5CF6', '#EC4899', '#06B6D4', '#F97316']
    if (aggDist?.countries?.length) return buildPieFromList(aggDist.countries, colors)
    const m: Record<string, number> = {}
    clicks.forEach(c => { const cc = c.country_code || 'N/A'; m[cc] = (m[cc] || 0) + 1 })
    return buildPie(m, colors)
  }, [clicks, aggDist])

  // --- Chart options ---
  const tinyBar: any = {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { labels: { color: '#6B7280', font: { size: 10 }, boxWidth: 8, padding: 6 } }, tooltip: { backgroundColor: '#111827', titleColor: '#fff', bodyColor: '#D1D5DB', padding: 8, cornerRadius: 6 } },
    scales: { x: { grid: { display: false }, ticks: { color: '#9CA3AF', font: { size: 9 } } }, y: { grid: { color: '#F3F4F6' }, ticks: { color: '#9CA3AF', font: { size: 9 } } } },
  }
  const stackedBar: any = { ...tinyBar, scales: { x: { ...tinyBar.scales.x, stacked: true }, y: { ...tinyBar.scales.y, stacked: true } } }
  const earningsBar: any = { ...tinyBar, plugins: { ...tinyBar.plugins, legend: { display: false } }, scales: { ...tinyBar.scales, y: { ...tinyBar.scales.y, ticks: { ...tinyBar.scales.y.ticks, callback: (v: any) => `$${v}` } } } }
  const pctLabel = (ctx: any) => {
    const v = ctx.raw as number; const t = (ctx.dataset.data as number[]).reduce((a: number, b: number) => a + b, 0)
    return ` ${ctx.label}: ${v.toLocaleString()} (${t ? ((v / t) * 100).toFixed(1) : 0}%)`
  }
  const tinyPie: any = {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { position: 'right', labels: { color: '#6B7280', font: { size: 9 }, boxWidth: 8, boxHeight: 8, padding: 5, usePointStyle: true, pointStyle: 'circle' } }, tooltip: { backgroundColor: '#111827', titleColor: '#fff', bodyColor: '#D1D5DB', padding: 8, cornerRadius: 6, callbacks: { label: pctLabel } } },
  }
  const tinyDoughnut: any = { ...tinyPie, plugins: { ...tinyPie.plugins } }

  const countryPieOpts: any = {
    responsive: true, maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'right',
        labels: {
          color: '#6B7280', font: { size: 9 }, boxWidth: 8, boxHeight: 8, padding: 5,
          usePointStyle: true, pointStyle: 'circle',
          generateLabels: (chart: any) => {
            const dataset = chart.data.datasets[0]
            const total = dataset.data.reduce((a: number, b: number) => a + b, 0)
            return chart.data.labels.map((label: string, i: number) => {
              const value = dataset.data[i]
              const pct = total > 0 ? ((value / total) * 100).toFixed(1) : '0'
              return {
                text: `${label} ${pct}%`,
                fillStyle: dataset.backgroundColor[i],
                strokeStyle: '#fff',
                lineWidth: 2,
                hidden: false,
                index: i,
                pointStyle: 'circle',
              }
            })
          },
        },
      },
      tooltip: {
        backgroundColor: '#111827', titleColor: '#fff', bodyColor: '#D1D5DB', padding: 8, cornerRadius: 6,
        callbacks: { label: pctLabel },
      },
    },
  }

  const sel = "px-2 py-1.5 border border-gray-200 rounded-lg text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary text-xs"

  return (
    <div className="flex min-h-screen bg-[#f8f9fb]" style={{ zoom: 0.9 }}>
      <Sidebar />
      <div className="flex-1 lg:ml-64 p-3 lg:p-4">
        {/* Header */}
        <div className="flex items-center justify-between mb-2 pt-12 lg:pt-0">
          <div>
            <h1 className="text-xl font-bold text-gray-900">Statistics</h1>
            <p className="text-gray-400 text-xs">{total.toLocaleString()} total clicks</p>
          </div>
          <button onClick={handleExport} className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium border border-gray-200 text-gray-700 hover:bg-gray-50">
            <Download size={14} /> Export CSV
          </button>
        </div>

        {/* Stat Cards */}
        <div className="grid grid-cols-4 gap-2 mb-2">
          {[
            { icon: <MousePointer size={14} />, color: 'text-primary', label: 'Total', value: total.toLocaleString(), valueColor: 'text-gray-900' },
            { icon: <CheckCircle size={14} />, color: 'text-emerald-500', label: 'Valid', value: stats.valid.toLocaleString(), valueColor: 'text-emerald-600' },
            { icon: <XCircle size={14} />, color: 'text-red-500', label: 'Invalid', value: stats.invalid.toLocaleString(), valueColor: 'text-red-600' },
            { icon: <DollarSign size={14} />, color: 'text-amber-500', label: 'Earnings', value: `$${stats.earnings.toFixed(4)}`, valueColor: 'text-gray-900' },
          ].map((s, i) => (
            <div key={i} className="bg-white rounded-xl border border-gray-100 px-3 py-2.5">
              <div className="flex items-center gap-1.5"><span className={s.color}>{s.icon}</span><span className="text-[10px] font-medium text-gray-400 uppercase tracking-wide">{s.label}</span></div>
              <p className={`text-lg font-bold ${s.valueColor} mt-0.5`}>{s.value}</p>
            </div>
          ))}
        </div>

        {/* Filters */}
        <div className="bg-white rounded-xl border border-gray-100 px-3 py-2 mb-2">
          <div className="flex flex-wrap gap-2 items-center">
            <input type="date" value={filters.date_from} onChange={e => setFilters(p => ({...p, date_from: e.target.value}))} className={sel} />
            <span className="text-gray-300 text-xs">to</span>
            <input type="date" value={filters.date_to} onChange={e => setFilters(p => ({...p, date_to: e.target.value}))} className={sel} />
            <select value={filters.publisher_id} onChange={e => setFilters(p => ({...p, publisher_id: e.target.value, website_id: ''}))} className={sel}>
              <option value="">All Publishers</option>
              {publishers.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            <select value={filters.website_id} onChange={e => setFilters(p => ({...p, website_id: e.target.value}))} className={sel}>
              <option value="">All Websites</option>
              {(filters.publisher_id ? websites.filter(w => w.publisher_id === filters.publisher_id) : websites).map(w => <option key={w.id} value={w.id}>{w.domain}</option>)}
            </select>
            <select value={filters.status} onChange={e => setFilters(p => ({...p, status: e.target.value}))} className={sel}>
              <option value="">All Status</option>
              <option value="valid">Valid</option>
              <option value="invalid">Invalid</option>
              <option value="pending">Pending</option>
            </select>
            <select value={filters.device_type} onChange={e => setFilters(p => ({...p, device_type: e.target.value}))} className={sel}>
              <option value="">All Devices</option>
              <option value="desktop">Desktop</option>
              <option value="mobile">Mobile</option>
              <option value="tablet">Tablet</option>
            </select>
            <select value={filters.os} onChange={e => setFilters(p => ({...p, os: e.target.value}))} className={sel}>
              <option value="">All OS</option>
              <option value="Windows">Windows</option>
              <option value="macOS">macOS</option>
              <option value="iOS">iOS</option>
              <option value="Android">Android</option>
              <option value="Linux">Linux</option>
              <option value="Chrome OS">Chrome OS</option>
            </select>
            <select value={filters.browser} onChange={e => setFilters(p => ({...p, browser: e.target.value}))} className={sel}>
              <option value="">All Browsers</option>
              <option value="Chrome">Chrome</option>
              <option value="Safari">Safari</option>
              <option value="Firefox">Firefox</option>
              <option value="Edge">Edge</option>
              <option value="Opera">Opera</option>
              <option value="Samsung">Samsung</option>
            </select>
            <input value={filters.country_code} onChange={e => setFilters(p => ({...p, country_code: e.target.value.toUpperCase()}))}
              placeholder="CC" maxLength={2} className={`${sel} w-14`} />
            <button onClick={() => { setPage(1); loadClicks() }} className="bg-primary hover:bg-primary-dark text-white px-3 py-1.5 rounded-lg text-xs font-medium">
              Apply
            </button>
            <button onClick={() => { const today = new Date().toISOString().split('T')[0]; setFilters(p => ({...p, date_from: today, date_to: today})); setPage(1) }}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium ${filters.date_from === new Date().toISOString().split('T')[0] && filters.date_to === new Date().toISOString().split('T')[0] ? 'bg-primary text-white' : 'border border-gray-200 text-gray-600 hover:bg-gray-50'}`}>
              Today
            </button>
            <button onClick={() => { setFilters(p => ({...p, date_from: '', date_to: ''})); setPage(1) }} className="px-3 py-1.5 rounded-lg text-xs font-medium border border-gray-200 text-gray-600 hover:bg-gray-50">
              Show All
            </button>
          </div>
        </div>

        {/* Charts — collapsible */}
        {clicks.length > 0 && (
          <div className={`mb-2 ${showCharts ? '' : 'hidden'}`}>
            {/* Row 1: 2 bar charts + 2 pies */}
            <div className="grid grid-cols-4 gap-2 mb-2">
              <div className="bg-white rounded-xl border border-gray-100 p-2">
                <h3 className="text-[11px] font-semibold text-gray-600 mb-1">Valid vs Invalid</h3>
                <div style={{ height: '100px' }}>
                  <Bar data={{ labels: dailyTrend.labels, datasets: [
                    { label: 'Valid', data: dailyTrend.valid, backgroundColor: '#16A34A', borderRadius: 2, stack: 's' },
                    { label: 'Invalid', data: dailyTrend.invalid, backgroundColor: '#DC2626', borderRadius: 2, stack: 's' },
                  ]}} options={stackedBar} />
                </div>
              </div>
              <div className="bg-white rounded-xl border border-gray-100 p-2">
                <h3 className="text-[11px] font-semibold text-gray-600 mb-1">Earnings</h3>
                <div style={{ height: '100px' }}>
                  <Bar data={{ labels: dailyTrend.labels, datasets: [{ label: '$', data: dailyTrend.earnings, backgroundColor: 'rgba(220,38,38,0.7)', borderRadius: 2 }] }} options={earningsBar} />
                </div>
              </div>
              <div className="bg-white rounded-xl border border-gray-100 p-2">
                <h3 className="text-[11px] font-semibold text-gray-600 mb-1">Status</h3>
                <div style={{ height: '100px' }}>
                  <Pie data={statusPie} options={tinyPie} />
                </div>
              </div>
              <div className="bg-white rounded-xl border border-gray-100 p-2">
                <h3 className="text-[11px] font-semibold text-gray-600 mb-1">Devices</h3>
                <div style={{ height: '100px' }}>
                  <Pie data={devicePie} options={tinyPie} />
                </div>
              </div>
            </div>
            {/* Row 2: OS + Browsers + Countries */}
            <div className="grid grid-cols-3 gap-2">
              <div className="bg-white rounded-xl border border-gray-100 p-2">
                <h3 className="text-[11px] font-semibold text-gray-600 mb-1">OS</h3>
                <div style={{ height: '90px' }}>
                  <Doughnut data={osPie} options={tinyDoughnut} />
                </div>
              </div>
              <div className="bg-white rounded-xl border border-gray-100 p-2">
                <h3 className="text-[11px] font-semibold text-gray-600 mb-1">Browsers</h3>
                <div style={{ height: '90px' }}>
                  <Doughnut data={browserPie} options={tinyDoughnut} />
                </div>
              </div>
              <div className="bg-white rounded-xl border border-gray-100 p-2">
                <h3 className="text-[11px] font-semibold text-gray-600 mb-1">Traffic by Country</h3>
                <div style={{ height: '90px' }}>
                  <Pie data={countryPie} options={countryPieOpts} />
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Toggle charts button */}
        {clicks.length > 0 && (
          <button onClick={() => setShowCharts(p => !p)}
            className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 mb-1 transition-colors">
            <BarChart3 size={12} /> {showCharts ? 'Hide charts' : 'Show charts'}
          </button>
        )}

        {/* Data Table — always visible */}
        <div className="bg-white rounded-xl border border-gray-100 p-2">
          <DataTable columns={columns} data={clicks} loading={loading} compact
            pagination={{ page, total, limit: 50, onPageChange: setPage }}
            emptyMessage="No clicks found for the selected filters" />
        </div>
      </div>
    </div>
  )
}
