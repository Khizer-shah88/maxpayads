'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  Edit3, CheckCircle, Copy, RefreshCw,
  Plus, Trash2, Link, ExternalLink, Share2, X, Link2, MousePointerClick, Target, Globe2, Settings2, History,
} from 'lucide-react'
import { toast } from 'sonner'
import Sidebar from '@/components/shared/Sidebar'
import ConfirmDialog from '@/components/ui/ConfirmDialog'
import { StatusBadge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/loading'
import { adminApi, directLinkApi, statsProfileApi } from '@/lib/api'
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
  show_mac_clicks: true,
  show_android_clicks: true,
}

interface LinkFormData {
  name: string
  publisher_id: string
  status: 'active' | 'paused' | 'archived'
  daily_conversion_cap: number
  notes: string
  preferences: StatsPreferences
}

const EMPTY_LINK_FORM: LinkFormData = {
  name: '',
  publisher_id: '',
  status: 'active',
  daily_conversion_cap: 0,
  notes: '',
  preferences: { ...DEFAULT_PREFS },
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

  // Share stats modal
  const [shareModal, setShareModal] = useState<{ name: string; url: string } | null>(null)
  const [generatingShare, setGeneratingShare] = useState<string | null>(null)
  // Regenerate public stats URL (expires the old link, keeps config & data)
  const [regenerating, setRegenerating] = useState<string | null>(null)

  // Styled delete confirmations (replace native confirm())
  const [deleteLinkTarget, setDeleteLinkTarget] = useState<DirectLink | null>(null)
  const [deletingLink, setDeletingLink] = useState(false)
  const [deleteAllTarget, setDeleteAllTarget] = useState<{ name: string; count: number; ids: string[] } | null>(null)
  const [deletingAll, setDeletingAll] = useState(false)

  // Stats domain config (white-label domain for share links)
  const [statsDomain, setStatsDomain] = useState('')
  const [savingDomain, setSavingDomain] = useState(false)
  const [cleaningUp, setCleaningUp] = useState(false)

  // Per-publisher stats-domain editor (fisherhub-style dedicated domain)
  const [pubDomainModal, setPubDomainModal] = useState<{ pubId: string; pubName: string; value: string } | null>(null)
  const [savingPubDomain, setSavingPubDomain] = useState(false)

  // Per-publisher stats-page preferences editor (what the pub sees on /public-stats)
  const [prefsModal, setPrefsModal] = useState<{ pubId: string; pubName: string; linkId: string; prefs: StatsPreferences } | null>(null)
  const [savingPrefs, setSavingPrefs] = useState(false)

  // Conversion history browser/editor (old conversions editable + deletable)
  const [historyModal, setHistoryModal] = useState<{ pubId: string; pubName: string } | null>(null)
  const [historyRows, setHistoryRows] = useState<ManualConversionRow[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [editingConversion, setEditingConversion] = useState<ManualConversionRow | null>(null)
  const [editConvValue, setEditConvValue] = useState(0)
  const [editConvReason, setEditConvReason] = useState('')
  const [savingConversion, setSavingConversion] = useState(false)

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
      // Load both independently — one failure never blocks the other
      const [pubResult, linksResult] = await Promise.allSettled([
        adminApi.getPublishers({ limit: 200 }),
        directLinkApi.getAll(),
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

  // Auto-cleanup duplicate links on page load (runs silently)
  useEffect(() => {
    directLinkApi.cleanupDuplicateLinks().catch(() => {/* silent */})
  }, [])

  // Manual cleanup handler (with feedback)
  const handleCleanupDuplicates = async () => {
    setCleaningUp(true)
    try {
      const res = await directLinkApi.cleanupDuplicateLinks()
      const { links_archived, publishers_affected } = res.data
      if (links_archived > 0) {
        toast.success(`Archived ${links_archived} old link${links_archived !== 1 ? 's' : ''} across ${publishers_affected} publisher${publishers_affected !== 1 ? 's' : ''}`)
      } else {
        toast.success('Already clean — no duplicate links found')
      }
      loadData()
    } catch {
      toast.error('Cleanup failed')
    } finally {
      setCleaningUp(false)
    }
  }

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
      toast.success('Stats domain saved — new share links will use this domain')
    } catch {
      toast.error('Failed to save stats domain')
    } finally {
      setSavingDomain(false)
    }
  }

  // ── Per-publisher dedicated stats domain (e.g. fisherhub.com) ─────────────
  const openPubDomain = (pub: { id: string; name: string }) => {
    const link = links.find(l => l.publisher_id === pub.id && l.status !== 'archived')
    setPubDomainModal({ pubId: pub.id, pubName: pub.name, value: link?.stats_domain || '' })
  }

  const savePubDomain = async () => {
    if (!pubDomainModal) return
    setSavingPubDomain(true)
    try {
      const link = links.find(l => l.publisher_id === pubDomainModal.pubId && l.status !== 'archived')
      if (!link) { toast.error('No active link for this publisher'); return }
      await directLinkApi.update(link.id, { stats_domain: pubDomainModal.value.trim() })
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
  const openPrefs = (pub: { id: string; name: string }) => {
    const link = links.find(l => l.publisher_id === pub.id && l.status !== 'archived')
    if (!link) { toast.error('No active link for this publisher'); return }
    const current = link.preferences || {}
    setPrefsModal({
      pubId: pub.id,
      pubName: pub.name,
      linkId: link.id,
      prefs: { ...DEFAULT_PREFS, ...current },
    })
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
  const openHistory = async (pub: { id: string; name: string }) => {
    setHistoryModal({ pubId: pub.id, pubName: pub.name })
    setHistoryLoading(true)
    setEditingConversion(null)
    try {
      const res = await directLinkApi.listManualConversions({ publisher_id: pub.id })
      setHistoryRows(res.data?.conversions || [])
    } catch (err: any) {
      console.error('Failed to load conversion history:', err)
      const errorMsg = err?.response?.data?.detail || err?.response?.data?.error || 'Failed to load conversion history'
      toast.error(errorMsg)
      setHistoryRows([])
    } finally {
      setHistoryLoading(false)
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
      const res = await directLinkApi.listManualConversions({ publisher_id: editingConversion.publisher_id })
      setHistoryRows(res.data?.conversions || [])
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

  // Links for selected publisher — only active/paused for display
  const publisherLinks = selectedPublisherId
    ? links.filter(l => l.publisher_id === selectedPublisherId)
    : []

  // Active link for selected publisher (only 1 should exist)
  const activePublisherLinks = publisherLinks.filter(l => l.status !== 'archived')

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
        totalClicks,
        totalConversions,
        todayConversions,
        cr: totalClicks > 0 ? (totalConversions / totalClicks * 100) : 0,
      }
    })
    .filter(p => p.totalLinks > 0) // show publishers that have any links (including archived)

  // All publishers for the Create Link dropdown (regardless of existing links)
  const publisherDropdownList = publishers

  // Create link
  const handleCreateLink = async () => {
    if (!linkForm.name.trim()) { toast.error('Name is required'); return }
    if (!linkForm.publisher_id) { toast.error('Publisher is required'); return }

    setSavingLink(true)
    try {
      await directLinkApi.create({
        name: linkForm.name.trim(),
        publisher_id: linkForm.publisher_id,
        status: linkForm.status,
        daily_conversion_cap: Number(linkForm.daily_conversion_cap) || 0,
        notes: linkForm.notes.trim() || null,
        preferences: linkForm.preferences,
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

  // Delete link (invoked from the styled ConfirmDialog)
  const handleDeleteLink = async (link: DirectLink) => {
    setDeletingLink(true)
    try {
      await directLinkApi.delete(link.id)
      toast.success('Link deleted')
      setDeleteLinkTarget(null)
      loadData()
    } catch {
      toast.error('Delete failed')
    } finally {
      setDeletingLink(false)
    }
  }

  // Delete all links for a publisher (invoked from the styled ConfirmDialog)
  const handleDeleteAllLinks = async () => {
    if (!deleteAllTarget) return
    setDeletingAll(true)
    try {
      await Promise.all(deleteAllTarget.ids.map(id => directLinkApi.delete(id)))
      toast.success('Links deleted')
      setDeleteAllTarget(null)
      loadData()
    } catch {
      toast.error('Delete failed')
    } finally {
      setDeletingAll(false)
    }
  }

  // Manual override submit — writes to BOTH conversion override (for internal
  // reports) and manual conversions (for the publisher's public stats page)
  const handleOverrideSubmit = async () => {
    if (!overrideForm.reason.trim()) { toast.error('Reason is required'); return }
    if (overrideForm.manual_conversions < 0) { toast.error('Conversions must be ≥ 0'); return }
    setSavingOverride(true)
    try {
      await Promise.allSettled([
        directLinkApi.createManualOverride({
          date: overrideForm.date,
          publisher_id: overrideForm.publisher_id,
          link_id: overrideForm.link_id || undefined,
          manual_conversions: overrideForm.manual_conversions,
          reason: overrideForm.reason,
        }),
        directLinkApi.createManualConversion({
          date: overrideForm.date,
          publisher_id: overrideForm.publisher_id,
          link_id: overrideForm.link_id || null,
          conversions: overrideForm.manual_conversions,
          reason: overrideForm.reason,
        }),
      ])
      toast.success('Conversions added — they now appear on the publisher stats page')
      setShowOverrideModal(false)
      loadData()
    } catch (err: any) {
      const errorMsg = err?.response?.data?.detail || err?.response?.data?.error || 'Failed to apply override'
      toast.error(errorMsg)
    } finally {
      setSavingOverride(false)
    }
  }

  // Generate stats URL for publisher — resolves the active link, shows modal
  const generateStatsUrl = async (publisherId: string, publisherName: string) => {
    setGeneratingShare(publisherId)
    try {
      const res = await directLinkApi.generateStatsToken({ publisher_id: publisherId })
      const url = res.data?.stats_url
      if (url) {
        setShareModal({ name: publisherName, url })
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

  // Resolve the active link ID for a publisher (newest active/paused link)
  const activeLinkIdFor = (pubId: string): string | null => {
    const active = links
      .filter(l => l.publisher_id === pubId && (l.status === 'active' || l.status === 'paused'))
      .sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
    return active[0]?.id ?? null
  }

  // Regenerate the public stats URL for a publisher's active link
  const regenerateStatsUrl = async (publisherId: string, publisherName: string) => {
    const linkId = activeLinkIdFor(publisherId)
    if (!linkId) { toast.error('No active link for this publisher'); return }
    setRegenerating(publisherId)
    try {
      const res = await directLinkApi.regenerateStatsLink(linkId)
      const url = res.data?.stats_url
      if (url) {
        setShareModal({ name: publisherName, url })
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
                Create links per publisher — track clicks, conversions and share white-label stats
              </p>
            </div>
          </div>
          <div className="flex gap-2 self-start">
            <button
              onClick={handleCleanupDuplicates}
              disabled={cleaningUp}
              className="border border-gray-200 text-gray-600 hover:bg-gray-50 px-4 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2 disabled:opacity-60"
              title="Archive old links — keeps only the newest link per publisher"
            >
              {cleaningUp ? <Spinner size={16} /> : <RefreshCw size={16} />}
              Clean Duplicates
            </button>
            <button
              onClick={() => {
                setLinkForm({ ...EMPTY_LINK_FORM })
                setShowCreateModal(true)
              }}
              className="bg-primary hover:bg-primary-dark text-white px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2 shadow-sm"
            >
              <Plus size={18} /> Create Link
            </button>
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

        {/* Summary cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          {[
            { label: 'Total Links', value: links.length.toLocaleString(), icon: Link2, tone: 'text-primary', bg: 'bg-primary/10 border-primary/15' },
            { label: 'Publishers with Links', value: publisherStats.length.toLocaleString(), icon: Globe2, tone: 'text-blue-600', bg: 'bg-blue-50 border-blue-100' },
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
                    <p className="text-[10px] text-gray-400 uppercase font-semibold tracking-wider">Active Links</p>
                    <p className="text-base font-bold text-gray-900">{pub.linkCount}</p>
                  </div>
                  <div className="bg-gray-50 rounded-xl p-2.5 text-center">
                    <p className="text-[10px] text-gray-400 uppercase font-semibold tracking-wider">Today Conv.</p>
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

                <div className="flex gap-2 pt-2 border-t border-gray-100 flex-wrap">
                  <button
                    onClick={e => { e.stopPropagation(); generateStatsUrl(pub.id, pub.name) }}
                    disabled={generatingShare === pub.id}
                    className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs font-medium text-primary hover:bg-primary/5 border border-primary/20 transition-colors disabled:opacity-60"
                  >
                    {generatingShare === pub.id
                      ? <><Spinner size={12} /> Getting…</>
                      : <><Share2 size={12} /> Share Stats</>
                    }
                  </button>
                  <button
                    onClick={e => { e.stopPropagation(); openPrefs(pub) }}
                    disabled={!links.some(l => l.publisher_id === pub.id && l.status !== 'archived')}
                    title="Choose what this publisher sees on their stats page (OS columns, conversions, CR…)"
                    className="flex items-center justify-center p-1.5 rounded-lg text-gray-500 hover:text-primary hover:bg-primary/5 border border-gray-200 transition-colors disabled:opacity-40"
                  >
                    <Settings2 size={13} />
                  </button>
                  <button
                    onClick={e => { e.stopPropagation(); openPubDomain(pub) }}
                    disabled={!links.some(l => l.publisher_id === pub.id && l.status !== 'archived')}
                    title="Assign a dedicated white-label stats domain for this publisher"
                    className="flex items-center justify-center p-1.5 rounded-lg text-gray-500 hover:text-blue-600 hover:bg-blue-50 border border-gray-200 transition-colors disabled:opacity-40"
                  >
                    <Globe2 size={13} />
                  </button>
                  <button
                    onClick={e => { e.stopPropagation(); openHistory(pub) }}
                    title="View / edit / delete entered conversions (including old dates)"
                    className="flex items-center justify-center p-1.5 rounded-lg text-gray-500 hover:text-amber-600 hover:bg-amber-50 border border-gray-200 transition-colors"
                  >
                    <History size={13} />
                  </button>
                  <button
                    onClick={e => { e.stopPropagation(); regenerateStatsUrl(pub.id, pub.name) }}
                    disabled={regenerating === pub.id}
                    title="Generate a new stats URL — the old link expires immediately; settings and data are kept"
                    className="flex items-center justify-center p-1.5 rounded-lg text-gray-500 hover:text-primary hover:bg-primary/5 border border-gray-200 transition-colors disabled:opacity-60"
                  >
                    {regenerating === pub.id ? <Spinner size={13} /> : <RefreshCw size={13} />}
                  </button>
                  <button
                    onClick={e => {
                      e.stopPropagation()
                      const pubLinks = links.filter(l => l.publisher_id === pub.id)
                      if (pubLinks.length === 0) return
                      setDeleteAllTarget({
                        name: pub.name,
                        count: pubLinks.length,
                        ids: pubLinks.map(l => l.id),
                      })
                    }}
                    title="Delete all links for this publisher"
                    className="flex items-center justify-center p-1.5 rounded-lg text-red-400 hover:text-red-600 hover:bg-red-50 border border-red-100 transition-colors"
                  >
                    <Trash2 size={13} />
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
                <p className="text-xs text-gray-400 mt-0.5">
                  {activePublisherLinks.length} active
                  {publisherLinks.length > activePublisherLinks.length
                    ? ` · ${publisherLinks.length - activePublisherLinks.length} archived`
                    : ''}
                </p>
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
                      <tr key={link.id} className={`hover:bg-gray-50/50 ${link.status === 'archived' ? 'opacity-40' : ''}`}>
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
          </div>
        )}

        {/* ── Styled delete confirmations ──────────────────────────────────── */}
        <ConfirmDialog
          open={deleteLinkTarget !== null}
          title="Delete Link"
          message={<>Delete link <strong className="text-gray-900">{deleteLinkTarget?.name}</strong>? The link URL will stop working immediately. This cannot be undone.</>}
          confirmLabel="Delete Link"
          loading={deletingLink}
          onConfirm={() => { if (deleteLinkTarget) handleDeleteLink(deleteLinkTarget) }}
          onCancel={() => setDeleteLinkTarget(null)}
        />
        <ConfirmDialog
          open={deleteAllTarget !== null}
          title="Delete All Links"
          message={<>Delete all <strong className="text-gray-900">{deleteAllTarget?.count}</strong> link{deleteAllTarget?.count !== 1 ? 's' : ''} for <strong className="text-gray-900">{deleteAllTarget?.name}</strong>? This cannot be undone.</>}
          confirmLabel="Delete All"
          loading={deletingAll}
          onConfirm={handleDeleteAllLinks}
          onCancel={() => setDeleteAllTarget(null)}
        />

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
                    {publisherDropdownList.map(p => (
                      <option key={p.id} value={p.id}>{p.name} ({p.email})</option>
                    ))}
                  </select>
                  {publisherDropdownList.length === 0 && (
                    <p className="text-xs text-amber-600 mt-1">
                      No publishers found. Create publishers first from the Publishers page.
                    </p>
                  )}
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

                {/* ── Stats Preferences ── */}
                <div className="border border-gray-200 rounded-xl p-4 bg-gray-50">
                  <p className="text-sm font-semibold text-gray-800 mb-3">Stats Page Preferences</p>
                  <p className="text-xs text-gray-400 mb-4">Control what the publisher sees on their shared stats page.</p>
                  <div className="grid grid-cols-1 gap-2">
                    {(
                      [
                        { key: 'show_impressions',     label: 'Show Impressions' },
                        { key: 'show_clicks',          label: 'Show Clicks' },
                        { key: 'show_windows_clicks',  label: 'Show Windows Clicks' },
                        { key: 'show_mac_clicks',      label: 'Show Mac Clicks' },
                        { key: 'show_android_clicks',  label: 'Show Android Clicks' },
                        { key: 'show_valid_clicks',    label: 'Show Valid Clicks (Unique Wins)' },
                        { key: 'show_invalid_clicks',  label: 'Show Invalid Clicks' },
                        { key: 'show_conversions',     label: 'Show Conversions' },
                        { key: 'show_cr',              label: 'Show Conversion Rate' },
                        { key: 'show_os',              label: 'Show OS Statistics' },
                        { key: 'show_country',         label: 'Show Country Statistics' },
                        { key: 'show_device',          label: 'Show Device Statistics' },
                        { key: 'show_daily_breakdown', label: 'Show Daily Breakdown Table' },
                      ] as { key: keyof StatsPreferences; label: string }[]
                    ).map(({ key, label }) => (
                      <label key={key} className="flex items-center justify-between gap-3 cursor-pointer py-1.5 px-2 rounded-lg hover:bg-white transition-colors">
                        <span className="text-sm text-gray-700">{label}</span>
                        <button
                          type="button"
                          onClick={() => setLinkForm(p => ({
                            ...p,
                            preferences: { ...p.preferences, [key]: !p.preferences[key] }
                          }))}
                          className={`relative inline-flex h-5 w-9 flex-shrink-0 rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none ${
                            linkForm.preferences[key] ? 'bg-primary' : 'bg-gray-200'
                          }`}
                        >
                          <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform duration-200 ${
                            linkForm.preferences[key] ? 'translate-x-4' : 'translate-x-0'
                          }`} />
                        </button>
                      </label>
                    ))}
                  </div>
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
                    {shareModal.url}
                  </div>
                </div>
              </div>

              {/* Actions */}
              <div className="flex gap-3">
                <button
                  onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(shareModal.url)
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
                  href={shareModal.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex-1 py-2.5 rounded-xl text-sm font-semibold border border-gray-200 text-gray-700 hover:bg-gray-50 flex items-center justify-center gap-2 transition-colors"
                >
                  <ExternalLink size={15} /> Preview
                </a>
                <button
                  onClick={async () => {
                    const pub = publishers.find(p => p.name === shareModal.name)
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
                    Point this domain&apos;s DNS to the same server and make sure it is listed in
                    the portal/infra exemptions (public-stats paths are already exempt from the portal gate).
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
                stats page. OS toggles control the Valid Windows / Valid Mac / Valid Android columns.
              </p>
              <div className="border border-gray-200 rounded-xl p-4 bg-gray-50">
                <div className="grid grid-cols-1 gap-1">
                  {(
                    [
                      { key: 'show_impressions', label: 'Show Impressions' },
                      { key: 'show_clicks', label: 'Show Clicks' },
                      { key: 'show_windows_clicks', label: 'Show Windows Valid Clicks column' },
                      { key: 'show_mac_clicks', label: 'Show Mac Valid Clicks column' },
                      { key: 'show_android_clicks', label: 'Show Android Valid Clicks column' },
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
                <button onClick={() => setHistoryModal(null)}
                  className="p-2 rounded-xl text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors">
                  <X size={18} />
                </button>
              </div>

              <div className="overflow-y-auto flex-1">
                {historyLoading ? (
                  <div className="flex justify-center py-16"><Spinner size={28} /></div>
                ) : historyRows.length === 0 ? (
                  <div className="text-center py-16 text-gray-400">
                    <History size={36} className="mx-auto mb-3 opacity-20" />
                    <p className="text-sm">No conversion entries yet for this publisher</p>
                    <p className="text-xs mt-1">Use the ✏️ button on a link row to add conversions for any date.</p>
                  </div>
                ) : (
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50 border-b border-gray-100 sticky top-0">
                      <tr>
                        {['Date', 'Link', 'Conversions', 'Reason', ''].map(h => (
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
                              <td className="px-4 py-3 text-gray-500 text-xs">{row.link_name || 'All Links'}</td>
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
                              <td className="px-4 py-3 text-gray-500 text-xs max-w-[120px] truncate">{row.link_name || 'All Links'}</td>
                              <td className="px-4 py-3 font-mono font-bold text-gray-900">{row.conversions.toLocaleString()}</td>
                              <td className="px-4 py-3 text-gray-500 text-xs max-w-[200px] truncate" title={row.reason}>{row.reason || '—'}</td>
                              <td className="px-4 py-3 whitespace-nowrap">
                                <button
                                  onClick={() => { setEditingConversion(row); setEditConvValue(row.conversions); setEditConvReason(row.reason || '') }}
                                  title="Edit this conversion entry"
                                  className="p-1.5 rounded text-gray-400 hover:text-amber-600 hover:bg-amber-50 mr-1"
                                >
                                  <Edit3 size={13} />
                                </button>
                                <button
                                  onClick={() => deleteConversion(row)}
                                  title="Delete this conversion entry"
                                  className="p-1.5 rounded text-gray-400 hover:text-red-600 hover:bg-red-50"
                                >
                                  <Trash2 size={13} />
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
