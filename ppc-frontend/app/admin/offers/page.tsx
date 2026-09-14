'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { Plus, Edit, Trash2, Search, ChevronDown, X, Users, Globe, Monitor, Smartphone, Apple, Lock } from 'lucide-react'
import { toast } from 'sonner'
import Sidebar from '@/components/shared/Sidebar'
import ConfirmDialog from '@/components/ui/ConfirmDialog'
import DataTable from '@/components/tables/DataTable'
import { StatusBadge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/loading'
import { offerApi, adminApi, campaignApi } from '@/lib/api'
import { useAuth } from '@/lib/hooks/useAuth'
import type { Offer, Publisher } from '@/types'

/* ─── Constants ─── */
const COUNTRIES = [
  { code: 'US', label: 'United States', flag: '\u{1F1FA}\u{1F1F8}' },
  { code: 'GB', label: 'United Kingdom', flag: '\u{1F1EC}\u{1F1E7}' },
  { code: 'CA', label: 'Canada', flag: '\u{1F1E8}\u{1F1E6}' },
  { code: 'AU', label: 'Australia', flag: '\u{1F1E6}\u{1F1FA}' },
  { code: 'DE', label: 'Germany', flag: '\u{1F1E9}\u{1F1EA}' },
  { code: 'FR', label: 'France', flag: '\u{1F1EB}\u{1F1F7}' },
  { code: 'IT', label: 'Italy', flag: '\u{1F1EE}\u{1F1F9}' },
  { code: 'ES', label: 'Spain', flag: '\u{1F1EA}\u{1F1F8}' },
  { code: 'NL', label: 'Netherlands', flag: '\u{1F1F3}\u{1F1F1}' },
  { code: 'SE', label: 'Sweden', flag: '\u{1F1F8}\u{1F1EA}' },
  { code: 'NO', label: 'Norway', flag: '\u{1F1F3}\u{1F1F4}' },
  { code: 'DK', label: 'Denmark', flag: '\u{1F1E9}\u{1F1F0}' },
  { code: 'FI', label: 'Finland', flag: '\u{1F1EB}\u{1F1EE}' },
  { code: 'CH', label: 'Switzerland', flag: '\u{1F1E8}\u{1F1ED}' },
  { code: 'AT', label: 'Austria', flag: '\u{1F1E6}\u{1F1F9}' },
  { code: 'BE', label: 'Belgium', flag: '\u{1F1E7}\u{1F1EA}' },
  { code: 'IE', label: 'Ireland', flag: '\u{1F1EE}\u{1F1EA}' },
  { code: 'PT', label: 'Portugal', flag: '\u{1F1F5}\u{1F1F9}' },
  { code: 'PL', label: 'Poland', flag: '\u{1F1F5}\u{1F1F1}' },
  { code: 'CZ', label: 'Czech Republic', flag: '\u{1F1E8}\u{1F1FF}' },
  { code: 'RO', label: 'Romania', flag: '\u{1F1F7}\u{1F1F4}' },
  { code: 'HU', label: 'Hungary', flag: '\u{1F1ED}\u{1F1FA}' },
  { code: 'GR', label: 'Greece', flag: '\u{1F1EC}\u{1F1F7}' },
  { code: 'JP', label: 'Japan', flag: '\u{1F1EF}\u{1F1F5}' },
  { code: 'KR', label: 'South Korea', flag: '\u{1F1F0}\u{1F1F7}' },
  { code: 'IN', label: 'India', flag: '\u{1F1EE}\u{1F1F3}' },
  { code: 'BR', label: 'Brazil', flag: '\u{1F1E7}\u{1F1F7}' },
  { code: 'MX', label: 'Mexico', flag: '\u{1F1F2}\u{1F1FD}' },
  { code: 'AR', label: 'Argentina', flag: '\u{1F1E6}\u{1F1F7}' },
  { code: 'CL', label: 'Chile', flag: '\u{1F1E8}\u{1F1F1}' },
  { code: 'CO', label: 'Colombia', flag: '\u{1F1E8}\u{1F1F4}' },
  { code: 'ZA', label: 'South Africa', flag: '\u{1F1FF}\u{1F1E6}' },
  { code: 'NG', label: 'Nigeria', flag: '\u{1F1F3}\u{1F1EC}' },
  { code: 'KE', label: 'Kenya', flag: '\u{1F1F0}\u{1F1EA}' },
  { code: 'EG', label: 'Egypt', flag: '\u{1F1EA}\u{1F1EC}' },
  { code: 'SA', label: 'Saudi Arabia', flag: '\u{1F1F8}\u{1F1E6}' },
  { code: 'AE', label: 'UAE', flag: '\u{1F1E6}\u{1F1EA}' },
  { code: 'TR', label: 'Turkey', flag: '\u{1F1F9}\u{1F1F7}' },
  { code: 'RU', label: 'Russia', flag: '\u{1F1F7}\u{1F1FA}' },
  { code: 'UA', label: 'Ukraine', flag: '\u{1F1FA}\u{1F1E6}' },
  { code: 'PK', label: 'Pakistan', flag: '\u{1F1F5}\u{1F1F0}' },
  { code: 'BD', label: 'Bangladesh', flag: '\u{1F1E7}\u{1F1E9}' },
  { code: 'ID', label: 'Indonesia', flag: '\u{1F1EE}\u{1F1E9}' },
  { code: 'MY', label: 'Malaysia', flag: '\u{1F1F2}\u{1F1FE}' },
  { code: 'TH', label: 'Thailand', flag: '\u{1F1F9}\u{1F1ED}' },
  { code: 'VN', label: 'Vietnam', flag: '\u{1F1FB}\u{1F1F3}' },
  { code: 'PH', label: 'Philippines', flag: '\u{1F1F5}\u{1F1ED}' },
  { code: 'SG', label: 'Singapore', flag: '\u{1F1F8}\u{1F1EC}' },
  { code: 'NZ', label: 'New Zealand', flag: '\u{1F1F3}\u{1F1FF}' },
  { code: 'IL', label: 'Israel', flag: '\u{1F1EE}\u{1F1F1}' },
  { code: 'CN', label: 'China', flag: '\u{1F1E8}\u{1F1F3}' },
  { code: 'TW', label: 'Taiwan', flag: '\u{1F1F9}\u{1F1FC}' },
  { code: 'HK', label: 'Hong Kong', flag: '\u{1F1ED}\u{1F1F0}' },
  { code: 'PE', label: 'Peru', flag: '\u{1F1F5}\u{1F1EA}' },
  { code: 'EC', label: 'Ecuador', flag: '\u{1F1EA}\u{1F1E8}' },
  { code: 'VE', label: 'Venezuela', flag: '\u{1F1FB}\u{1F1EA}' },
  { code: 'MA', label: 'Morocco', flag: '\u{1F1F2}\u{1F1E6}' },
  { code: 'GH', label: 'Ghana', flag: '\u{1F1EC}\u{1F1ED}' },
  { code: 'TZ', label: 'Tanzania', flag: '\u{1F1F9}\u{1F1FF}' },
  { code: 'ET', label: 'Ethiopia', flag: '\u{1F1EA}\u{1F1F9}' },
  { code: 'LK', label: 'Sri Lanka', flag: '\u{1F1F1}\u{1F1F0}' },
  { code: 'NP', label: 'Nepal', flag: '\u{1F1F3}\u{1F1F5}' },
  { code: 'QA', label: 'Qatar', flag: '\u{1F1F6}\u{1F1E6}' },
  { code: 'KW', label: 'Kuwait', flag: '\u{1F1F0}\u{1F1FC}' },
  { code: 'BH', label: 'Bahrain', flag: '\u{1F1E7}\u{1F1ED}' },
  { code: 'OM', label: 'Oman', flag: '\u{1F1F4}\u{1F1F2}' },
  { code: 'JO', label: 'Jordan', flag: '\u{1F1EF}\u{1F1F4}' },
  { code: 'LB', label: 'Lebanon', flag: '\u{1F1F1}\u{1F1E7}' },
  { code: 'IQ', label: 'Iraq', flag: '\u{1F1EE}\u{1F1F6}' },
  { code: 'HR', label: 'Croatia', flag: '\u{1F1ED}\u{1F1F7}' },
  { code: 'RS', label: 'Serbia', flag: '\u{1F1F7}\u{1F1F8}' },
  { code: 'BG', label: 'Bulgaria', flag: '\u{1F1E7}\u{1F1EC}' },
  { code: 'SK', label: 'Slovakia', flag: '\u{1F1F8}\u{1F1F0}' },
  { code: 'LT', label: 'Lithuania', flag: '\u{1F1F1}\u{1F1F9}' },
  { code: 'LV', label: 'Latvia', flag: '\u{1F1F1}\u{1F1FB}' },
  { code: 'EE', label: 'Estonia', flag: '\u{1F1EA}\u{1F1EA}' },
  { code: 'SI', label: 'Slovenia', flag: '\u{1F1F8}\u{1F1EE}' },
]

// OS targets the routing engine can actually distinguish. Linux visitors are
// normalized to "windows" in the backend os_map, so a standalone "linux" target
// could never match — it is intentionally omitted.
const OS_OPTIONS = [
  { key: 'windows', label: 'Windows', icon: Monitor },
  { key: 'mac', label: 'Mac / iOS', icon: Apple },
  { key: 'android', label: 'Android', icon: Smartphone },
]

/* ─── Reusable Multi-Select Dropdown ─── */
function MultiSelect({ label, items, selected, onChange, renderItem, searchable = true, allLabel = 'All' }: {
  label: string
  items: { key: string; label: string; extra?: string }[]
  selected: string[]
  onChange: (val: string[]) => void
  renderItem?: (item: { key: string; label: string; extra?: string }, isSelected: boolean) => React.ReactNode
  searchable?: boolean
  allLabel?: string
}) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) { setOpen(false); setSearch('') }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const filtered = items.filter(i =>
    i.label.toLowerCase().includes(search.toLowerCase()) ||
    i.key.toLowerCase().includes(search.toLowerCase()) ||
    (i.extra || '').toLowerCase().includes(search.toLowerCase())
  )

  const isAll = selected.length === 0
  const toggle = (key: string) => onChange(selected.includes(key) ? selected.filter(k => k !== key) : [...selected, key])
  const selectAll = () => onChange([])
  const clearAll = () => onChange([])

  return (
    <div ref={ref} className="relative">
      <div className="flex items-center justify-between mb-1">
        <label className="block text-sm font-medium text-gray-700">{label}</label>
        {selected.length > 0 && (
          <button type="button" onClick={selectAll} className="text-[11px] text-primary font-semibold hover:underline">Reset to All</button>
        )}
      </div>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-2.5 border border-gray-200 rounded-xl text-sm bg-white hover:border-gray-300 focus:outline-none focus:ring-2 focus:ring-primary/20 focus:border-primary transition-all text-left"
      >
        <span className={isAll ? 'text-gray-500' : 'text-gray-900'}>
          {isAll ? `${allLabel}` : `${selected.length} selected`}
        </span>
        <ChevronDown size={16} className={`text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute z-50 mt-1 w-full bg-white border border-gray-200 rounded-xl shadow-2xl overflow-hidden">
          {searchable && (
            <div className="p-2 border-b border-gray-100">
              <div className="relative">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
                <input
                  type="text"
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  placeholder="Search..."
                  className="w-full pl-8 pr-3 py-2 text-sm border border-gray-100 rounded-lg focus:outline-none focus:ring-1 focus:ring-primary/20"
                  autoFocus
                />
              </div>
            </div>
          )}
          <div className="overflow-y-auto" style={{ maxHeight: '240px' }}>
            {/* All option */}
            <button
              type="button"
              onClick={selectAll}
              className={`w-full flex items-center gap-3 px-4 py-2.5 text-left text-sm border-b border-gray-50 transition-colors ${
                isAll ? 'bg-primary/5 text-primary font-medium' : 'text-gray-700 hover:bg-gray-50'
              }`}
            >
              <input type="checkbox" checked={isAll} readOnly className="w-4 h-4 rounded border-gray-300 accent-primary pointer-events-none" />
              <span className="font-medium">{allLabel}</span>
            </button>
            {filtered.map(item => {
              const isSel = selected.includes(item.key)
              return (
                <button
                  key={item.key}
                  type="button"
                  onClick={() => toggle(item.key)}
                  className={`w-full flex items-center gap-3 px-4 py-2 text-left text-sm border-b border-gray-50 transition-colors ${
                    isSel ? 'bg-red-50 text-primary font-medium' : 'text-gray-700 hover:bg-gray-50'
                  }`}
                >
                  <input type="checkbox" checked={isSel} readOnly className="w-4 h-4 rounded border-gray-300 accent-primary pointer-events-none" />
                  {renderItem ? renderItem(item, isSel) : (
                    <>
                      <span className="flex-1">{item.label}</span>
                      {item.extra && <span className="text-[11px] text-gray-400 font-mono">{item.extra}</span>}
                    </>
                  )}
                </button>
              )
            })}
            {filtered.length === 0 && (
              <div className="p-4 text-center text-sm text-gray-400">No results</div>
            )}
          </div>
        </div>
      )}

      {/* Selected tags */}
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-2">
          {selected.slice(0, 10).map(key => {
            const item = items.find(i => i.key === key)
            return (
              <span key={key} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg text-xs font-medium bg-red-50 text-primary border border-red-100 group">
                {item?.label || key}
                <button type="button" onClick={() => toggle(key)} className="ml-0.5 opacity-50 group-hover:opacity-100 hover:text-red-800">
                  <X size={11} />
                </button>
              </span>
            )
          })}
          {selected.length > 10 && (
            <span className="inline-flex items-center px-2 py-0.5 rounded-lg text-xs font-medium bg-gray-100 text-gray-500">+{selected.length - 10} more</span>
          )}
        </div>
      )}
    </div>
  )
}

/* ─── Main Page ─── */
interface DeviceCampaign {
  id: string
  name: string
  device_os: string
}

const DEVICE_ICONS_MAP: Record<string, any> = {
  global: Globe,
  windows: Monitor,
  mac: Apple,
  android: Smartphone,
}

interface OfferForm {
  name: string
  offer_url: string
  password: string
  status: string
  cpc: string
  campaign_id: string
  publisher_ids: string[]
  website_ids: string[]
  os_types: string[]
  country_codes: string[]
  direct_redirect_mode: boolean
}

const emptyForm = (): OfferForm => ({
  name: '', offer_url: '', password: '', status: 'active', cpc: '0.0',
  campaign_id: '',
  publisher_ids: [], website_ids: [], os_types: [], country_codes: [], direct_redirect_mode: false,
})

/* Validates URL: allows any non-email string, auto-prepends https:// if no protocol. */
function isValidHttpUrl(value: string): boolean {
  const v = (value || '').trim()
  if (!v) return false
  // Reject email addresses
  if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)) return false
  // Accept anything that looks like a domain/path (protocol will be auto-added on save)
  return v.length > 3
}

export default function OffersPage() {
  const { initialize } = useAuth()
  const [offers, setOffers] = useState<Offer[]>([])
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState<'create' | 'edit' | null>(null)
  const [editId, setEditId] = useState<string | null>(null)
  const [form, setForm] = useState<OfferForm>(emptyForm())
  const [saving, setSaving] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<Offer | null>(null)
  const [deleting, setDeleting] = useState(false)

  // Loaded data for selectors
  const [publishers, setPublishers] = useState<Publisher[]>([])
  const [websites, setWebsites] = useState<any[]>([])
  const [campaigns, setCampaigns] = useState<DeviceCampaign[]>([])

  useEffect(() => { initialize() }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [offersRes, pubRes, websitesRes, cRes] = await Promise.all([
        offerApi.getAll().catch(() => ({ data: { offers: [] } })),
        adminApi.getPublishers({ page: 1, limit: 200 }).catch(() => ({ data: { publishers: [] } })),
        adminApi.getWebsites().catch(() => ({ data: { websites: [] } })),
        campaignApi.getAll({ status: 'active' }).catch(() => ({ data: { campaigns: [] } })),
      ])
      setOffers(offersRes.data.offers || [])
      const pubs = (pubRes.data.publishers || []).filter((p: Publisher) => p.role !== 'admin')
      setPublishers(pubs)
      setWebsites(websitesRes.data.websites || [])
      // Build campaign list — only device campaigns (global, windows, mac, android)
      const regularCampaigns = (cRes.data.campaigns || []).filter((c: any) => c.device_os)
      const campaignList: DeviceCampaign[] = regularCampaigns.map((c: any) => ({
        id: c.id, name: c.name, device_os: c.device_os || 'global',
      }))
      setCampaigns(campaignList)
    } catch { setOffers([]) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const handleSave = async () => {
    const name = form.name.trim()
    const offer_url_raw = form.offer_url.trim()
    if (!name) { toast.error('Offer name is required'); return }
    if (!isValidHttpUrl(offer_url_raw)) { toast.error('Enter a valid URL (e.g. example.com/offer)'); return }
    // Auto-prepend https:// when protocol is missing
    const offer_url = /^https?:\/\//i.test(offer_url_raw) ? offer_url_raw : `https://${offer_url_raw}`
    const parsedCpc = parseFloat(form.cpc)
    const cpc = Number.isFinite(parsedCpc) && parsedCpc >= 0 ? parsedCpc : 0

    setSaving(true)
    try {
      const data = {
        name,
        offer_url,
        password: form.password,
        status: form.status,
        cpc,
        campaign_id: form.campaign_id || null,
        publisher_ids: form.publisher_ids,
        website_ids: form.website_ids,
        os_types: form.os_types,
        country_codes: form.country_codes,
        direct_redirect_mode: form.direct_redirect_mode,
      }
      if (modal === 'edit' && editId) {
        await offerApi.update(editId, data)
        toast.success('Offer updated')
      } else {
        await offerApi.create(data)
        toast.success('Offer created')
      }
      setModal(null)
      load()
    } catch (err: any) { toast.error(err.response?.data?.detail?.[0]?.msg || err.response?.data?.detail || 'Failed to save offer') }
    finally { setSaving(false) }
  }

  const handleDelete = async (offer: Offer) => {
    setDeleting(true)
    try {
      await offerApi.delete(offer.id)
      toast.success('Offer deleted')
      setDeleteTarget(null)
      load()
    } catch { toast.error('Delete failed') }
    finally { setDeleting(false) }
  }

  const openEdit = (o: Offer) => {
    setEditId(o.id)
    setForm({
      name: o.name,
      offer_url: o.offer_url,
      password: o.password || '',
      status: o.status,
      cpc: (o.cpc ?? o.payout ?? 0).toString(),
      campaign_id: o.campaign_id || '',
      publisher_ids: o.publisher_ids || [],
      website_ids: o.website_ids || [],
      os_types: o.os_types || [],
      country_codes: o.country_codes || [],
      direct_redirect_mode: o.direct_redirect_mode || false,
    })
    setModal('edit')
  }

  const openCreate = () => {
    setForm(emptyForm())
    setModal('create')
  }

  // Build selector items
  const publisherItems = publishers.map(p => ({ key: p.id, label: p.name, extra: p.email }))
  const websiteItems = websites.map((w: any) => ({ key: w.id || w._id, label: w.name || w.domain, extra: w.domain, publisher_id: w.publisher_id }))
  const osItems = OS_OPTIONS.map(o => ({ key: o.key, label: o.label }))
  const countryItems = COUNTRIES.map(c => ({ key: c.code, label: `${c.flag} ${c.label}`, extra: c.code }))

  // Helper to display tags in table
  const tagDisplay = (ids: string[] | undefined, allLabel: string, lookupList?: { id: string; name: string }[]) => {
    if (!ids || ids.length === 0) return <span className="text-xs text-emerald-600 font-medium">All {allLabel}</span>
    if (lookupList) {
      const names = ids.map(id => lookupList.find(item => item.id === id)?.name || id).slice(0, 2)
      return (
        <span className="text-xs text-gray-600">
          {names.join(', ')}{ids.length > 2 ? ` +${ids.length - 2}` : ''}
        </span>
      )
    }
    return <span className="text-xs text-gray-500">{ids.length} selected</span>
  }

  const columns = [
    { key: 'name', label: 'Name', render: (o: Offer) => <span className="font-medium text-gray-900">{o.name}</span> },
    { key: 'offer_url', label: 'URL', render: (o: Offer) => <span className="text-sm text-gray-500 max-w-[180px] block truncate font-mono">{o.offer_url}</span> },
    { key: 'password', label: 'Pass', render: (o: Offer) => o.password ? <Lock size={13} className="text-gray-400" /> : <span className="text-gray-300">&mdash;</span> },
    { key: 'campaign_id', label: 'Campaign', render: (o: Offer) => {
      const c = campaigns.find(c => c.id === o.campaign_id)
      if (!c) return <span className="text-gray-300">&mdash;</span>
      const Icon = DEVICE_ICONS_MAP[c.device_os] || Globe
      return <div className="flex items-center gap-1.5"><Icon size={14} className="text-gray-500" /><span className="text-xs">{c.name}</span></div>
    }},
    { key: 'publishers', label: 'Publishers', render: (o: Offer) => tagDisplay(o.publisher_ids, 'Publishers', publishers as any) },
    { key: 'os', label: 'OS', render: (o: Offer) => tagDisplay(o.os_types, 'OS') },
    { key: 'countries', label: 'Countries', render: (o: Offer) => tagDisplay(o.country_codes, 'Countries') },
    { key: 'status', label: 'Status', render: (o: Offer) => <StatusBadge status={o.status} /> },
    { key: 'cpc', label: 'CPC', render: (o: Offer) => <span className="font-mono text-primary font-semibold">${(o.cpc ?? o.payout ?? 0).toFixed(3)}</span> },
    { key: 'actions', label: '', render: (o: Offer) => (
      <div className="flex gap-1">
        <button onClick={() => openEdit(o)} className="p-1.5 rounded-lg text-gray-500 hover:text-gray-900 hover:bg-gray-100"><Edit size={15} /></button>
        <button onClick={() => setDeleteTarget(o)} className="p-1.5 rounded-lg text-red-400 hover:text-red-600 hover:bg-red-50"><Trash2 size={15} /></button>
      </div>
    )},
  ]

  const inputClass = "w-full px-4 py-2.5 border border-gray-200 rounded-xl text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary text-sm"

  return (
    <div className="flex min-h-screen bg-[#f8f9fb]" style={{ zoom: 0.9 }}>
      <Sidebar />
      <div className="flex-1 lg:ml-64 p-6 lg:p-8 min-w-0">
        <div className="flex items-center justify-between mb-8 pt-12 lg:pt-0">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Offers</h1>
            <p className="text-gray-400 text-sm mt-0.5">Manage advertising offers with targeting</p>
          </div>
          <button onClick={openCreate}
            className="bg-primary hover:bg-primary-dark text-white px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2">
            <Plus size={18} /> Add Offer
          </button>
        </div>

        <div className="bg-white rounded-2xl border border-gray-100 p-6 overflow-x-auto">
          <DataTable columns={columns} data={offers} loading={loading} emptyMessage="No offers yet. Create your first offer." />
        </div>

        {/* ==================== CREATE / EDIT MODAL ==================== */}
        {modal && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setModal(null)}>
            <div className="bg-white rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl border border-gray-100" onClick={e => e.stopPropagation()}>
              {/* Modal Header */}
              <div className="sticky top-0 z-10 flex items-center justify-between px-6 py-4 border-b border-gray-100 bg-white rounded-t-2xl">
                <h3 className="text-lg font-bold text-gray-900">{modal === 'create' ? 'Create Offer' : 'Edit Offer'}</h3>
                <button onClick={() => setModal(null)} className="p-2 hover:bg-gray-100 rounded-xl transition-colors">
                  <X size={20} className="text-gray-400" />
                </button>
              </div>

              <div className="p-6 space-y-5">
                {/* Row 1: Name + Status */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Offer Name</label>
                    <input name="offer_name" autoComplete="off" value={form.name} onChange={e => setForm(p => ({...p, name: e.target.value}))} placeholder="Finance Lead US" className={inputClass} />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
                      <select value={form.status} onChange={e => setForm(p => ({...p, status: e.target.value}))} className={inputClass}>
                        <option value="active">Active</option>
                        <option value="paused">Paused</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">CPC ($)</label>
                      <input type="number" name="offer_cpc" autoComplete="off" step="0.001" min="0" value={form.cpc} onChange={e => setForm(p => ({...p, cpc: e.target.value}))} className={inputClass} />
                    </div>
                  </div>
                </div>

                {/* Row 2: URL + Password */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Offer URL</label>
                    <input type="text" inputMode="url" name="offer_url" autoComplete="off" value={form.offer_url} onChange={e => setForm(p => ({...p, offer_url: e.target.value}))} placeholder="example.com/offer or https://example.com/offer"
                      className={`${inputClass} ${form.offer_url.trim() && !isValidHttpUrl(form.offer_url) ? 'border-red-300 focus:ring-red-200 focus:border-red-400' : ''}`} />
                    {form.offer_url.trim() && !isValidHttpUrl(form.offer_url) && (
                      <p className="text-xs text-red-500 mt-1">Enter a URL or domain — https:// will be added automatically</p>
                    )}
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Password <span className="text-gray-400 font-normal">(optional)</span></label>
                    <input
                      type="text"
                      name="offer_password"
                      autoComplete="off"
                      value={form.password}
                      onChange={e => setForm(p => ({...p, password: e.target.value}))}
                      placeholder="Offer password"
                      className={inputClass}
                    />
                  </div>
                </div>

                {/* Campaign Selection */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Campaign</label>
                  <select value={form.campaign_id} onChange={e => setForm(p => ({...p, campaign_id: e.target.value}))} className={inputClass}>
                    <option value="">All Campaigns</option>
                    {campaigns.map(c => {
                      const label = c.device_os ? `[${c.device_os.toUpperCase()}] ${c.name}` : c.name
                      return <option key={c.id} value={c.id}>{label}</option>
                    })}
                  </select>
                  {form.campaign_id && (() => {
                    const selected = campaigns.find(c => c.id === form.campaign_id)
                    if (!selected) return null
                    const Icon = DEVICE_ICONS_MAP[selected.device_os] || Globe
                    return (
                      <div className="mt-2 p-2.5 rounded-lg bg-gray-50 border border-gray-100 flex items-center gap-2">
                        <Icon size={16} className="text-gray-500" />
                        <div className="text-xs">
                          <span className="font-medium text-gray-900">{selected.name}</span>
                          <span className="text-gray-400 ml-1.5">({selected.device_os})</span>
                        </div>
                      </div>
                    )
                  })()}
                </div>

                {/* Bypass Redirect Toggle */}
                <div className="flex items-center justify-between p-3.5 rounded-xl border border-gray-200 bg-gray-50/50">
                  <div>
                    <p className="text-sm font-semibold text-gray-700">Bypass Redirect Links</p>
                    <p className="text-xs text-gray-400 mt-0.5">Skip intermediate redirects and go directly to the offer URL</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setForm(p => ({ ...p, direct_redirect_mode: !p.direct_redirect_mode }))}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${form.direct_redirect_mode ? 'bg-primary' : 'bg-gray-300'}`}
                  >
                    <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform shadow-sm ${form.direct_redirect_mode ? 'translate-x-6' : 'translate-x-1'}`} />
                  </button>
                </div>

                <div className="h-px bg-gray-100" />

                {/* Targeting Section */}
                <div>
                  <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-4">Targeting</p>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Publishers */}
                    <MultiSelect
                      label="Publishers"
                      items={publisherItems}
                      selected={form.publisher_ids}
                      onChange={val => setForm(p => {
                        // Drop any selected websites that no longer belong to the
                        // chosen publishers, so the payload can't carry orphan ids.
                        const allowed = val.length > 0
                          ? new Set(websites.filter((w: any) => val.includes(w.publisher_id)).map((w: any) => w.id || w._id))
                          : null
                        return {
                          ...p,
                          publisher_ids: val,
                          website_ids: allowed ? p.website_ids.filter(id => allowed.has(id)) : p.website_ids,
                        }
                      })}
                      allLabel="All Publishers"
                    />

                    {/* Websites */}
                    <MultiSelect
                      label="Websites"
                      items={
                        form.publisher_ids.length > 0
                          ? websiteItems.filter((w: any) => form.publisher_ids.includes(w.publisher_id))
                          : websiteItems
                      }
                      selected={form.website_ids}
                      onChange={val => setForm(p => ({ ...p, website_ids: val }))}
                      allLabel="All Websites"
                    />

                    {/* OS Types */}
                    <MultiSelect
                      label="Operating Systems"
                      items={osItems}
                      selected={form.os_types}
                      onChange={val => setForm(p => ({ ...p, os_types: val }))}
                      allLabel="All OS Types"
                      searchable={false}
                    />

                    {/* Countries */}
                    <MultiSelect
                      label="Countries"
                      items={countryItems}
                      selected={form.country_codes}
                      onChange={val => setForm(p => ({ ...p, country_codes: val }))}
                      allLabel="All Countries"
                    />
                  </div>
                </div>
              </div>

              {/* Modal Footer */}
              <div className="sticky bottom-0 flex gap-3 px-6 py-4 border-t border-gray-100 bg-white rounded-b-2xl">
                <button onClick={handleSave} disabled={saving || !form.name.trim() || !isValidHttpUrl(form.offer_url)}
                  className="flex-1 bg-primary hover:bg-primary-dark text-white py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center disabled:bg-gray-300 transition-colors">
                  {saving ? <Spinner size={16} /> : modal === 'create' ? 'Create Offer' : 'Save Changes'}
                </button>
                <button onClick={() => setModal(null)} className="flex-1 py-2.5 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50 transition-colors">Cancel</button>
              </div>
            </div>
          </div>
        )}

        {/* ── Delete Offer Confirmation ────────────────────────────────────── */}
        <ConfirmDialog
          open={deleteTarget !== null}
          title="Delete Offer"
          message={<>Delete offer <strong className="text-gray-900">{deleteTarget?.name}</strong>? Traffic targeting this offer will fall back to the campaign URL. This cannot be undone.</>}
          confirmLabel="Delete Offer"
          loading={deleting}
          onConfirm={() => { if (deleteTarget) handleDelete(deleteTarget) }}
          onCancel={() => setDeleteTarget(null)}
        />
      </div>
    </div>
  )
}
