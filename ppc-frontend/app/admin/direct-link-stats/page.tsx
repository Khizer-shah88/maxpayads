'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  BarChart3, Monitor, Apple, Globe2, Hash, Shield,
  Calendar, Edit3, CheckCircle, TrendingUp, Copy, RefreshCw,
  Plus, Trash2, Link,
} from 'lucide-react'
import { toast } from 'sonner'
import Sidebar from '@/components/shared/Sidebar'
import { StatusBadge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/loading'
import { adminApi, directLinkApi } from '@/lib/api'
import { useAuth } from '@/lib/hooks/useAuth'

// ─── Types ────────────────────────────────────────────────────────────────────

interface DirectLink {
  id: string
  name: string
  publisher_id: string
  publisher_name: string
  masked_domain: string
  slug: string
  masked_url: string
  destination_url: string
  status: string
  total_clicks: number
  total_conversions: number
  today_conversions: number
  created_at?: string | null
}

interface Publisher {
  id: string
  name: string
  email: string
  role: string
  status: string
}

interface ManualOverride {
  date: string
  publisher_id: string
  link_id?: string
  manual_conversions: number
  reason: string
}

interface LinkFormData {
  name: string
  publisher_id: string
  masked_domain: string
  destination_url: string
  status: 'active' | 'paused' | 'archived'
  daily_conversion_cap: number
  notes: string
}

const EMPTY_LINK_FORM: LinkFormData = {
  name: '',
  publisher_id: '',
  masked_domain: '',
  destination_url: '',
  status: 'active',
  daily_conversion_cap: 0,
  notes: '',
}

function safeBtoa(str: string): string {
  try {
    // encode to handle unicode
    return btoa(unescape(encodeURIComponent(str)))
  } catch {
    return btoa(str.replace(/[^\x00-\x7F]/g, '?'))
  }
}

function formatDate(dateStr: string): string {
  try {
    const d = new Date(dateStr + 'T00:00:00')
    if (isNaN(d.getTime())) return dateStr
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  } catch {
    return dateStr
  }
}

function CopyButton({ text, label = 'Copy' }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false)
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
      toast.success('Copied!')
    } catch {
      toast.error('Copy failed')
    }
  }
  return (
    <button onClick={handleCopy}
      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-primary hover:bg-primary/5 border border-primary/20 transition-colors">
      {copied ? <CheckCircle size={13} className="text-emerald-500" /> : <Copy size={13} />}
      {label}
    </button>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function DirectLinkStatsPage() {
  const { initialize } = useAuth()

  const [publishers, setPublishers] = useState<Publisher[]>([])
  const [links, setLinks] = useState<DirectLink[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedPublisherId, setSelectedPublisherId] = useState<string>('')

  // Create link modal
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [linkForm, setLinkForm] = useState<LinkFormData>({ ...EMPTY_LINK_FORM })
  const [savingLink, setSavingLink] = useState(false)

  // Manual override modal
  const [showOverrideModal, setShowOverrideModal] = useState(false)
  const [overrideForm, setOverrideForm] = useState<ManualOverride>({
    date: '',
    publisher_id: '',
    link_id: '',
    manual_conversions: 0,
    reason: '',
  })
  const [savingOverride, setSavingOverride] = useState(false)

  // Date filter
  const [dateFrom, setDateFrom] = useState(() => {
    const d = new Date()
    d.setDate(d.getDate() - 30)
    return d.toISOString().split('T')[0]
  })
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().split('T')[0])

  // Auth init
  useEffect(() => {
    try { initialize() } catch { /* ignore */ }
  }, [initialize])

  // Load publishers + links together
  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [pubRes, linksRes] = await Promise.all([
        adminApi.getPublishers({ limit: 500 }),
        directLinkApi.getAll().catch(() => ({ data: { links: [] } })),
      ])
      const allPubs: Publisher[] = (pubRes.data?.publishers ?? []).filter(
        (p: Publisher) => p.role === 'publisher'
      )
      setPublishers(allPubs)
      setLinks(linksRes.data?.links ?? [])
    } catch (err: any) {
      toast.error(err?.response?.data?.error || 'Failed to load data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  // Links for selected publisher
  const publisherLinks = selectedPublisherId
    ? links.filter(l => l.publisher_id === selectedPublisherId)
    : []

  const selectedPublisher = publishers.find(p => p.id === selectedPublisherId)

  // Aggregated stats per publisher
  const publisherStats = publishers.map(pub => {
    const pubLinks = links.filter(l => l.publisher_id === pub.id)
    const totalClicks = pubLinks.reduce((s, l) => s + (l.total_clicks || 0), 0)
    const totalConversions = pubLinks.reduce((s, l) => s + (l.total_conversions || 0), 0)
    const todayConversions = pubLinks.reduce((s, l) => s + (l.today_conversions || 0), 0)
    return {
      ...pub,
      linkCount: pubLinks.length,
      totalClicks,
      totalConversions,
      todayConversions,
      cr: totalClicks > 0 ? (totalConversions / totalClicks * 100) : 0,
    }
  }).filter(p => p.linkCount > 0) // only publishers with at least 1 link

  // Create link
  const handleCreateLink = async () => {
    if (!linkForm.name.trim()) { toast.error('Name is required'); return }
    if (!linkForm.publisher_id) { toast.error('Publisher is required'); return }
    if (!linkForm.masked_domain.trim()) { toast.error('Masked domain is required'); return }
    if (!linkForm.destination_url.trim()) { toast.error('Destination URL is required'); return }

    setSavingLink(true)
    try {
      await directLinkApi.create({
        name: linkForm.name.trim(),
        publisher_id: linkForm.publisher_id,
        masked_domain: linkForm.masked_domain.trim(),
        destination_url: linkForm.destination_url.trim(),
        status: linkForm.status,
        daily_conversion_cap: Number(linkForm.daily_conversion_cap) || 0,
        notes: linkForm.notes.trim() || null,
      })
      toast.success('Direct link created')
      setShowCreateModal(false)
      setLinkForm({ ...EMPTY_LINK_FORM })
      loadData()
    } catch (err: any) {
      const detail = err?.response?.data?.error || err?.response?.data?.detail
      toast.error(typeof detail === 'string' ? detail : 'Failed to create link')
    } finally {
      setSavingLink(false)
    }
  }

  // Delete link
  const handleDeleteLink = async (link: DirectLink) => {
    if (!confirm(`Delete link "${link.name}"?`)) return
    try {
      await directLinkApi.delete(link.id)
      toast.success('Link deleted')
      loadData()
    } catch {
      toast.error('Delete failed')
    }
  }

  // Manual override submit
  const handleOverrideSubmit = async () => {
    if (!overrideForm.reason.trim()) { toast.error('Reason is required'); return }
    if (overrideForm.manual_conversions < 0) { toast.error('Conversions must be ≥ 0'); return }
    setSavingOverride(true)
    try {
      await directLinkApi.createManualOverride({
        date: overrideForm.date,
        publisher_id: overrideForm.publisher_id,
        link_id: overrideForm.link_id || undefined,
        manual_conversions: overrideForm.manual_conversions,
        reason: overrideForm.reason,
      })
      toast.success('Manual override applied')
      setShowOverrideModal(false)
    } catch (err: any) {
      toast.error(err?.response?.data?.error || 'Failed to apply override')
    } finally {
      setSavingOverride(false)
    }
  }

  // Generate stats URL for publisher
  const generateStatsUrl = async (publisherId: string, publisherName: string) => {
    try {
      const res = await directLinkApi.generateStatsToken({ publisher_id: publisherId })
      const url = res.data?.stats_url
      if (url) {
        await navigator.clipboard.writeText(url)
        toast.success(`Stats link copied for ${publisherName}`)
      }
    } catch {
      // Fallback URL
      const fallback = `${window.location.origin}/public-stats/${publisherId}`
      await navigator.clipboard.writeText(fallback).catch(() => {})
      toast.success('Stats link copied')
    }
  }

  const inp = 'w-full px-4 py-2.5 border border-gray-200 rounded-xl text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary text-sm'

  return (
    <div className="flex min-h-screen bg-[#f8f9fb]">
      <Sidebar />
      <div className="flex-1 lg:ml-64 p-6 lg:p-8">

        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 pt-12 lg:pt-0">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Direct Link Stats</h1>
            <p className="text-gray-400 text-sm mt-0.5">
              Create links per publisher — track clicks, conversions and share white-label stats
            </p>
          </div>
          <button
            onClick={() => {
              setLinkForm({ ...EMPTY_LINK_FORM })
              setShowCreateModal(true)
            }}
            className="bg-primary hover:bg-primary-dark text-white px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2 self-start"
          >
            <Plus size={18} /> Create Link
          </button>
        </div>

        {/* Summary cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
          {[
            { label: 'Total Links', value: links.length },
            { label: 'Publishers with Links', value: publisherStats.length },
            { label: 'Total Clicks', value: links.reduce((s, l) => s + l.total_clicks, 0).toLocaleString() },
            { label: 'Total Conversions', value: links.reduce((s, l) => s + l.total_conversions, 0).toLocaleString() },
          ].map((s, i) => (
            <div key={i} className="bg-white rounded-2xl border border-gray-100 p-4">
              <p className="text-xs text-gray-400 font-medium">{s.label}</p>
              <p className="text-xl font-bold text-gray-900 mt-1">{s.value}</p>
            </div>
          ))}
        </div>

        {/* Date filter */}
        <div className="bg-white rounded-2xl border border-gray-100 p-4 mb-6 flex gap-3 items-center flex-wrap">
          <Calendar size={16} className="text-gray-400" />
          <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-xl text-sm" />
          <span className="text-gray-400">to</span>
          <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-xl text-sm" />
          <button onClick={loadData} className="px-3 py-2 border border-gray-200 rounded-xl text-sm hover:bg-gray-50 flex items-center gap-1.5">
            <RefreshCw size={14} /> Refresh
          </button>
        </div>

        {/* Publisher stats grid */}
        {loading ? (
          <div className="flex justify-center py-20"><Spinner size={32} /></div>
        ) : publisherStats.length === 0 ? (
          <div className="text-center py-20 text-gray-400">
            <Link size={48} className="mx-auto mb-4 opacity-20" />
            <p className="text-base font-medium mb-2">No direct links yet</p>
            <p className="text-sm mb-6">Create a link for a publisher to start tracking stats</p>
            <button
              onClick={() => setShowCreateModal(true)}
              className="bg-primary text-white px-5 py-2.5 rounded-xl text-sm font-semibold inline-flex items-center gap-2"
            >
              <Plus size={16} /> Create First Link
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 mb-6">
            {publisherStats.map(pub => (
              <div
                key={pub.id}
                onClick={() => setSelectedPublisherId(prev => prev === pub.id ? '' : pub.id)}
                className={`bg-white rounded-2xl border p-5 cursor-pointer transition-all hover:shadow-md ${
                  selectedPublisherId === pub.id
                    ? 'border-primary shadow-md ring-2 ring-primary/20'
                    : 'border-gray-100'
                }`}
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-gray-900 text-sm truncate">{pub.name}</h3>
                    <p className="text-xs text-gray-400 truncate">{pub.email}</p>
                  </div>
                  <StatusBadge status={pub.status} />
                </div>

                <div className="grid grid-cols-2 gap-2 mb-3">
                  <div className="bg-gray-50 rounded-xl p-2.5 text-center">
                    <p className="text-[10px] text-gray-400 uppercase font-semibold">Links</p>
                    <p className="text-base font-bold text-gray-900">{pub.linkCount}</p>
                  </div>
                  <div className="bg-gray-50 rounded-xl p-2.5 text-center">
                    <p className="text-[10px] text-gray-400 uppercase font-semibold">Today Conv.</p>
                    <p className={`text-base font-bold ${pub.todayConversions > 0 ? 'text-emerald-600' : 'text-gray-400'}`}>
                      {pub.todayConversions}
                    </p>
                  </div>
                </div>

                <div className="space-y-1.5 text-xs mb-3">
                  <div className="flex justify-between">
                    <span className="text-gray-400">Total Clicks</span>
                    <span className="font-semibold text-gray-700">{pub.totalClicks.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Total Conversions</span>
                    <span className="font-semibold text-gray-700">{pub.totalConversions.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">CR</span>
                    <span className={`font-bold ${pub.cr >= 5 ? 'text-emerald-600' : pub.cr >= 2 ? 'text-amber-600' : 'text-gray-700'}`}>
                      {pub.cr.toFixed(2)}%
                    </span>
                  </div>
                </div>

                <div className="flex gap-2 pt-2 border-t border-gray-100">
                  <button
                    onClick={e => { e.stopPropagation(); generateStatsUrl(pub.id, pub.name) }}
                    className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-medium text-primary hover:bg-primary/5 border border-primary/20 transition-colors"
                  >
                    <Copy size={12} /> Share Stats
                  </button>
                  <button
                    onClick={e => {
                      e.stopPropagation()
                      setLinkForm({ ...EMPTY_LINK_FORM, publisher_id: pub.id })
                      setShowCreateModal(true)
                    }}
                    className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-medium text-gray-600 hover:bg-gray-50 border border-gray-200 transition-colors"
                  >
                    <Plus size={12} /> Add Link
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Selected publisher links table */}
        {selectedPublisher && (
          <div className="bg-white rounded-2xl border border-gray-100 overflow-hidden mb-6">
            <div className="flex items-center justify-between p-5 border-b border-gray-100">
              <div>
                <h2 className="text-base font-bold text-gray-900">{selectedPublisher.name} — Links</h2>
                <p className="text-xs text-gray-400 mt-0.5">{publisherLinks.length} link{publisherLinks.length !== 1 ? 's' : ''}</p>
              </div>
              <button
                onClick={() => {
                  setLinkForm({ ...EMPTY_LINK_FORM, publisher_id: selectedPublisher.id })
                  setShowCreateModal(true)
                }}
                className="bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-xl text-xs font-semibold flex items-center gap-1.5"
              >
                <Plus size={14} /> Add Link
              </button>
            </div>

            {publisherLinks.length === 0 ? (
              <div className="text-center py-12 text-gray-400">
                <Link size={32} className="mx-auto mb-2 opacity-20" />
                <p className="text-sm">No links for this publisher</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 border-b border-gray-100">
                    <tr>
                      {['Name', 'Masked URL', 'Status', 'Clicks', 'Conv.', 'Today', 'Actions'].map(h => (
                        <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {publisherLinks.map(link => (
                      <tr key={link.id} className="hover:bg-gray-50/50">
                        <td className="px-4 py-3">
                          <p className="font-medium text-gray-900 text-sm">{link.name}</p>
                          <p className="text-[11px] text-gray-400 truncate max-w-[160px]">{link.destination_url}</p>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-1.5">
                            <code className="text-xs bg-gray-100 px-2 py-0.5 rounded font-mono text-gray-700 truncate max-w-[180px]">
                              {link.masked_url}
                            </code>
                            <CopyButton text={link.masked_url} label="" />
                          </div>
                        </td>
                        <td className="px-4 py-3"><StatusBadge status={link.status} /></td>
                        <td className="px-4 py-3 font-mono text-gray-700">{link.total_clicks.toLocaleString()}</td>
                        <td className="px-4 py-3 font-mono text-gray-700">{link.total_conversions.toLocaleString()}</td>
                        <td className="px-4 py-3">
                          <span className={`font-mono font-bold ${link.today_conversions > 0 ? 'text-emerald-600' : 'text-gray-400'}`}>
                            {link.today_conversions}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => {
                                const today = new Date().toISOString().split('T')[0]
                                setOverrideForm({
                                  date: today,
                                  publisher_id: link.publisher_id,
                                  link_id: link.id,
                                  manual_conversions: 0,
                                  reason: '',
                                })
                                setShowOverrideModal(true)
                              }}
                              title="Manual conversion override"
                              className="p-1.5 rounded text-gray-400 hover:text-amber-600 hover:bg-amber-50"
                            >
                              <Edit3 size={14} />
                            </button>
                            <button
                              onClick={() => handleDeleteLink(link)}
                              title="Delete"
                              className="p-1.5 rounded text-gray-400 hover:text-red-600 hover:bg-red-50"
                            >
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

            {/* Stats share section */}
            <div className="p-5 border-t border-gray-100 bg-blue-50/50">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-blue-900">White-Label Stats Link</p>
                  <p className="text-xs text-blue-600 mt-0.5">
                    Share a stats-only page with {selectedPublisher.name} — no internal data exposed
                  </p>
                </div>
                <button
                  onClick={() => generateStatsUrl(selectedPublisher.id, selectedPublisher.name)}
                  className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition-colors whitespace-nowrap"
                >
                  <Copy size={13} /> Generate & Copy
                </button>
              </div>
            </div>
          </div>
        )}

        {/* All links table (when no publisher selected) */}
        {!selectedPublisher && !loading && links.length > 0 && (
          <div className="bg-white rounded-2xl border border-gray-100 overflow-hidden">
            <div className="p-5 border-b border-gray-100">
              <h2 className="text-base font-bold text-gray-900">All Direct Links</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-100">
                  <tr>
                    {['Name / Publisher', 'Masked URL', 'Status', 'Clicks', 'Conv.', 'Actions'].map(h => (
                      <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {links.map(link => (
                    <tr key={link.id} className="hover:bg-gray-50/50">
                      <td className="px-4 py-3">
                        <p className="font-medium text-gray-900">{link.name}</p>
                        <p className="text-xs text-gray-400">{link.publisher_name || link.publisher_id.slice(-8)}</p>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1.5">
                          <code className="text-xs bg-gray-100 px-2 py-0.5 rounded font-mono text-gray-700 truncate max-w-[200px]">
                            {link.masked_url}
                          </code>
                          <CopyButton text={link.masked_url} label="" />
                        </div>
                      </td>
                      <td className="px-4 py-3"><StatusBadge status={link.status} /></td>
                      <td className="px-4 py-3 font-mono text-gray-700">{link.total_clicks.toLocaleString()}</td>
                      <td className="px-4 py-3 font-mono text-gray-700">{link.total_conversions.toLocaleString()}</td>
                      <td className="px-4 py-3">
                        <button
                          onClick={() => {
                            const today = new Date().toISOString().split('T')[0]
                            setOverrideForm({
                              date: today,
                              publisher_id: link.publisher_id,
                              link_id: link.id,
                              manual_conversions: 0,
                              reason: '',
                            })
                            setShowOverrideModal(true)
                          }}
                          className="p-1.5 rounded text-gray-400 hover:text-amber-600 hover:bg-amber-50"
                          title="Override"
                        >
                          <Edit3 size={14} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}


        {/* ── Create Link Modal ────────────────────────────────────────────── */}
        {showCreateModal && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-6 w-full max-w-lg shadow-2xl border border-gray-100 max-h-[92vh] overflow-y-auto">
              <h3 className="text-lg font-bold text-gray-900 mb-5">Create Direct Link</h3>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Link Name <span className="text-red-500">*</span></label>
                  <input value={linkForm.name} onChange={e => setLinkForm(p => ({ ...p, name: e.target.value }))}
                    placeholder="e.g. Campaign A — Publisher 1" className={inp} />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Publisher <span className="text-red-500">*</span></label>
                  <select value={linkForm.publisher_id} onChange={e => setLinkForm(p => ({ ...p, publisher_id: e.target.value }))} className={inp}>
                    <option value="">Select publisher…</option>
                    {publishers.map(p => (
                      <option key={p.id} value={p.id}>{p.name} ({p.email})</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Masked Domain <span className="text-red-500">*</span>
                    <span className="text-gray-400 font-normal ml-1">— no https://</span>
                  </label>
                  <input value={linkForm.masked_domain} onChange={e => setLinkForm(p => ({ ...p, masked_domain: e.target.value }))}
                    placeholder="click.yourdomain.com" className={inp} />
                  {linkForm.masked_domain && (
                    <p className="text-[11px] text-gray-400 mt-1">
                      URL: <code className="bg-gray-100 px-1 rounded">https://{linkForm.masked_domain}/#/slug</code>
                    </p>
                  )}
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Destination URL <span className="text-red-500">*</span></label>
                  <input value={linkForm.destination_url} onChange={e => setLinkForm(p => ({ ...p, destination_url: e.target.value }))}
                    placeholder="https://offer-network.com/track/xyz" className={inp} />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
                    <select value={linkForm.status} onChange={e => setLinkForm(p => ({ ...p, status: e.target.value as LinkFormData['status'] }))} className={inp}>
                      <option value="active">Active</option>
                      <option value="paused">Paused</option>
                      <option value="archived">Archived</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Daily Cap <span className="text-gray-400 font-normal">(0=∞)</span></label>
                    <input type="number" min={0} value={linkForm.daily_conversion_cap}
                      onChange={e => setLinkForm(p => ({ ...p, daily_conversion_cap: parseInt(e.target.value) || 0 }))} className={inp} />
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Notes</label>
                  <textarea value={linkForm.notes} onChange={e => setLinkForm(p => ({ ...p, notes: e.target.value }))}
                    rows={2} className={inp} />
                </div>
              </div>

              <div className="flex gap-3 mt-6">
                <button onClick={handleCreateLink} disabled={savingLink}
                  className="flex-1 bg-primary hover:bg-primary-dark text-white py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 disabled:bg-gray-300">
                  {savingLink ? <Spinner size={16} /> : 'Create Link'}
                </button>
                <button onClick={() => setShowCreateModal(false)}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50">
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── Manual Override Modal ─────────────────────────────────────────── */}
        {showOverrideModal && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-2xl border border-gray-100">
              <h3 className="text-lg font-bold text-gray-900 mb-2">Manual Conversion Override</h3>
              <p className="text-sm text-gray-500 mb-5">
                Override the conversion count for a specific date. This affects reporting only.
              </p>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Date <span className="text-red-500">*</span></label>
                  <input type="date" value={overrideForm.date}
                    onChange={e => setOverrideForm(p => ({ ...p, date: e.target.value }))} className={inp} />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Manual Conversions <span className="text-red-500">*</span></label>
                  <input type="number" min={0} value={overrideForm.manual_conversions}
                    onChange={e => setOverrideForm(p => ({ ...p, manual_conversions: parseInt(e.target.value) || 0 }))}
                    className={inp} />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Reason <span className="text-red-500">*</span></label>
                  <textarea rows={3} value={overrideForm.reason}
                    onChange={e => setOverrideForm(p => ({ ...p, reason: e.target.value }))}
                    placeholder="Explain the override reason…" className={inp} />
                </div>
              </div>

              <div className="flex gap-3 mt-6">
                <button onClick={handleOverrideSubmit} disabled={savingOverride}
                  className="flex-1 bg-amber-500 hover:bg-amber-600 text-white py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 disabled:bg-gray-300">
                  {savingOverride ? <Spinner size={16} /> : 'Apply Override'}
                </button>
                <button onClick={() => setShowOverrideModal(false)}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50">
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
