'use client'

import PublisherId from '@/components/shared/PublisherId'

import { useState, useEffect, useCallback } from 'react'
import {
  Edit3, Copy, RefreshCw,
  Plus, Link, ExternalLink, Share2, X, Link2, MousePointerClick, Target, Globe2, Settings2, History,
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
  stats_domain?: string
  preferences?: Partial<StatsPreferences>
  created_at?: string | null
}

interface Publisher {
  public_id?: string
  id: string
  name: string
  email: string
  role: string
  status: string
}

// One row of the admin-entered conversion history (editable / deletable)
interface ManualConversionRow {
  id: string
  date: string
  publisher_id: string
  publisher_name?: string
  link_id?: string | null
  link_name?: string
  conversions: number
  reason: string
  updated_at?: string | null
}

interface StatsPreferences {
  show_os: boolean
  show_country: boolean
  show_device: boolean
  show_clicks: boolean
  show_valid_clicks: boolean
  show_invalid_clicks: boolean
  show_impressions: boolean
  show_conversions: boolean
  show_cr: boolean
  show_daily_breakdown: boolean
  // Per-OS click breakdown toggles — whether the publisher sees each OS's clicks
  show_windows_clicks: boolean
  show_mac_clicks: boolean
  show_android_clicks: boolean
}

