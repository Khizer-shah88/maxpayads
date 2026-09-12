'use client'

import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  Plus, Edit, Trash2, Link, Copy, CheckCircle, RefreshCw,
  BarChart3, TrendingUp, MousePointer, Calendar,
} from 'lucide-react'
import { toast } from 'sonner'
import Sidebar from '@/components/shared/Sidebar'
import { StatusBadge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/loading'
import { directLinkApi, adminApi } from '@/lib/api'
import { useAuth } from '@/lib/hooks/useAuth'
import type { Publisher } from '@/types'
import { format } from 'date-fns'

// ─── types ────────────────────────────────────────────────────────────────────

interface DirectLink {
  id: string
  name: string
  publisher_id: string
  publisher_name: string
  campaign_id?: string | null
  masked_domain: string
  slug: string
  masked_url: string
  destination_url: string
  prelander_template_id?: string | null
  status: 'active' | 'paused' | 'archived'
  notes?: string | null
  daily_conversion_cap: number
  total_clicks: number
  total_conversions: number
  today_conversions: number
  created_at?: string | null
}

interface Conversion {
  id: string
  link_id: string
  publisher_id: string
  slug: string
  ip_address: string
  user_agent: string
  referrer: string
  created_at: string
}

interface DailySummary {
  date: string
  conversions: number
  unique_links: number
}

const EMPTY_FORM = {
  name: '',
  publisher_id: '',
  masked_domain: '',
  destination_url: '',
  prelander_template_id: '',
  campaign_id: '',
  status: 'active' as 'active' | 'paused' | 'archived',
  daily_conversion_cap: 0,
  notes: '',
}

// ─── helpers ──────────────────────────────────────────────────────────────────

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  const handleCopy = () => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1800)
  }
  return (
    <button onClick={handleCopy}
      className="p-1.5 rounded-lg text-gray-400 hover:text-primary hover:bg-primary/5 transition-colors"
      title="Copy URL">
      {copied ? <CheckCircle size={14} className="text-emerald-500" /> : <Copy size={14} />}
    </button>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function DirectLinksPage() {
  const { initialize } = useAuth()

  // List state
  const [links, setLinks] = useState<DirectLink[]>([])
  const [loading, setLoading] = useState(true)
  const [pubFilter, setPubFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  // Create / edit
  const [modal, setModal] = useState<'create' | 'edit' | null>(null)
  const [editTarget, setEditTarget] = useState<DirectLink | null>(null)
  const [form, setForm] = useState({ ...EMPTY_FORM })
  const [saving, setSaving] = useState(false)

  // Conversions drawer
  const [convDrawer, setConvDrawer] = useState<DirectLink | null>(null)
  const [conversions, setConversions] = useState<Conversion[]>([])
  const [convTotal, setConvTotal] = useState(0)
  const [convPage, setConvPage] = useState(1)
  const [convLoading, setConvLoading] = useState(false)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')

  // Chart data
  const [dailySummary, setDailySummary] = useState<DailySummary[]>([])

  // Publishers + templates for dropdowns
  const [publishers, setPublishers] = useState<Publisher[]>([])
  const [regenerating, setRegenerating] = useState<string | null>(null)
  const [error, setError] = useState<string>('')

  // Safe auth initialization
  useEffect(() => { 
    const initAuth = async () => {
      try {
        await initialize()
      } catch (err) {
        console.error('Auth initialization error:', err)
        toast.error('Authentication initialization failed')
      }
    }
    initAuth()
  }, [initialize])

  // Load publishers once
  useEffect(() => {
    const loadPubs = async () => {
      try {
        const r = await adminApi.getPublishers({ limit: 200 })
        setPublishers((r.data?.publishers ?? []).filter((p: Publisher) => p.role !== 'admin'))
      } catch (err) {
        console.error('Failed to load publishers:', err)
        toast.error('Failed to load publishers')
      }
    }
    loadPubs()
  }, [])

  // ── Load links ─────────────────────────────────────────────────────────────
  const loadLinks = useCallback(async () => {
    setLoading(true)
    try {
      console.log('Loading direct links with filters:', { pubFilter, statusFilter })
      
      const res = await directLinkApi.getAll({
        publisher_id: pubFilter || undefined,
        status: statusFilter || undefined,
      })
      
      console.log('Direct links response:', res.data)
      setLinks(res.data?.links ?? [])
    } catch (err: any) {
      console.error('Failed to load direct links:', err)
      console.error('Error response:', err?.response?.data)
      
      if (err?.response?.status === 404) {
        toast.error('Direct links API not available - feature may not be deployed yet')
        // Set empty array so UI still renders
        setLinks([])
      } else {
        toast.error(err?.response?.data?.detail || 'Failed to load direct links')
        setLinks([])
      }
    } finally {
      setLoading(false)
    }
  }, [pubFilter, statusFilter])

  useEffect(() => { 
    loadLinks() 
  }, [loadLinks])

  // Load daily summary chart (last 30 days)
  useEffect(() => {
    const loadSummary = async () => {
      try {
        await directLinkApi.getConversions({ limit: 1 })
        
        const token = document.cookie
          .split('; ')
          .find(row => row.startsWith('admin_token='))
          ?.split('=')[1]
        
        if (!token) {
          console.warn('No admin token found for daily summary')
          return
        }

        const response = await fetch('/api/direct-links/conversions/daily-summary?days=30', {
          headers: { 
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        })
        
        if (response.ok) {
          const data = await response.json()
          setDailySummary(data?.summary ?? [])
        }
      } catch (err) {
        console.warn('Daily summary not available:', err)
      }
    }
    
    loadSummary()
  }, [])

  // Conversions drawer loading
  const loadConversions = useCallback(async () => {
    if (!convDrawer) return
    setConvLoading(true)
    try {
      const res = await directLinkApi.getConversions({
        link_id: convDrawer.id,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        page: convPage,
        limit: 50,
      })
      setConversions(res.data?.conversions ?? [])
      setConvTotal(res.data?.total ?? 0)
    } catch { toast.error('Failed to load conversions') }
    finally { setConvLoading(false) }
  }, [convDrawer, dateFrom, dateTo, convPage])

  useEffect(() => { 
    if (convDrawer) loadConversions() 
  }, [convDrawer, loadConversions])

  // CRUD operations
  const openCreate = () => {
    setForm({ ...EMPTY_FORM })
    setEditTarget(null)
    setModal('create')
  }

  const openEdit = (l: DirectLink) => {
    setEditTarget(l)
    setForm({
      name: l.name,
      publisher_id: l.publisher_id,
      masked_domain: l.masked_domain,
      destination_url: l.destination_url,
      prelander_template_id: l.prelander_template_id ?? '',
      campaign_id: l.campaign_id ?? '',
      status: l.status,
      daily_conversion_cap: l.daily_conversion_cap,
      notes: l.notes ?? '',
    })
    setModal('edit')
  }

  const handleSave = async () => {
    if (!form.name.trim()) { toast.error('Name is required'); return }
    if (!form.publisher_id) { toast.error('Publisher is required'); return }
    if (!form.masked_domain.trim()) { toast.error('Masked domain is required'); return }
    if (!form.destination_url.trim()) { toast.error('Destination URL is required'); return }

    setSaving(true)
    try {
      console.log('Creating direct link with payload:', form)
      
      const payload: any = {
        name: form.name.trim(),
        publisher_id: form.publisher_id,
        masked_domain: form.masked_domain.trim(),
        destination_url: form.destination_url.trim(),
        status: form.status,
        daily_conversion_cap: Number(form.daily_conversion_cap),
        notes: form.notes.trim() || null,
      }
      if (form.prelander_template_id.trim()) payload.prelander_template_id = form.prelander_template_id.trim()
      if (form.campaign_id.trim()) payload.campaign_id = form.campaign_id.trim()

      let result
      if (modal === 'edit' && editTarget) {
        console.log('Updating direct link:', editTarget.id)
        result = await directLinkApi.update(editTarget.id, payload)
        toast.success('Direct link updated')
      } else {
        console.log('Creating new direct link')
        result = await directLinkApi.create(payload)
        toast.success('Direct link created')
      }
      
      console.log('Direct link save result:', result)
      setModal(null)
      loadLinks()
    } catch (err: any) {
      console.error('Direct link save error:', err)
      console.error('Error response:', err?.response?.data)
      console.error('Error status:', err?.response?.status)
      
      // More specific error messages
      if (err?.response?.status === 404) {
        toast.error('Direct link API endpoint not found - feature may not be deployed yet')
      } else if (err?.response?.status === 422) {
        // Handle validation errors - detail can be a string or an array of objects
        const detail = err?.response?.data?.detail
        let errorMessage = 'Validation error: '
        
        if (typeof detail === 'string') {
          errorMessage += detail
        } else if (Array.isArray(detail)) {
          // FastAPI validation errors are arrays of objects with loc, msg, type
          errorMessage += detail.map((e: any) => e.msg || JSON.stringify(e)).join(', ')
        } else if (detail && typeof detail === 'object') {
          errorMessage += JSON.stringify(detail)
        } else {
          errorMessage += 'Invalid data provided'
        }
        
        toast.error(errorMessage)
      } else {
        const detail = err?.response?.data?.detail
        const message = typeof detail === 'string' ? detail : (err?.message || 'Save failed')
        toast.error(message)
      }
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (l: DirectLink) => {
    if (!confirm(`Delete link "${l.name}"?`)) return
    try {
      await directLinkApi.delete(l.id)
      toast.success('Link deleted')
      loadLinks()
    } catch { toast.error('Delete failed') }
  }

  const handleRegenSlug = async (l: DirectLink) => {
    if (!confirm('Regenerate the slug? The old URL will stop working immediately.')) return
    setRegenerating(l.id)
    try {
      await directLinkApi.regenerateSlug(l.id)
      toast.success('Slug regenerated')
      loadLinks()
    } catch { toast.error('Failed to regenerate slug') }
    finally { setRegenerating(null) }
  }

  // Summary stats
  const totalConversions = useMemo(() => links.reduce((s, l) => s + l.total_conversions, 0), [links])
  const todayTotal = useMemo(() => links.reduce((s, l) => s + l.today_conversions, 0), [links])

  const inp = 'w-full px-4 py-2.5 border border-gray-200 rounded-xl text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary text-sm'

  // Early error state check
  if (error) {
    return (
      <div className="flex min-h-screen bg-[#f8f9fb]">
        <Sidebar />
        <div className="flex-1 lg:ml-64 p-6 lg:p-8 min-w-0 overflow-x-hidden">
          <div className="text-center py-20">
            <div className="text-red-500 mb-4">
              <Link size={48} className="mx-auto mb-4 opacity-30" />
            </div>
            <h2 className="text-xl font-bold text-gray-900 mb-2">Direct Links Error</h2>
            <p className="text-gray-600 mb-4">{error}</p>
            <button 
              onClick={() => window.location.reload()} 
              className="px-4 py-2 bg-primary text-white rounded-lg hover:bg-primary-dark"
            >
              Reload Page
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex min-h-screen bg-[#f8f9fb]">
      <Sidebar />
      <div className="flex-1 lg:ml-64 p-6 lg:p-8 min-w-0 overflow-x-hidden">

        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 pt-12 lg:pt-0">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Direct Links</h1>
            <p className="text-gray-400 text-sm mt-0.5">
              Masked hash-slug affiliate URLs — hides network identity, tracks conversions daily
            </p>
          </div>
          <button onClick={openCreate}
            className="bg-primary hover:bg-primary-dark text-white px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2 self-start">
            <Plus size={18} /> Add Link
          </button>
        </div>

        {/* Summary cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
          {[
            { icon: <Link size={18} />, label: 'Total Links', value: links.length, color: 'text-primary' },
            { icon: <MousePointer size={18} />, label: 'Total Clicks', value: links.reduce((s, l) => s + l.total_clicks, 0).toLocaleString(), color: 'text-blue-600' },
            { icon: <TrendingUp size={18} />, label: 'Total Conversions', value: totalConversions.toLocaleString(), color: 'text-emerald-600' },
            { icon: <Calendar size={18} />, label: "Today's Conversions", value: todayTotal.toLocaleString(), color: 'text-amber-600' },
          ].map((s, i) => (
            <div key={i} className="bg-white rounded-2xl border border-gray-100 p-4">
              <div className={`${s.color} mb-1.5`}>{s.icon}</div>
              <p className="text-xs text-gray-400 font-medium">{s.label}</p>
              <p className="text-xl font-bold text-gray-900 mt-0.5">{s.value}</p>
            </div>
          ))}
        </div>

        {/* Daily conversions mini-chart */}
        {dailySummary.length > 0 && (
          <div className="bg-white rounded-2xl border border-gray-100 p-5 mb-6">
            <div className="flex items-center gap-2 mb-3">
              <BarChart3 size={16} className="text-gray-400" />
              <h2 className="text-sm font-semibold text-gray-900">Conversions — Last 30 Days</h2>
            </div>
            <div className="flex items-end gap-1 h-16">
              {dailySummary.map((d, i) => {
                const max = Math.max(...dailySummary.map(x => x.conversions), 1)
                const h = Math.round((d.conversions / max) * 100)
                return (
                  <div key={i} title={`${d.date}: ${d.conversions}`}
                    className="flex-1 bg-primary/20 hover:bg-primary/50 rounded-t transition-colors cursor-default"
                    style={{ height: `${Math.max(h, 4)}%` }} />
                )
              })}
            </div>
            <div className="flex justify-between text-[10px] text-gray-300 mt-1">
              <span>{dailySummary[0]?.date}</span>
              <span>{dailySummary[dailySummary.length - 1]?.date}</span>
            </div>
          </div>
        )}

        {/* Filters */}
        <div className="bg-white rounded-2xl border border-gray-100 p-4 mb-4 flex flex-wrap gap-3 items-center">
          <select value={pubFilter} onChange={e => setPubFilter(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-xl text-sm text-gray-700 bg-white focus:outline-none">
            <option value="">All Publishers</option>
            {publishers.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-xl text-sm text-gray-700 bg-white focus:outline-none">
            <option value="">All Status</option>
            <option value="active">Active</option>
            <option value="paused">Paused</option>
            <option value="archived">Archived</option>
          </select>
        </div>

        {/* Links table */}
        <div className="bg-white rounded-2xl border border-gray-100 overflow-hidden">
          {loading ? (
            <div className="p-8 flex justify-center"><Spinner size={24} /></div>
          ) : links.length === 0 ? (
            <div className="text-center py-16 text-gray-400">
              <Link size={40} className="mx-auto mb-3 opacity-30" />
              <p>No direct links yet</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-100">
                  <tr>
                    {['Name / Publisher', 'Masked URL', 'Status', 'Today', 'Total Conv.', 'Actions'].map(h => (
                      <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {links.map(l => (
                    <tr key={l.id} className="hover:bg-gray-50/50">
                      <td className="px-4 py-3">
                        <p className="font-medium text-gray-900">{l.name}</p>
                        <p className="text-xs text-gray-400">{l.publisher_name || l.publisher_id.slice(-8)}</p>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1 max-w-[240px]">
                          <code className="text-xs text-gray-600 bg-gray-100 px-2 py-0.5 rounded font-mono truncate">{l.masked_url}</code>
                          <CopyButton text={l.masked_url} />
                        </div>
                        <p className="text-[11px] text-gray-300 mt-0.5 truncate max-w-[200px]">{l.destination_url}</p>
                      </td>
                      <td className="px-4 py-3"><StatusBadge status={l.status} /></td>
                      <td className="px-4 py-3">
                        <span className={`font-mono font-bold ${l.today_conversions > 0 ? 'text-emerald-600' : 'text-gray-400'}`}>
                          {l.today_conversions}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="font-mono text-gray-700">{l.total_conversions.toLocaleString()}</span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1">
                          <button onClick={() => { setConvDrawer(l); setConvPage(1); setDateFrom(''); setDateTo('') }}
                            title="View conversions"
                            className="p-1.5 rounded text-gray-400 hover:text-emerald-600 hover:bg-emerald-50">
                            <BarChart3 size={14} />
                          </button>
                          <button onClick={() => openEdit(l)} title="Edit"
                            className="p-1.5 rounded text-gray-400 hover:text-gray-900 hover:bg-gray-100">
                            <Edit size={14} />
                          </button>
                          <button onClick={() => handleRegenSlug(l)} disabled={regenerating === l.id}
                            title="Regenerate slug"
                            className="p-1.5 rounded text-gray-400 hover:text-blue-600 hover:bg-blue-50 disabled:opacity-50">
                            {regenerating === l.id ? <Spinner size={14} /> : <RefreshCw size={14} />}
                          </button>
                          <button onClick={() => handleDelete(l)} title="Delete"
                            className="p-1.5 rounded text-red-400 hover:text-red-600 hover:bg-red-50">
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* ── Create / Edit Modal ─────────────────────────────────────────── */}
        {(modal === 'create' || modal === 'edit') && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-6 w-full max-w-lg shadow-2xl border border-gray-100 max-h-[92vh] overflow-y-auto">
              <h3 className="text-lg font-bold text-gray-900 mb-5">
                {modal === 'create' ? 'Create Direct Link' : `Edit — ${editTarget?.name}`}
              </h3>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Link Name <span className="text-red-500">*</span></label>
                  <input value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))}
                    placeholder="e.g. Campaign A — Publisher 1" className={inp} />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Publisher <span className="text-red-500">*</span></label>
                  <select value={form.publisher_id} onChange={e => setForm(p => ({ ...p, publisher_id: e.target.value }))} className={inp}>
                    <option value="">Select publisher…</option>
                    {publishers.map(p => <option key={p.id} value={p.id}>{p.name} ({p.email})</option>)}
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Masked Domain <span className="text-red-500">*</span>
                    <span className="text-gray-400 font-normal ml-1">— no https://</span>
                  </label>
                  <input value={form.masked_domain} onChange={e => setForm(p => ({ ...p, masked_domain: e.target.value }))}
                    placeholder="click.yourdomain.com" className={inp} />
                  {form.masked_domain && (
                    <p className="text-[11px] text-gray-400 mt-1">
                      Generated URL: <code className="bg-gray-100 px-1 rounded">https://{form.masked_domain}/#/{'<slug>'}</code>
                    </p>
                  )}
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Destination URL <span className="text-red-500">*</span></label>
                  <input value={form.destination_url} onChange={e => setForm(p => ({ ...p, destination_url: e.target.value }))}
                    placeholder="https://offer-network.com/track/xyz" className={inp} />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
                    <select value={form.status} onChange={e => setForm(p => ({ ...p, status: e.target.value as typeof form.status }))} className={inp}>
                      <option value="active">Active</option>
                      <option value="paused">Paused</option>
                      <option value="archived">Archived</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Daily Cap <span className="text-gray-400 font-normal">(0 = unlimited)</span></label>
                    <input type="number" min={0} value={form.daily_conversion_cap}
                      onChange={e => setForm(p => ({ ...p, daily_conversion_cap: parseInt(e.target.value) || 0 }))} className={inp} />
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Notes</label>
                  <textarea value={form.notes} onChange={e => setForm(p => ({ ...p, notes: e.target.value }))}
                    rows={2} className={inp} />
                </div>
              </div>

              <div className="flex gap-3 mt-6">
                <button onClick={handleSave} disabled={saving}
                  className="flex-1 bg-primary hover:bg-primary-dark text-white py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 disabled:bg-gray-300">
                  {saving ? <Spinner size={16} /> : (modal === 'create' ? 'Create Link' : 'Save Changes')}
                </button>
                <button onClick={() => setModal(null)}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50">
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── Conversions Drawer ──────────────────────────────────────────── */}
        {convDrawer && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-end sm:items-center justify-center p-0 sm:p-4">
            <div className="bg-white w-full sm:rounded-2xl sm:max-w-2xl shadow-2xl border border-gray-100 max-h-[90vh] flex flex-col">
              {/* Drawer header */}
              <div className="flex items-center justify-between p-5 border-b border-gray-100">
                <div>
                  <h3 className="font-bold text-gray-900">{convDrawer.name}</h3>
                  <p className="text-xs text-gray-400 mt-0.5">
                    <code className="bg-gray-100 px-1 rounded">{convDrawer.masked_url}</code>
                    {' — '}Total: {convDrawer.total_conversions} | Today: {convDrawer.today_conversions}
                  </p>
                </div>
                <button onClick={() => setConvDrawer(null)}
                  className="text-gray-400 hover:text-gray-700 text-2xl font-light leading-none">×</button>
              </div>

              {/* Date filter */}
              <div className="flex gap-2 px-5 py-3 border-b border-gray-100 flex-wrap">
                <input type="date" value={dateFrom} onChange={e => { setDateFrom(e.target.value); setConvPage(1) }}
                  className="px-3 py-1.5 border border-gray-200 rounded-xl text-sm" />
                <span className="text-gray-300 self-center">→</span>
                <input type="date" value={dateTo} onChange={e => { setDateTo(e.target.value); setConvPage(1) }}
                  className="px-3 py-1.5 border border-gray-200 rounded-xl text-sm" />
                <button onClick={loadConversions}
                  className="px-3 py-1.5 bg-primary text-white rounded-xl text-sm font-medium">Apply</button>
                <span className="text-xs text-gray-400 self-center ml-auto">{convTotal} total</span>
              </div>

              {/* Table */}
              <div className="flex-1 overflow-y-auto">
                {convLoading ? (
                  <div className="p-8 flex justify-center"><Spinner size={24} /></div>
                ) : conversions.length === 0 ? (
                  <div className="text-center py-12 text-gray-400 text-sm">No conversions in this range</div>
                ) : (
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50 sticky top-0">
                      <tr>
                        {['Time', 'IP', 'Country', 'User Agent'].map(h => (
                          <th key={h} className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase whitespace-nowrap">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-50">
                      {conversions.map(c => (
                        <tr key={c.id} className="hover:bg-gray-50/50">
                          <td className="px-4 py-2.5 text-xs font-mono text-gray-500 whitespace-nowrap">
                            {(() => {
                              try {
                                return format(new Date(c.created_at), 'MMM d, HH:mm')
                              } catch (err) {
                                return c.created_at || '—'
                              }
                            })()}
                          </td>
                          <td className="px-4 py-2.5 text-xs font-mono text-gray-600">{c.ip_address}</td>
                          <td className="px-4 py-2.5 text-xs text-gray-500">—</td>
                          <td className="px-4 py-2.5 text-xs text-gray-400 max-w-[200px] truncate"
                            title={c.user_agent}>{c.user_agent || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>

              {/* Pagination */}
              {convTotal > 50 && (
                <div className="flex items-center justify-between p-4 border-t border-gray-100">
                  <button disabled={convPage <= 1} onClick={() => setConvPage(p => p - 1)}
                    className="px-3 py-1.5 rounded-xl border border-gray-200 text-sm disabled:opacity-30">Prev</button>
                  <span className="text-xs text-gray-400">Page {convPage} of {Math.ceil(convTotal / 50)}</span>
                  <button disabled={convPage >= Math.ceil(convTotal / 50)} onClick={() => setConvPage(p => p + 1)}
                    className="px-3 py-1.5 rounded-xl border border-gray-200 text-sm disabled:opacity-30">Next</button>
                </div>
              )}
            </div>
          </div>
        )}

      </div>
    </div>
  )
}
