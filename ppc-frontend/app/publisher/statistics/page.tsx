'use client'

import { useState, useEffect, useCallback, useMemo } from 'react'
import { Download, MousePointer, CheckCircle, XCircle, DollarSign } from 'lucide-react'
import { toast } from 'sonner'
import PublisherSidebar from '@/components/shared/PublisherSidebar'
import DataTable from '@/components/tables/DataTable'
import { StatusBadge } from '@/components/ui/badge'
import { publisherApi, downloadBlob } from '@/lib/api'
import { useAuth } from '@/lib/hooks/useAuth'
import type { Click } from '@/types'
import { format } from 'date-fns'

export default function PublisherStatisticsPage() {
  const { initialize } = useAuth()
  const [clicks, setClicks] = useState<Click[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [summary, setSummary] = useState<{total: number; valid: number; invalid: number; earnings: number} | null>(null)
  const [websites, setWebsites] = useState<{id: string; domain: string}[]>([])
  const [filters, setFilters] = useState({
    date_from: '', date_to: '', website_id: '',
    status: '', device_type: '', os: '', browser: '', country_code: '',
  })

  useEffect(() => { initialize() }, [])

  useEffect(() => {
    // Default: show today's stats (date_to = today, inclusive of full day via backend)
    const today = new Date().toISOString().split('T')[0]
    setFilters(f => ({ ...f, date_from: today, date_to: today }))
  }, [])

  useEffect(() => {
    const loadWebsites = async () => {
      try {
        const res = await publisherApi.getWebsites()
        setWebsites(res.data.websites?.map((w: any) => ({ id: w.id, domain: w.domain })) || [])
      } catch {}
    }
    loadWebsites()
  }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params: any = { page, limit: 50 }
      if (filters.date_from) params.date_from = filters.date_from
      if (filters.date_to) params.date_to = filters.date_to
      if (filters.website_id) params.website_id = filters.website_id
      if (filters.status) params.status = filters.status
      if (filters.device_type) params.device_type = filters.device_type
      if (filters.os) params.os = filters.os
      if (filters.browser) params.browser = filters.browser
      if (filters.country_code) params.country_code = filters.country_code
      const res = await publisherApi.getReports(params)
      setClicks(res.data.clicks)
      setTotal(res.data.total)
      setSummary(res.data.summary || null)
    } catch { toast.error('Failed to load statistics') }
    finally { setLoading(false) }
  }, [page, filters])

  useEffect(() => { load() }, [load])

  const handleExport = async () => {
    try {
      const params: any = {}
      if (filters.date_from) params.date_from = filters.date_from
      if (filters.date_to) params.date_to = filters.date_to
      if (filters.website_id) params.website_id = filters.website_id
      if (filters.status) params.status = filters.status
      if (filters.device_type) params.device_type = filters.device_type
      if (filters.os) params.os = filters.os
      if (filters.browser) params.browser = filters.browser
      if (filters.country_code) params.country_code = filters.country_code
      const res = await publisherApi.exportReportsCSV(params)
      downloadBlob(res.data, `my_statistics_${Date.now()}.csv`)
      toast.success('Exported')
    } catch { toast.error('Export failed') }
  }

  const stats = useMemo(() => {
    // Prefer the backend's full-window summary; fall back to the current page
    // only if it's unavailable (e.g. summary field missing on an old response).
    if (summary) return { valid: summary.valid, invalid: summary.invalid, earnings: summary.earnings }
    const v = clicks.filter(c => c.status === 'valid').length
    const inv = clicks.filter(c => c.status === 'invalid').length
    const e = clicks.reduce((s, c) => s + c.earnings, 0)
    return { valid: v, invalid: inv, earnings: e }
  }, [clicks, summary])

  const sel = "px-2 py-1.5 border border-gray-200 rounded-lg text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary text-xs"

  const columns = [
    { key: 'timestamp', label: 'Time', render: (c: Click) => <span className="text-xs font-mono text-gray-500">{format(new Date(c.timestamp), 'MMM d, HH:mm:ss')}</span> },
    { key: 'website', label: 'Website', render: (c: Click) => {
      const domain = (c as any).website_domain || c.website_id
      return domain ? <span className="text-xs text-blue-600 font-medium truncate max-w-[120px] block">{domain}</span> : <span className="text-gray-300">—</span>
    }},
    { key: 'country_code', label: 'Country', render: (c: Click) => <span className="text-gray-700">{c.country_code || '—'}</span> },
    { key: 'device_type', label: 'Device', render: (c: Click) => <StatusBadge status={c.device_type} /> },
    { key: 'os', label: 'OS', render: (c: Click) => <span className="text-xs text-gray-500">{c.os || '—'}</span> },
    { key: 'browser', label: 'Browser', render: (c: Click) => <span className="text-xs text-gray-500">{c.browser || '—'}</span> },
    { key: 'status', label: 'Status', render: (c: Click) => <StatusBadge status={c.status} /> },
    { key: 'earnings', label: 'Earnings', render: (c: Click) => <span className="font-mono text-red-600 font-semibold">${c.earnings.toFixed(6)}</span> },
    { key: 'fraud_reason', label: 'Fraud', render: (c: Click) => c.fraud_reason ? <span className="text-red-500 text-xs">{c.fraud_reason}</span> : <span className="text-gray-300">—</span> },
  ]

  return (
    <div className="flex min-h-screen bg-[#f8f9fb]">
      <PublisherSidebar />
      <div className="flex-1 lg:ml-64 p-4 lg:p-5">
        <div className="flex items-center justify-between mb-3 pt-12 lg:pt-0">
          <div>
            <h1 className="text-xl font-bold text-gray-900">Statistics</h1>
            <p className="text-gray-400 text-xs">{total.toLocaleString()} total clicks</p>
          </div>
          <button onClick={handleExport}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium border border-gray-200 text-gray-700 hover:bg-gray-50">
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
            <select value={filters.website_id} onChange={e => setFilters(p => ({...p, website_id: e.target.value}))} className={sel}>
              <option value="">All Websites</option>
              {websites.map(w => (
                <option key={w.id} value={w.id}>{w.domain}</option>
              ))}
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
              placeholder="CC" maxLength={2} className={`${sel} w-16`} />
            <button onClick={() => { setPage(1); load() }} className="bg-primary hover:bg-primary-dark text-white px-3 py-1.5 rounded-lg text-xs font-medium">
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

        {/* Data Table */}
        <div className="bg-white rounded-xl border border-gray-100 p-3">
          <DataTable columns={columns} data={clicks} loading={loading} compact
            pagination={{ page, total, limit: 50, onPageChange: setPage }}
            emptyMessage="No click data available" />
        </div>
      </div>
    </div>
  )
}