// Default column set: ONLY Windows valid clicks are shown to the publisher.
// The admin opts Mac / Android columns in per publisher via these toggles.
const DEFAULT_PREFS: StatsPreferences = {
  show_os: true,
  show_country: true,
  show_device: true,
  show_clicks: true,
  show_valid_clicks: true,
  show_invalid_clicks: false,
  show_impressions: true,
  show_conversions: true,
  show_cr: true,
  show_daily_breakdown: true,
  show_windows_clicks: true,
  show_mac_clicks: false,
  show_android_clicks: false,
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

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function DirectLinkStatsPage() {
  const { initialize } = useAuth()
  const [publishers, setPublishers] = useState<Publisher[]>([])
  const [links, setLinks] = useState<DirectLink[]>([])
  const [publisherDomains, setPublisherDomains] = useState<Record<string, any>>({})
  const [loading, setLoading] = useState(true)
  const [selectedPublisherId, setSelectedPublisherId] = useState<string>('')

  // Share stats modal
  const [shareModal, setShareModal] = useState<{ name: string; url: string; publisherId: string } | null>(null)
  const [generatingShare, setGeneratingShare] = useState<string | null>(null)
  // Regenerate public stats URL (expires the old link, keeps config & data)
  const [regenerating, setRegenerating] = useState<string | null>(null)

  // Stats domain config (white-label domain for share links)
  const [statsDomain, setStatsDomain] = useState('')
  const [savingDomain, setSavingDomain] = useState(false)
  const [cleaningUp, setCleaningUp] = useState(false)

  // Per-publisher stats-domain editor (fisherhub-style dedicated domain)
  const [pubDomainModal, setPubDomainModal] = useState<{ pubId: string; pubName: string; linkId: string; value: string } | null>(null)
  const [openingDomain, setOpeningDomain] = useState<string | null>(null)
  const [savingPubDomain, setSavingPubDomain] = useState(false)

  // Per-publisher stats-page preferences editor (what the pub sees on /public-stats)
  const [prefsModal, setPrefsModal] = useState<{ pubId: string; pubName: string; linkId: string; prefs: StatsPreferences } | null>(null)
  const [openingPrefs, setOpeningPrefs] = useState<string | null>(null)
  const [savingPrefs, setSavingPrefs] = useState(false)

  // Conversion history browser/editor (old conversions editable + deletable)
  const [historyModal, setHistoryModal] = useState<{ pubId: string; pubName: string } | null>(null)
  const [historyRows, setHistoryRows] = useState<ManualConversionRow[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [editingConversion, setEditingConversion] = useState<ManualConversionRow | null>(null)
  const [editConvValue, setEditConvValue] = useState(0)
  const [editConvReason, setEditConvReason] = useState('')
  const [savingConversion, setSavingConversion] = useState(false)
  // Add-new-conversion form (inside the history modal — works even when the
  // list is empty, so the publisher's card action is never a dead end)
  const [showAddConv, setShowAddConv] = useState(false)
  const [addConvDate, setAddConvDate] = useState(() => new Date().toISOString().split('T')[0])
  const [addConvValue, setAddConvValue] = useState(0)
  const [addConvReason, setAddConvReason] = useState('')
  const [addingConversion, setAddingConversion] = useState(false)

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
      // Load publishers, links, and domain info together
      const [pubResult, linksResult, domainsResult] = await Promise.allSettled([
        adminApi.getPublishers({ limit: 200 }),
        directLinkApi.getAll(),
        directLinkApi.getPublisherDomains(),
      ])

      // Backend's get_all_publishers already filters role=publisher in DB
      // Accept any result — no extra role filter needed
      const allPubs: Publisher[] =
        pubResult.status === 'fulfilled'
          ? (pubResult.value.data?.publishers ?? [])
          : []

      const allLinks: DirectLink[] =
        linksResult.status === 'fulfilled'
          ? (linksResult.value.data?.links ?? [])
          : []

      setPublishers(allPubs)
      setLinks(allLinks)

      // Process publisher domains
      if (domainsResult.status === 'fulfilled') {
        const domainsData = domainsResult.value.data?.publisher_domains ?? []
        const domainsMap: Record<string, any> = {}
        domainsData.forEach((pd: any) => {
          domainsMap[pd.publisher_id] = pd.domains
        })
        setPublisherDomains(domainsMap)
      }

      // Show a user-visible error if publishers failed to load
      if (pubResult.status === 'rejected') {
        const status = pubResult.reason?.response?.status
        const msg = pubResult.reason?.response?.data?.error
          || pubResult.reason?.response?.data?.detail
          || pubResult.reason?.message
          || 'Unknown error'
        console.error('Publishers API error:', status, msg)
        if (status !== 401) {
          // 401 = auth interceptor already redirects; don't double-toast
          toast.error(`Could not load publishers (${status ?? 'network error'})`)
        }
      }
      if (linksResult.status === 'rejected') {
        console.warn('Direct links API:', linksResult.reason?.response?.status)
      }
    } catch (err: any) {
      console.error('Unexpected loadData error:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  // Load saved stats domain setting
  useEffect(() => {
    adminApi.getStatsDomain()
      .then(res => { if (res.data?.domain) setStatsDomain(res.data.domain) })
      .catch(() => {})
  }, [])

  const saveStatsDomain = async () => {
    setSavingDomain(true)
    try {
      await adminApi.setStatsDomain(statsDomain.trim())
      setShareModal(null)
      toast.success('Stats domain saved — new share links will use this domain')
    } catch {
      toast.error('Failed to save stats domain')
    } finally {
      setSavingDomain(false)
    }
  }

  // ── Per-publisher dedicated stats domain (e.g. fisherhub.com) ─────────────
  const resolveStatsLink = async (publisherId: string): Promise<DirectLink> => {
    const res = await directLinkApi.ensurePublisherStatsLink(publisherId)
    return res.data.link
  }

  const openPubDomain = async (pub: { id: string; name: string }) => {
    setOpeningDomain(pub.id)
    try {
      const link = await resolveStatsLink(pub.id)
      setPubDomainModal({ pubId: pub.id, pubName: pub.name, linkId: link.id, value: link.stats_domain || '' })
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to load the stats domain')
    } finally {
      setOpeningDomain(null)
    }
  }

  const savePubDomain = async () => {
    if (!pubDomainModal) return
    setSavingPubDomain(true)
    try {
      await directLinkApi.update(pubDomainModal.linkId, { stats_domain: pubDomainModal.value.trim() })
      setShareModal(null)
      toast.success(pubDomainModal.value.trim()
        ? `Dedicated stats domain saved for ${pubDomainModal.pubName}`
        : 'Dedicated domain cleared — publisher falls back to the global stats domain')
      setPubDomainModal(null)
      loadData()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to save the stats domain')
    } finally {
      setSavingPubDomain(false)
    }
  }

  // ── Per-publisher stats preferences (what the pub sees on /public-stats) ──
  const openPrefs = async (pub: { id: string; name: string }) => {
    setOpeningPrefs(pub.id)
    try {
      const link = await resolveStatsLink(pub.id)
      setPrefsModal({
        pubId: pub.id,
        pubName: pub.name,
        linkId: link.id,
        prefs: { ...DEFAULT_PREFS, ...link.preferences },
      })
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to load stats preferences')
    } finally {
      setOpeningPrefs(null)
    }
  }

  const savePrefs = async () => {
    if (!prefsModal) return
    setSavingPrefs(true)
    try {
      await directLinkApi.update(prefsModal.linkId, { preferences: prefsModal.prefs })
      toast.success(`Stats preferences saved for ${prefsModal.pubName}`)
      setPrefsModal(null)
      loadData()
    } catch (err: any) {
      toast.error(err?.response?.data?.error || 'Failed to save preferences')
    } finally {
      setSavingPrefs(false)
    }
  }

  // ── Conversion history (old entries editable + deletable) ─────────────────
  const refreshHistory = async (pubId: string) => {
    const res = await directLinkApi.listManualConversions({ publisher_id: pubId })
    setHistoryRows(res.data?.conversions || [])
  }

  const openHistory = async (pub: { id: string; name: string }) => {
    setHistoryModal({ pubId: pub.id, pubName: pub.name })
    setHistoryLoading(true)
    setEditingConversion(null)
    setShowAddConv(false)
    try {
      await refreshHistory(pub.id)
    } catch (err: any) {
      console.error('Failed to load conversion history:', err)
      const errorMsg = err?.response?.data?.detail || err?.response?.data?.error || 'Failed to load conversion history'
      toast.error(errorMsg)
      setHistoryRows([])
    } finally {
      setHistoryLoading(false)
    }
  }

  const addConversion = async () => {
    if (!historyModal) return
    if (!addConvDate) { toast.error('Date is required'); return }
    if (addConvValue < 0) { toast.error('Conversions must be ≥ 0'); return }
    if (!addConvReason.trim()) { toast.error('Reason is required'); return }
    setAddingConversion(true)
    try {
      await directLinkApi.createManualConversion({
        date: addConvDate,
        publisher_id: historyModal.pubId,
        link_id: null,
        conversions: addConvValue,
        reason: addConvReason.trim(),
      })
      toast.success('Conversion entry added')
      setShowAddConv(false)
      setAddConvValue(0)
      setAddConvReason('')
      await refreshHistory(historyModal.pubId)
    } catch (err: any) {
      const errorMsg = err?.response?.data?.detail || err?.response?.data?.error || 'Failed to add the conversion entry'
      toast.error(errorMsg)
    } finally {
      setAddingConversion(false)
    }
  }

  const saveConversionEdit = async () => {
    if (!editingConversion) return
    if (editConvValue < 0) { toast.error('Conversions must be ≥ 0'); return }
    if (!editConvReason.trim()) { toast.error('Reason is required'); return }
    setSavingConversion(true)
    try {
      await directLinkApi.updateManualConversion(editingConversion.id, {
        conversions: editConvValue,
        reason: editConvReason.trim(),
      })
      toast.success('Conversion entry updated')
      setEditingConversion(null)
      // Refresh the open history list
      await refreshHistory(editingConversion.publisher_id)
    } catch (err: any) {
      const errorMsg = err?.response?.data?.detail || err?.response?.data?.error || 'Failed to update the conversion entry'
      toast.error(errorMsg)
    } finally {
      setSavingConversion(false)
    }
  }

  const deleteConversion = async (row: ManualConversionRow) => {
    try {
      await directLinkApi.deleteManualConversion(row.id)
      toast.success(`Conversion entry for ${row.date} deleted`)
      setHistoryRows(prev => prev.filter(r => r.id !== row.id))
    } catch (err: any) {
      const errorMsg = err?.response?.data?.detail || err?.response?.data?.error || 'Failed to delete the conversion entry'
      toast.error(errorMsg)
    }
  }

  // The selected publisher drives the white-label share section below.
  const selectedPublisher = publishers.find(p => p.id === selectedPublisherId)

  // Aggregated stats per publisher — only count active/paused links, not archived
  const publisherStats = publishers
    .map(pub => {
      const pubLinks = links.filter(l => l.publisher_id === pub.id)
      const activeLinks = pubLinks.filter(l => l.status !== 'archived')
      const totalClicks = activeLinks.reduce((s, l) => s + (l.total_clicks || 0), 0)
      const totalConversions = activeLinks.reduce((s, l) => s + (l.total_conversions || 0), 0)
      const todayConversions = activeLinks.reduce((s, l) => s + (l.today_conversions || 0), 0)
      return {
        ...pub,
        linkCount: activeLinks.length,  // only count active links
        totalLinks: pubLinks.length,     // total including archived
        hasLinks: pubLinks.length > 0,   // whether publisher has any links
        totalClicks,
        totalConversions,
        todayConversions,
        cr: totalClicks > 0 ? (totalConversions / totalClicks * 100) : 0,
      }
    })
    // Show ALL publishers regardless of whether they have links
    .sort((a, b) => {
      // Sort: publishers with links first, then by total clicks (desc), then by name
      if (a.hasLinks && !b.hasLinks) return -1
      if (!a.hasLinks && b.hasLinks) return 1
      if (a.totalClicks !== b.totalClicks) return b.totalClicks - a.totalClicks
      return a.name.localeCompare(b.name)
    })

  // Generate stats URL for publisher — resolves the active link, shows modal
  const generateStatsUrl = async (publisherId: string, publisherName: string) => {
    setGeneratingShare(publisherId)
    try {
      const link = await resolveStatsLink(publisherId)
      const res = await directLinkApi.shareStatsLink(link.id)
      const url = res.data?.stats_url
      if (url) {
        setShareModal({ name: publisherName, url, publisherId })
      } else {
        throw new Error('No URL returned')
      }
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.response?.data?.error
      toast.error(typeof detail === 'string' ? detail : 'Failed to generate stats link')
    } finally {
      setGeneratingShare(null)
    }
  }

  // Regenerate the public stats URL for a publisher's active link
  const regenerateStatsUrl = async (publisherId: string, publisherName: string) => {
    setRegenerating(publisherId)
    try {
      const link = await resolveStatsLink(publisherId)
      const res = await directLinkApi.regenerateStatsLink(link.id)
      const url = res.data?.stats_url
      if (url) {
        setShareModal({ name: publisherName, url, publisherId })
        toast.success('New link generated — the previous link has expired')
      } else {
        throw new Error('No URL returned')
      }
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.response?.data?.error
      toast.error(typeof detail === 'string' ? detail : 'Failed to regenerate link')
    } finally {
      setRegenerating(null)
    }
  }

  const inp = 'w-full px-4 py-2.5 border border-gray-200 rounded-xl text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary text-sm'

  return (
    <div className="flex min-h-screen bg-[#f8f9fb]">
      <Sidebar />
      <div className="flex-1 lg:ml-64 p-6 lg:p-8 min-w-0 overflow-x-hidden">

        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 pt-12 lg:pt-0">
          <div className="flex items-center gap-3.5">
            <div className="w-11 h-11 rounded-2xl bg-primary/10 border border-primary/15 flex items-center justify-center flex-shrink-0">
              <Link2 size={20} className="text-primary" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-gray-900 tracking-tight">Direct Link Stats</h1>
              <p className="text-gray-400 text-sm mt-0.5">
                Publisher statistics — clicks, conversions and white-label stats links
              </p>
            </div>
          </div>
        </div>

        {/* Stats domain config — white-label domain for share links */}
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5 mb-6">
          <div className="flex items-start gap-3.5 mb-4">
            <div className="w-9 h-9 rounded-xl bg-blue-50 border border-blue-100 flex items-center justify-center flex-shrink-0">
              <Globe2 size={16} className="text-blue-600" />
            </div>
            <div className="flex-1">
              <label className="block text-sm font-semibold text-gray-800">
                White-Label Stats Domain
              </label>
              <p className="text-xs text-gray-400 mt-0.5">
                When set, publisher share links use this domain instead of the admin panel domain.
                Point this domain&apos;s DNS to the same server, then enter it here.
              </p>
            </div>
          </div>
          <div className="flex flex-col sm:flex-row sm:items-end gap-4 sm:pl-[52px]">
            <div className="flex-1">
              <input
                value={statsDomain}
                onChange={e => setStatsDomain(e.target.value)}
                placeholder="stats.yournetwork.com  (no https://)"
                className={inp}
              />
              {statsDomain && (
                <p className="text-[11px] text-gray-400 mt-1.5">
                  Share links will look like:{' '}
                  <code className="bg-gray-100 px-1.5 py-0.5 rounded">
                    https://{statsDomain}/public-stats/…
                  </code>
                </p>
              )}
            </div>
            <button
              onClick={saveStatsDomain}
              disabled={savingDomain}
              className="px-5 py-2.5 bg-primary hover:bg-primary-dark text-white rounded-xl text-sm font-semibold flex items-center gap-2 whitespace-nowrap disabled:bg-gray-300 self-end"
            >
              {savingDomain ? <Spinner size={16} /> : 'Save Domain'}
            </button>
          </div>
        </div>

        {/* Summary cards — publisher-centric */}
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
          {[
            { label: 'Publishers', value: publisherStats.length.toLocaleString(), icon: Globe2, tone: 'text-blue-600', bg: 'bg-blue-50 border-blue-100' },
            { label: 'Total Clicks', value: links.reduce((s, l) => s + l.total_clicks, 0).toLocaleString(), icon: MousePointerClick, tone: 'text-indigo-600', bg: 'bg-indigo-50 border-indigo-100' },
            { label: 'Total Conversions', value: links.reduce((s, l) => s + l.total_conversions, 0).toLocaleString(), icon: Target, tone: 'text-emerald-600', bg: 'bg-emerald-50 border-emerald-100' },
          ].map((s, i) => (
            <div key={i} className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
              <div className="flex items-center gap-3 mb-3">
                <div className={`w-9 h-9 rounded-xl border flex items-center justify-center flex-shrink-0 ${s.bg}`}>
                  <s.icon size={16} className={s.tone} />
                </div>
                <span className="text-[11px] font-semibold uppercase tracking-wider text-gray-400">{s.label}</span>
              </div>
              <p className="text-2xl font-bold text-gray-900 tracking-tight">{s.value}</p>
            </div>
          ))}
        </div>
        
        {/* Date filter */}
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm px-4 py-3 mb-6 flex gap-3 items-center flex-wrap">
          <span className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider mr-1">Period</span>
          <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary" />
          <span className="text-gray-300">→</span>
          <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary" />
          <button onClick={loadData} className="px-3.5 py-2 border border-gray-200 rounded-xl text-sm hover:bg-gray-50 flex items-center gap-1.5 text-gray-600 font-medium">
            <RefreshCw size={14} /> Refresh
          </button>
        </div>

        {/* Publisher stats table */}
        {loading ? (
          <div className="flex justify-center py-20"><Spinner size={32} /></div>
        ) : publisherStats.length === 0 ? (
          <div className="text-center py-20 text-gray-400">
            <Link size={48} className="mx-auto mb-4 opacity-20" />
            <p className="text-base font-medium mb-2">No publishers yet</p>
            <p className="text-sm">Add a publisher to manage their stats and sharing options</p>
          </div>
        ) : (
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden mb-6">
            <div className="px-5 py-4 border-b border-gray-100">
              <h2 className="text-base font-bold text-gray-900">Publishers</h2>
              <p className="text-xs text-gray-400 mt-0.5">
                {publisherStats.length} publisher{publisherStats.length !== 1 ? 's' : ''} total
                {publisherStats.filter(p => p.hasLinks).length > 0 && 
                  ` · ${publisherStats.filter(p => p.hasLinks).length} with links`
                }
              </p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-gray-50 border-b border-gray-100">
                  <tr>
                    <th className="px-5 py-3 text-left text-[10px] font-semibold text-gray-500 uppercase tracking-wider">Publisher</th>
                    <th className="px-3 py-3 text-center text-[10px] font-semibold text-gray-500 uppercase tracking-wider">Status</th>
                    <th className="px-3 py-3 text-right text-[10px] font-semibold text-gray-500 uppercase tracking-wider">Clicks</th>
                    <th className="px-3 py-3 text-right text-[10px] font-semibold text-gray-500 uppercase tracking-wider">Conversions</th>
                    <th className="px-3 py-3 text-right text-[10px] font-semibold text-gray-500 uppercase tracking-wider">Today</th>
                    <th className="px-3 py-3 text-right text-[10px] font-semibold text-gray-500 uppercase tracking-wider">CR</th>
                    <th className="px-3 py-3 text-left text-[10px] font-semibold text-gray-500 uppercase tracking-wider">Domains</th>
                    <th className="px-3 py-3 text-center text-[10px] font-semibold text-gray-500 uppercase tracking-wider">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {publisherStats.map(pub => (
                    <tr
                      key={pub.id}
                      onClick={() => setSelectedPublisherId(prev => prev === pub.id ? '' : pub.id)}
                      className={`cursor-pointer transition-colors hover:bg-gray-50/70 ${
                        selectedPublisherId === pub.id ? 'bg-primary/5' : ''
                      }`}
                    >
                      {/* Publisher Info */}
                      <td className="px-5 py-4">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary/10 to-primary/5 border border-primary/10 flex items-center justify-center flex-shrink-0">
                            <span className="text-sm font-bold text-primary">{pub.name.charAt(0).toUpperCase()}</span>
                          </div>
                          <div className="min-w-0">
                            <p className="font-semibold text-gray-900 text-sm truncate max-w-[200px]">{pub.name}</p>
                            <p className="text-xs text-gray-400 truncate max-w-[200px]">{pub.email}</p>
                            <PublisherId publicId={pub.public_id} publisherId={pub.id} />
                          </div>
                        </div>
                      </td>
                      
                      {/* Status */}
                      <td className="px-3 py-4 text-center">
                        <StatusBadge status={pub.status} />
                      </td>
                      
                      {/* Total Clicks */}
                      <td className="px-3 py-4 text-right">
                        <span className="font-mono text-sm text-gray-700 font-semibold">{pub.totalClicks.toLocaleString()}</span>
                      </td>
                      
                      {/* Total Conversions */}
                      <td className="px-3 py-4 text-right">
                        <span className="font-mono text-sm text-gray-700 font-semibold">{pub.totalConversions.toLocaleString()}</span>
                      </td>
                      
                      {/* Today Conversions */}
                      <td className="px-3 py-4 text-right">
                        <span className={`inline-flex items-center justify-center min-w-[2rem] h-7 px-2 rounded-lg font-mono text-sm font-bold ${
                          pub.todayConversions > 0 
                            ? 'bg-emerald-50 border border-emerald-100 text-emerald-600' 
                            : 'bg-gray-50 border border-gray-100 text-gray-400'
                        }`}>
                          {pub.todayConversions}
                        </span>
                      </td>
                      
                      {/* Conversion Rate */}
                      <td className="px-3 py-4 text-right">
                        <span className={`font-mono text-sm font-bold ${
                          pub.cr >= 5 ? 'text-emerald-600' : pub.cr >= 2 ? 'text-amber-600' : 'text-gray-500'
                        }`}>
                          {pub.cr.toFixed(2)}%
                        </span>
                      </td>
                      
                      {/* Domain Stats */}
                      <td className="px-3 py-4">
                        {publisherDomains[pub.id] && publisherDomains[pub.id].total > 0 ? (
                          <div className="flex items-center gap-1.5 flex-wrap">
                            {publisherDomains[pub.id].anchor?.length > 0 && (
                              <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-indigo-50 border border-indigo-100">
                                <span className="text-[9px] font-semibold text-indigo-700 uppercase">A</span>
                                <span className="text-xs font-bold text-indigo-600">{publisherDomains[pub.id].anchor.length}</span>
                              </span>
                            )}
                            {publisherDomains[pub.id].inter?.length > 0 && (
                              <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-purple-50 border border-purple-100">
                                <span className="text-[9px] font-semibold text-purple-700 uppercase">I</span>
                                <span className="text-xs font-bold text-purple-600">{publisherDomains[pub.id].inter.length}</span>
                              </span>
                            )}
                            {publisherDomains[pub.id].prelander?.length > 0 && (
                              <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-teal-50 border border-teal-100">
                                <span className="text-[9px] font-semibold text-teal-700 uppercase">P</span>
                                <span className="text-xs font-bold text-teal-600">{publisherDomains[pub.id].prelander.length}</span>
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="text-xs text-gray-300">—</span>
                        )}
                      </td>
                      
                      {/* Actions */}
                      <td className="px-3 py-4">
                        <div className="flex items-center justify-center gap-1" onClick={e => e.stopPropagation()}>
                          <button
                            onClick={() => generateStatsUrl(pub.id, pub.name)}
                            disabled={generatingShare === pub.id}
                            title="Share stats link"
                            className="p-2 rounded-lg text-gray-400 hover:text-primary hover:bg-primary/5 border border-transparent hover:border-primary/20 transition-colors disabled:opacity-60"
                          >
                            {generatingShare === pub.id ? <Spinner size={14} /> : <Share2 size={14} />}
                          </button>
                          <button
                            onClick={() => openPrefs(pub)}
                            disabled={openingPrefs === pub.id}
                            title="Stats preferences"
                            className="p-2 rounded-lg text-gray-400 hover:text-primary hover:bg-primary/5 border border-transparent hover:border-primary/20 transition-colors disabled:opacity-40"
                          >
                            {openingPrefs === pub.id ? <Spinner size={14} /> : <Settings2 size={14} />}
                          </button>
                          <button
                            onClick={() => openPubDomain(pub)}
                            disabled={openingDomain === pub.id}
                            title="Dedicated stats domain"
                            className="p-2 rounded-lg text-gray-400 hover:text-blue-600 hover:bg-blue-50 border border-transparent hover:border-blue-100 transition-colors disabled:opacity-40"
                          >
                            {openingDomain === pub.id ? <Spinner size={14} /> : <Globe2 size={14} />}
                          </button>
                          <button
                            onClick={() => openHistory(pub)}
                            title="Conversion history"
                            className="p-2 rounded-lg text-gray-400 hover:text-amber-600 hover:bg-amber-50 border border-transparent hover:border-amber-100 transition-colors"
                          >
                            <History size={14} />
                          </button>
                          <button
                            onClick={() => regenerateStatsUrl(pub.id, pub.name)}
                            disabled={regenerating === pub.id}
                            title="Regenerate stats link"
                            className="p-2 rounded-lg text-gray-400 hover:text-primary hover:bg-primary/5 border border-transparent hover:border-primary/20 transition-colors disabled:opacity-60"
                          >
                            {regenerating === pub.id ? <Spinner size={14} /> : <RefreshCw size={14} />}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Selected publisher links table removed — Direct Link Stats tracks
            publisher stats, not individual links. Per-link rows, masked URLs
            and link CRUD are no longer part of this page. */}

        {/* Stats share section */}
        {selectedPublisher && (
          <div className="bg-white rounded-2xl border border-gray-100 overflow-hidden mb-6">
            <div className="p-5 border-t border-gray-100 bg-blue-50/60">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-xl bg-blue-100 border border-blue-200 flex items-center justify-center flex-shrink-0">
                    <Share2 size={16} className="text-blue-600" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-blue-900">White-Label Stats Link</p>
                    <p className="text-xs text-blue-600/80 mt-0.5">
                      Share a stats-only page with {selectedPublisher.name} — no internal data exposed.
                      Regenerating expires the previous URL immediately while keeping all settings and data.
                    </p>
                  </div>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => generateStatsUrl(selectedPublisher.id, selectedPublisher.name)}
                    className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition-colors whitespace-nowrap"
                  >
                    <Copy size={13} /> Generate &amp; Copy
                  </button>
                  <button
                    onClick={() => regenerateStatsUrl(selectedPublisher.id, selectedPublisher.name)}
                    disabled={regenerating === selectedPublisher.id}
                    title="Expire the current link and generate a new one"
                    className="border border-gray-200 bg-white text-gray-600 hover:bg-gray-50 px-4 py-2 rounded-xl text-xs font-semibold flex items-center gap-1.5 transition-colors whitespace-nowrap disabled:opacity-60"
                  >
                    {regenerating === selectedPublisher.id ? <Spinner size={13} /> : <RefreshCw size={13} />} Regenerate
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* All Direct Links section removed - publishers are displayed in the grid above */}


        {/* Share Stats Modal info update — domain config notice */}
        {/* ── Share Stats Modal ────────────────────────────────────────────── */}
        {shareModal && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-6 w-full max-w-lg shadow-2xl border border-gray-100">
              {/* Header */}
              <div className="flex items-center justify-between mb-5">
                <div>
                  <h3 className="text-lg font-bold text-gray-900">Publisher Stats Link</h3>
                  <p className="text-sm text-gray-400 mt-0.5">{shareModal.name}</p>
                </div>
                <button onClick={() => setShareModal(null)}
                  className="p-2 rounded-xl text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors">
                  <X size={18} />
                </button>
              </div>

              {/* Info */}
              <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 mb-5">
                <p className="text-sm font-semibold text-blue-900 mb-1">White-label stats link</p>
                <p className="text-xs text-blue-700">
                  This link shows only performance stats — no admin panel, no branding, no campaign or domain names exposed.
                  Regenerating the link expires the previous URL immediately while keeping all report settings and data.
                </p>
              </div>

              {/* URL display */}
              <div className="mb-5">
                <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Shareable URL</label>
                <div className="flex items-center gap-2 bg-gray-50 border border-gray-200 rounded-xl p-1">
                  <div className="flex-1 px-3 py-2 text-xs font-mono text-gray-700 break-all select-all min-w-0">
                    {shareModal.url.split('?')[0]}
                  </div>
                </div>
              </div>

              {/* Actions */}
              <div className="flex gap-3">
                <button
                  onClick={async () => {
                    try {
                      // Copy only the clean URL without query params
                      const cleanUrl = shareModal.url.split('?')[0]
                      await navigator.clipboard.writeText(cleanUrl)
                      toast.success('Link copied to clipboard!')
                    } catch {
                      toast.error('Copy failed — please select and copy manually')
                    }
                  }}
                  className="flex-1 bg-primary hover:bg-primary-dark text-white py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center gap-2"
                >
                  <Copy size={15} /> Copy Link
                </button>
                <a
                  href={shareModal.url.split('?')[0]}
                  onClick={async event => {
                    event.preventDefault()
                    const preview = window.open('about:blank', '_blank')
                    if (preview) preview.opener = null
                    try {
                      const link = await resolveStatsLink(shareModal.publisherId)
                      const res = await directLinkApi.shareStatsLink(link.id)
                      const url = res.data?.stats_url
                      if (!url) throw new Error('No URL returned')
                      setShareModal({ ...shareModal, url })
                      if (preview) preview.location.replace(url)
                      else toast.error('Allow popups to preview the stats page')
                    } catch {
                      preview?.close()
                      toast.error('Failed to load the current stats link')
                    }
                  }}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex-1 py-2.5 rounded-xl text-sm font-semibold border border-gray-200 text-gray-700 hover:bg-gray-50 flex items-center justify-center gap-2 transition-colors"
                >
                  <ExternalLink size={15} /> Preview
                </a>
                <button
                  onClick={async () => {
                    const pub = publishers.find(p => p.id === shareModal.publisherId)
                    if (!pub) { toast.error('Publisher not found'); return }
                    await regenerateStatsUrl(pub.id, pub.name)
                  }}
                  title="Expire this link and generate a new one — settings and data are kept"
                  className="px-4 py-2.5 rounded-xl text-sm font-medium border border-gray-200 text-gray-600 hover:bg-gray-50 flex items-center justify-center gap-2 transition-colors"
                >
                  <RefreshCw size={15} /> Regenerate
                </button>
              </div>

              <p className="text-xs text-gray-400 text-center mt-4">
                Anyone opening an expired link sees only “This statistics link has expired.”
              </p>
            </div>
          </div>
        )}

        {/* ── Per-Publisher Stats Domain Modal ─────────────────────────────── */}
        {pubDomainModal && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-2xl border border-gray-100">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-lg font-bold text-gray-900">Dedicated Stats Domain</h3>
                <button onClick={() => setPubDomainModal(null)}
                  className="p-2 rounded-xl text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors">
                  <X size={18} />
                </button>
              </div>
              <p className="text-sm text-gray-500 mb-5">
                Assign a unique white-label domain for <strong className="text-gray-800">{pubDomainModal.pubName}</strong>&apos;s
                public stats page. Leave empty to use the global stats domain.
              </p>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Stats Domain</label>
                  <input
                    value={pubDomainModal.value}
                    onChange={e => setPubDomainModal(p => p ? { ...p, value: e.target.value } : p)}
                    placeholder="e.g. fisherhub.com  (no https://)"
                    className={inp}
                  />
                  {pubDomainModal.value.trim() && (
                    <p className="text-[11px] text-gray-400 mt-1.5">
                      Share links will look like:{' '}
                      <code className="bg-gray-100 px-1.5 py-0.5 rounded">
                        https://{pubDomainModal.value.trim()}/public-stats/…
                      </code>
                    </p>
                  )}
                  <p className="text-[11px] text-gray-400 mt-2">
                    Point this domain&apos;s DNS to the same server. Saving it here assigns it to
                    this publisher&apos;s statistics. Other domain roles cannot serve this link.
                  </p>
                </div>
              </div>
              <div className="flex gap-3 mt-6">
                <button onClick={savePubDomain} disabled={savingPubDomain}
                  className="flex-1 bg-primary hover:bg-primary-dark text-white py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 disabled:bg-gray-300">
                  {savingPubDomain ? <Spinner size={16} /> : 'Save Domain'}
                </button>
                <button onClick={() => setPubDomainModal(null)}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50">
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── Per-Publisher Stats Preferences Modal ────────────────────────── */}
        {prefsModal && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-6 w-full max-w-lg shadow-2xl border border-gray-100 max-h-[92vh] overflow-y-auto">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-lg font-bold text-gray-900">Stats Page Preferences</h3>
                <button onClick={() => setPrefsModal(null)}
                  className="p-2 rounded-xl text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors">
                  <X size={18} />
                </button>
              </div>
              <p className="text-sm text-gray-500 mb-5">
                Choose exactly what <strong className="text-gray-800">{prefsModal.pubName}</strong> sees on their shared
                stats page. By default only the <strong>Windows Valid Clicks</strong> column is shown — enable the
                toggles below to also show Mac / Android columns.
              </p>
              <div className="border border-gray-200 rounded-xl p-4 bg-gray-50">
                <div className="grid grid-cols-1 gap-1">
                  {(
                    [
                      { key: 'show_impressions', label: 'Show Impressions' },
                      { key: 'show_clicks', label: 'Show Clicks' },
                      { key: 'show_windows_clicks', label: 'Show Windows Valid Clicks column (default ON)' },
                      { key: 'show_mac_clicks', label: 'Show Mac Valid Clicks column (opt-in)' },
                      { key: 'show_android_clicks', label: 'Show Android Valid Clicks column (opt-in)' },
                      { key: 'show_valid_clicks', label: 'Show Valid Clicks (Unique Wins)' },
                      { key: 'show_invalid_clicks', label: 'Show Invalid Clicks' },
                      { key: 'show_conversions', label: 'Show Conversions' },
                      { key: 'show_cr', label: 'Show Conversion Rate' },
                      { key: 'show_os', label: 'Show OS Statistics / filters' },
                      { key: 'show_country', label: 'Show Country Statistics' },
                      { key: 'show_device', label: 'Show Device Statistics' },
                      { key: 'show_daily_breakdown', label: 'Show Daily Breakdown Table' },
                    ] as { key: keyof StatsPreferences; label: string }[]
                  ).map(({ key, label }) => (
                    <label key={key} className="flex items-center justify-between gap-3 cursor-pointer py-1.5 px-2 rounded-lg hover:bg-white transition-colors">
                      <span className="text-sm text-gray-700">{label}</span>
                      <button
                        type="button"
                        onClick={() => setPrefsModal(p => p ? ({ ...p, prefs: { ...p.prefs, [key]: !p.prefs[key] } }) : p)}
                        className={`relative inline-flex h-5 w-9 flex-shrink-0 rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none ${
                          prefsModal.prefs[key] ? 'bg-primary' : 'bg-gray-200'
                        }`}
                      >
                        <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform duration-200 ${
                          prefsModal.prefs[key] ? 'translate-x-4' : 'translate-x-0'
                        }`} />
                      </button>
                    </label>
                  ))}
                </div>
              </div>
              <div className="flex gap-3 mt-6">
                <button onClick={savePrefs} disabled={savingPrefs}
                  className="flex-1 bg-primary hover:bg-primary-dark text-white py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 disabled:bg-gray-300">
                  {savingPrefs ? <Spinner size={16} /> : 'Save Preferences'}
                </button>
                <button onClick={() => setPrefsModal(null)}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50">
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── Conversion History Modal (old entries editable) ──────────────── */}
        {historyModal && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl w-full max-w-2xl shadow-2xl border border-gray-100 max-h-[92vh] flex flex-col">
              <div className="flex items-center justify-between p-5 border-b border-gray-100">
                <div>
                  <h3 className="text-lg font-bold text-gray-900">Conversion History</h3>
                  <p className="text-sm text-gray-400 mt-0.5">{historyModal.pubName} — entered conversions, newest first</p>
                </div>
                <div className="flex items-center gap-2">
                  {!showAddConv && (
                    <button
                      onClick={() => {
                        setShowAddConv(true)
                        setEditingConversion(null)
                        setAddConvDate(new Date().toISOString().split('T')[0])
                        setAddConvValue(0)
                        setAddConvReason('')
                      }}
                      className="flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-semibold bg-primary hover:bg-primary-dark text-white transition-colors"
                    >
                      <Plus size={14} /> Add Conversion
                    </button>
                  )}
                  <button onClick={() => { setHistoryModal(null); setShowAddConv(false) }}
                    className="p-2 rounded-xl text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors">
                    <X size={18} />
                  </button>
                </div>
              </div>

              {/* ── Add conversion form (works even when the list is empty) ── */}
              {showAddConv && (
                <div className="mx-5 mt-5 border border-gray-200 rounded-xl bg-gray-50 p-4">
                  <p className="text-sm font-semibold text-gray-800 mb-3">New conversion entry</p>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-1">Date</label>
                      <input type="date" value={addConvDate}
                        onChange={e => setAddConvDate(e.target.value)} className={inp} />
                    </div>
                    <div>
                      <label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-1">Conversions</label>
                      <input type="number" min={0} value={addConvValue}
                        onChange={e => setAddConvValue(parseInt(e.target.value) || 0)} className={inp} />
                    </div>
                  </div>
                  <div className="mt-3">
                    <label className="block text-[11px] font-semibold text-gray-500 uppercase tracking-wide mb-1">Reason</label>
                    <input value={addConvReason}
                      onChange={e => setAddConvReason(e.target.value)}
                      placeholder="e.g. Postback missed — entered manually"
                      className={inp} />
                  </div>
                  <div className="flex gap-2 mt-4">
                    <button onClick={addConversion} disabled={addingConversion}
                      className="px-4 py-2 rounded-xl text-xs font-semibold bg-primary hover:bg-primary-dark text-white disabled:bg-gray-300 flex items-center gap-1.5">
                      {addingConversion ? <><Spinner size={13} /> Saving…</> : 'Save Entry'}
                    </button>
                    <button onClick={() => setShowAddConv(false)}
                      className="px-4 py-2 rounded-xl text-xs text-gray-600 border border-gray-200 hover:bg-gray-50">
                      Cancel
                    </button>
                  </div>
                </div>
              )}

              <div className="overflow-y-auto flex-1">
                {historyLoading ? (
                  <div className="flex justify-center py-16"><Spinner size={28} /></div>
                ) : historyRows.length === 0 ? (
                  <div className="text-center py-16 text-gray-400">
                    <History size={36} className="mx-auto mb-3 opacity-20" />
                    <p className="text-sm">No conversion entries yet for this publisher</p>
                    <p className="text-xs mt-1 mb-4">Add one for any date — past or today.</p>
                    {!showAddConv && (
                      <button
                        onClick={() => {
                          setShowAddConv(true)
                          setAddConvDate(new Date().toISOString().split('T')[0])
                          setAddConvValue(0)
                          setAddConvReason('')
                        }}
                        className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold bg-primary hover:bg-primary-dark text-white transition-colors"
                      >
                        <Plus size={14} /> Add First Conversion
                      </button>
                    )}
                  </div>
                ) : (
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50 border-b border-gray-100 sticky top-0">
                      <tr>
                        {['Date', 'Conversions', 'Reason', ''].map(h => (
                          <th key={h} className="px-4 py-2.5 text-left text-[11px] font-semibold text-gray-500 uppercase tracking-wide whitespace-nowrap">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-50">
                      {historyRows.map(row => (
                        <tr key={row.id} className="hover:bg-gray-50/50">
                          {editingConversion?.id === row.id ? (
                            <>
                              <td className="px-4 py-3 text-gray-700 whitespace-nowrap">{formatDate(row.date)}</td>
                              <td className="px-4 py-3">
                                <input type="number" min={0} value={editConvValue}
                                  onChange={e => setEditConvValue(parseInt(e.target.value) || 0)}
                                  className="w-24 px-2.5 py-1.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20" />
                              </td>
                              <td className="px-4 py-3">
                                <input value={editConvReason}
                                  onChange={e => setEditConvReason(e.target.value)}
                                  placeholder="Reason…"
                                  className="w-full px-2.5 py-1.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary/20" />
                              </td>
                              <td className="px-4 py-3 whitespace-nowrap">
                                <button onClick={saveConversionEdit} disabled={savingConversion}
                                  className="px-2.5 py-1.5 rounded-lg text-xs font-semibold text-white bg-primary hover:bg-primary-dark disabled:opacity-60 mr-1.5">
                                  {savingConversion ? 'Saving…' : 'Save'}
                                </button>
                                <button onClick={() => setEditingConversion(null)}
                                  className="px-2.5 py-1.5 rounded-lg text-xs text-gray-500 border border-gray-200 hover:bg-gray-50">
                                  Cancel
                                </button>
                              </td>
                            </>
                          ) : (
                            <>
                              <td className="px-4 py-3 text-gray-700 whitespace-nowrap">{formatDate(row.date)}</td>
                              <td className="px-4 py-3 font-mono font-bold text-gray-900">{row.conversions.toLocaleString()}</td>
                              <td className="px-4 py-3 text-gray-500 text-xs max-w-[200px] truncate" title={row.reason}>{row.reason || '—'}</td>
                              <td className="px-4 py-3 whitespace-nowrap">
                                <button
                                  onClick={() => { setEditingConversion(row); setEditConvValue(row.conversions); setEditConvReason(row.reason || ''); setShowAddConv(false) }}
                                  title="Edit this conversion entry"
                                  className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-medium text-amber-700 bg-amber-50 border border-amber-200 hover:bg-amber-100 mr-1.5"
                                >
                                  <Edit3 size={12} /> Edit
                                </button>
                                <button
                                  onClick={() => deleteConversion(row)}
                                  title="Delete this conversion entry"
                                  className="p-1.5 rounded text-gray-400 hover:text-red-600 hover:bg-red-50"
                                >
                                  <X size={13} />
                                </button>
                              </td>
                            </>
                          )}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  )
}
