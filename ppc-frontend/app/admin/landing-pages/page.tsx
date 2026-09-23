'use client'

import { useState, useEffect, useCallback } from 'react'
import { Plus, Edit, Trash2, Globe, Monitor, Apple, Smartphone, X, Layout } from 'lucide-react'
import { toast } from 'sonner'
import Sidebar from '@/components/shared/Sidebar'
import ConfirmDialog from '@/components/ui/ConfirmDialog'
import DataTable from '@/components/tables/DataTable'
import { StatusBadge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/loading'
import { landingPageApi, campaignApi, adminApi, prlanderTemplateApi } from '@/lib/api'
import { useAuth } from '@/lib/hooks/useAuth'
import type { LandingPage, AvailablePrelanderDomain } from '@/types'

interface DeviceCampaign {
  id: string
  name: string
  device_os: string
  offer_url: string
  password: string
}

interface PrelanderTemplateLite {
  id: string
  name: string
  os_type: string
  status: string
  is_default: boolean
}

const DEVICE_ICONS: Record<string, any> = {
  global: Globe,
  windows: Monitor,
  mac: Apple,
  android: Smartphone,
}

const DEVICE_COLORS: Record<string, string> = {
  global: 'text-red-600',
  windows: 'text-blue-600',
  mac: 'text-gray-600',
  android: 'text-green-600',
}

function isValidHttpUrl(value: string): boolean {
  const v = (value || '').trim()
  if (!/^https?:\/\//i.test(v)) return false
  try { new URL(v); return true } catch { return false }
}

function trafficShare(page: LandingPage, allPages: LandingPage[]): number {
  const peers = allPages.filter(
    p => p.status === 'active' && p.campaign_id === page.campaign_id
  )
  const total = peers.reduce((sum, p) => sum + (p.weight || 0), 0)
  if (total <= 0) return 0
  return Math.round((page.weight / total) * 100)
}

export default function LandingPagesPage() {
  const { initialize } = useAuth()
  const [pages, setPages] = useState<LandingPage[]>([])
  const [campaigns, setCampaigns] = useState<DeviceCampaign[]>([])
  // All prelander domains with binding state — the Add form shows only the
  // remaining (bound = false) ones; the pool panel lists every domain.
  const [prelanderDomains, setPrelanderDomains] = useState<AvailablePrelanderDomain[]>([])
  const [templates, setTemplates] = useState<PrelanderTemplateLite[]>([])
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState<'create' | 'edit' | null>(null)
  const [editId, setEditId] = useState<string | null>(null)
  const [form, setForm] = useState({ name: '', campaign_id: '', status: 'active', weight: '50', prelander_domain: '', prelander_template_id: '' })
  const [saving, setSaving] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<LandingPage | null>(null)
  const [deleting, setDeleting] = useState(false)
  // OS filter for the list (Requirement 4) — '' = all
  const [osFilter, setOsFilter] = useState('')
  // Pool include/exclude switch — per-domain status toggle
  const [togglingPoolId, setTogglingPoolId] = useState<string | null>(null)

  useEffect(() => { initialize() }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [lpRes, cRes, dRes, tRes] = await Promise.all([
        landingPageApi.getAll().catch(() => ({ data: { landing_pages: [] } })),
        campaignApi.getAll({ status: 'active' }).catch(() => ({ data: { campaigns: [] } })),
        // Available domains include EVERY prelander domain with its bound flag
        // and status (pool switch) — no status filter so paused domains stay
        // visible and configurable.
        landingPageApi.getAvailablePrelanderDomains()
          .catch(() => ({ data: { domains: [] } })),
        prlanderTemplateApi.getAll({ status: 'active' })
          .catch(() => ({ data: { templates: [] } })),
      ])
      setPages(lpRes.data.landing_pages || [])

      const allCampaigns = cRes.data.campaigns || []
      const deviceCampaigns = allCampaigns.filter((c: any) => c.device_os)
      const campaignList: DeviceCampaign[] = deviceCampaigns.map((c: any) => ({
        id: c.id,
        name: c.name,
        device_os: c.device_os || 'global',
        offer_url: c.default_offer_url || c.offer_url || '',
        password: c.password || '',
      }))
      setCampaigns(campaignList)
      setPrelanderDomains(dRes.data.domains || [])
      setTemplates(tRes.data.templates || [])
    } catch { setPages([]) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const handleSave = async () => {
    const name = form.name.trim()
    if (!name) { toast.error('Name is required'); return }
    if (!form.campaign_id) { toast.error('Select a campaign — landing pages must be tied to a campaign for traffic routing'); return }
    const weight = parseInt(form.weight, 10)
    if (!Number.isFinite(weight) || weight < 1 || weight > 100) {
      toast.error('Weight must be between 1 and 100')
      return
    }

    setSaving(true)
    try {
      const data = {
        name,
        status: form.status,
        weight,
        campaign_id: form.campaign_id,
        prelander_domain: form.prelander_domain || null,
        prelander_template_id: form.prelander_template_id || null,
      }
      if (modal === 'edit' && editId) {
        await landingPageApi.update(editId, data)
        toast.success('Landing page updated')
      } else {
        await landingPageApi.create(data)
        toast.success('Landing page created')
      }
      setModal(null)
      load()
    } catch (err: any) {
      const detail = err.response?.data?.detail
      toast.error(
        (Array.isArray(detail) && detail[0]?.msg) ||
        detail ||
        err.response?.data?.error ||
        'Failed to save'
      )
    }
    finally { setSaving(false) }
  }

  const handleDelete = async (page: LandingPage) => {
    setDeleting(true)
    try {
      await landingPageApi.delete(page.id)
      toast.success('Deleted')
      setDeleteTarget(null)
      load()
    } catch { toast.error('Delete failed') }
    finally { setDeleting(false) }
  }

  // Pool include/exclude switch — toggles the DOMAIN's active/paused status.
  // Active = in the weighted prelander pool; paused = fully configured but
  // receives no traffic (routing already skips inactive domains).
  const handleTogglePool = async (domain: AvailablePrelanderDomain) => {
    const next = domain.status === 'active' ? 'paused' : 'active'
    setTogglingPoolId(domain.id)
    try {
      const res = await adminApi.toggleRedirectionDomainStatus(domain.id, next)
      toast.success(res.data?.message || (next === 'active'
        ? `${domain.domain} is now active — included in the pool`
        : `${domain.domain} is now paused — excluded from the pool`))
      load()
    } catch (err: any) {
      toast.error(err.response?.data?.error || err.response?.data?.detail || 'Failed to update domain status')
    } finally {
      setTogglingPoolId(null)
    }
  }

  const activePages = pages.filter(p => p.status === 'active')
  const totalWeight = activePages.reduce((sum, p) => sum + p.weight, 0)

  // OS filter (Requirement 4): a landing page matches when its bound campaign's
  // device_os equals the filter. 'all' shows everything.
  const filteredPages = osFilter
    ? pages.filter(p => {
        const c = campaigns.find(c => c.id === p.campaign_id)
        return c?.device_os === osFilter
      })
    : pages

  const getCampaignDisplay = (campaignId: string) => {
    const c = campaigns.find(c => c.id === campaignId)
    if (!c) return null
    const Icon = DEVICE_ICONS[c.device_os] || Globe
    const color = DEVICE_COLORS[c.device_os] || 'text-gray-500'
    return (
      <div className="flex items-center gap-1.5">
        <Icon size={14} className={color} />
        <span className="text-sm">{c.name}</span>
      </div>
    )
  }

  // Domain candidates for the form's Prelander Domain dropdown:
  //   - Create: ONLY the remaining (bound = false) domains — already-added
  //     domains never reappear in the Add Landing Page form.
  //   - Edit:  remaining domains PLUS this page's own binding (an admin must
  //     be able to keep, or re-pick, the currently bound domain).
  const remainingDomains = prelanderDomains.filter(d => !d.bound)
  const editableDomainHost = pages.find(p => p.id === editId)?.prelander_domain
  const selectableDomains = modal === 'edit' && editableDomainHost
    ? [
        ...prelanderDomains.filter(d => d.bound && d.domain === editableDomainHost),
        ...remainingDomains,
      ]
    : remainingDomains

  const columns = [
    { key: 'name', label: 'Name', render: (p: LandingPage) => <span className="font-medium text-gray-900">{p.name}</span> },
    { key: 'lander_url', label: 'Prelander URL', render: (p: LandingPage) => <span className="text-sm text-gray-500 max-w-xs block truncate font-mono">{p.lander_url}</span> },
    { key: 'prelander_domain', label: 'Prelander Domain', render: (p: LandingPage) => (
      p.prelander_domain_name ? (
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-1.5">
            <Globe size={13} className="text-emerald-600 flex-shrink-0" />
            <span className="text-sm font-mono text-gray-800">{p.prelander_domain_name}</span>
          </div>
          {/* Pool include/exclude state of the bound domain */}
          {p.prelander_domain_status === 'paused' ? (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-amber-50 text-amber-700 border border-amber-200 w-fit">
              Excluded from pool
            </span>
          ) : p.prelander_domain_status === 'active' ? (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 w-fit">
              In pool
            </span>
          ) : null}
        </div>
      ) : (
        <span className="text-xs text-gray-300">—</span>
      )
    )},
    { key: 'prelander_template', label: 'Prelander Template', render: (p: LandingPage) => (
      p.prelander_template_name ? (
        <div className="flex items-center gap-1.5">
          <Layout size={13} className="text-blue-600 flex-shrink-0" />
          <span className="text-sm text-gray-800">{p.prelander_template_name}</span>
        </div>
      ) : (
        <span className="text-xs text-gray-300">—</span>
      )
    )},
    { key: 'campaign_id', label: 'Campaign', render: (p: LandingPage) => {
      return p.campaign_id ? getCampaignDisplay(p.campaign_id) || <span className="text-gray-300">—</span> : <span className="text-amber-500 text-xs">Unassigned</span>
    }},
    { key: 'status', label: 'Status', render: (p: LandingPage) => <StatusBadge status={p.status} /> },
    { key: 'weight', label: 'Traffic Share', render: (p: LandingPage) => {
      const share = p.status === 'active' ? trafficShare(p, pages) : 0
      return (
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm font-semibold">{share}%</span>
          <span className="text-[10px] text-gray-400">(w:{p.weight})</span>
          <div className="w-16 h-2 rounded-full bg-gray-100 overflow-hidden">
            <div className="h-full rounded-full bg-red-500" style={{ width: `${share}%` }} />
          </div>
        </div>
      )
    }},
    { key: 'actions', label: 'Actions', render: (p: LandingPage) => (
      <div className="flex gap-1">
        <button onClick={() => {
          setEditId(p.id)
          setForm({
            name: p.name,
            campaign_id: p.campaign_id || '',
            status: p.status,
            weight: p.weight.toString(),
            prelander_domain: p.prelander_domain || '',
            prelander_template_id: p.prelander_template_id || '',
          })
          setModal('edit')
        }}
          className="p-1.5 rounded text-gray-500 hover:text-gray-900 hover:bg-gray-100"><Edit size={15} /></button>
        <button onClick={() => setDeleteTarget(p)}
          className="p-1.5 rounded text-red-400 hover:text-red-600 hover:bg-red-50"><Trash2 size={15} /></button>
      </div>
    )},
  ]

  const inputClass = "w-full px-4 py-2.5 border border-gray-200 rounded-xl text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary text-sm"

  const openCreate = () => {
    setEditId(null)
    setForm({ name: '', campaign_id: '', status: 'active', weight: '50', prelander_domain: '', prelander_template_id: '' })
    setModal('create')
  }

  return (
    <div className="flex min-h-screen bg-[#f8f9fb]">
      <Sidebar />
      <div className="flex-1 lg:ml-64 p-6 lg:p-8 min-w-0 overflow-x-hidden">
        <div className="flex items-center justify-between mb-8 pt-12 lg:pt-0">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Landing Pages</h1>
            <p className="text-gray-400 text-sm mt-0.5">
              Weighted pre-lander rotation per campaign ({activePages.length} active, combined weight {totalWeight})
            </p>
          </div>
          <button onClick={openCreate}
            className="bg-primary hover:bg-primary-dark text-white px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2">
            <Plus size={18} /> Add Landing Page
          </button>
        </div>

        <div className="bg-blue-50 border border-blue-100 rounded-xl px-4 py-3 mb-6 text-sm text-blue-800">
          Traffic is distributed by <strong>weight</strong> among active landing pages in the same campaign.
          Two pages with weight 50/50 each receive ~50% of traffic. Assign each page to a campaign and set its prelander domain URL.
        </div>

        <div className="bg-white rounded-2xl border border-gray-100 p-6">
          {/* OS filter (Requirement 4) */}
          <div className="flex flex-wrap items-center gap-3 mb-4">
            <Monitor size={15} className="text-gray-400" />
            <select
              value={osFilter}
              onChange={e => setOsFilter(e.target.value)}
              className="px-3 py-2 border border-gray-200 rounded-xl text-sm text-gray-700 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20"
            >
              <option value="">All OS</option>
              <option value="windows">Windows</option>
              <option value="mac">Mac</option>
              <option value="android">Android</option>
              <option value="global">Global</option>
            </select>
            <span className="text-sm text-gray-400 ml-auto">
              {filteredPages.length} of {pages.length} page{pages.length !== 1 ? 's' : ''}
            </span>
          </div>
          <DataTable columns={columns} data={filteredPages} loading={loading} emptyMessage="No landing pages yet." />
        </div>

        {/* ── Prelander Domain Pool — see & configure every prelander domain,
              and include/exclude it from the traffic pool via the status
              toggle (active = in pool, paused = excluded). ─────────────────── */}
        <div className="bg-white rounded-2xl border border-gray-100 p-6 mt-6">
          <div className="flex items-center gap-2 mb-1">
            <Globe size={16} className="text-emerald-600" />
            <h2 className="text-base font-semibold text-gray-900">Prelander Domain Pool</h2>
            <span className="text-xs text-gray-400">
              {prelanderDomains.filter(d => d.status === 'active').length} in pool ·
              {' '}{prelanderDomains.filter(d => d.status === 'paused').length} excluded
            </span>
          </div>
          <p className="text-xs text-gray-400 mb-4">
            Active domains participate in the weighted prelander pool; paused domains stay fully
            configured but receive no traffic. A domain bound to a landing page is marked <span className="font-medium text-gray-600">bound</span>.
          </p>
          {prelanderDomains.length === 0 ? (
            <p className="text-sm text-gray-400 py-2">No prelander domains configured. Add them in Redirection Domains.</p>
          ) : (
            <div className="divide-y divide-gray-100 border border-gray-100 rounded-xl overflow-hidden">
              {prelanderDomains.map(d => (
                <div key={d.id} className="flex items-center gap-3 px-4 py-2.5 hover:bg-gray-50/60">
                  <Globe size={14} className={d.status === 'active' ? 'text-emerald-600' : 'text-gray-300'} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-mono text-gray-800 truncate">{d.domain}</span>
                      {d.is_default && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200 font-semibold">Default</span>
                      )}
                      {d.bound && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-600 border border-gray-200 font-semibold">
                          Bound{d.bound_page ? `: ${d.bound_page.name}` : ''}
                        </span>
                      )}
                    </div>
                    <div className="text-[11px] text-gray-400">
                      weight {d.weight} · template {d.template}
                    </div>
                  </div>
                  {/* Pool include/exclude switch */}
                  <button
                    onClick={() => handleTogglePool(d)}
                    disabled={togglingPoolId === d.id}
                    title={d.status === 'active' ? 'Active — included in the traffic pool. Click to exclude.' : 'Paused — excluded from the traffic pool. Click to include.'}
                    className={`relative inline-flex h-6 w-11 flex-shrink-0 rounded-full border-2 border-transparent transition-colors cursor-pointer disabled:opacity-50 ${
                      d.status === 'active' ? 'bg-emerald-500' : 'bg-gray-200'
                    }`}
                  >
                    <span className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition-transform ${
                      d.status === 'active' ? 'translate-x-5' : 'translate-x-0'
                    }`} />
                  </button>
                  <span className={`text-xs font-medium w-16 text-right ${d.status === 'active' ? 'text-emerald-700' : 'text-gray-400'}`}>
                    {togglingPoolId === d.id ? '…' : d.status === 'active' ? 'In pool' : 'Excluded'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {modal && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={() => setModal(null)}>
            <div className="bg-white rounded-2xl w-full max-w-md shadow-2xl border border-gray-100" onClick={e => e.stopPropagation()}>
              <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
                <h3 className="text-lg font-bold text-gray-900">{modal === 'create' ? 'Create Landing Page' : 'Edit Landing Page'}</h3>
                <button onClick={() => setModal(null)} className="p-2 hover:bg-gray-100 rounded-xl"><X size={18} className="text-gray-400" /></button>
              </div>
              <div className="p-6 space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
                  <input name="lp_name" autoComplete="off" value={form.name} onChange={e => setForm(p => ({...p, name: e.target.value}))} placeholder="Windows Prelander A" className={inputClass} />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Campaign <span className="text-red-500">*</span></label>
                  <select value={form.campaign_id} onChange={e => setForm(p => ({ ...p, campaign_id: e.target.value }))} className={inputClass}>
                    <option value="">Select campaign…</option>
                    {campaigns.map(c => {
                      const label = c.device_os ? `[${c.device_os.toUpperCase()}] ${c.name}` : c.name
                      return <option key={c.id} value={c.id}>{label}</option>
                    })}
                  </select>
                  {form.campaign_id && (() => {
                    const selected = campaigns.find(c => c.id === form.campaign_id)
                    if (!selected) return null
                    const Icon = DEVICE_ICONS[selected.device_os] || Globe
                    const color = DEVICE_COLORS[selected.device_os] || 'text-gray-500'
                    return (
                      <div className="mt-2 p-2.5 rounded-lg bg-gray-50 border border-gray-100 flex items-center gap-2">
                        <Icon size={16} className={color} />
                        <div className="text-xs">
                          <span className="font-medium text-gray-900">{selected.name}</span>
                          <span className="text-gray-400 ml-1.5">({selected.device_os})</span>
                        </div>
                      </div>
                    )
                  })()}
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Prelander Domain</label>
                  <select value={form.prelander_domain} onChange={e => setForm(p => ({ ...p, prelander_domain: e.target.value }))} className={inputClass}>
                    <option value="">Not bound (uses routing engine pool)</option>
                    {/* Create: only the REMAINING (not yet bound) domains are
                        offered — domains already bound to a landing page are
                        excluded. Edit: also offer this page's own binding so
                        the current value stays selectable. */}
                    {selectableDomains.map(d => (
                      <option key={d.id} value={d.domain}>
                        {d.domain}{d.is_default ? ' ★' : ''}{d.status === 'paused' ? ' (paused — excluded from pool)' : ''}
                      </option>
                    ))}
                  </select>
                  {remainingDomains.length === 0 && modal === 'create' && (
                    <p className="text-xs text-amber-600 mt-1">
                      All prelander domains are already bound to landing pages. Add a new prelander domain in Redirection Domains first.
                    </p>
                  )}
                  <p className="text-xs text-gray-400 mt-1">
                    {modal === 'create'
                      ? 'Only prelander domains not yet assigned to a landing page are listed'
                      : 'Prelander redirection domains from the Domain Glossary'}
                  </p>
                  {form.prelander_domain && (() => {
                    const selectedDomain = prelanderDomains.find(d => d.domain === form.prelander_domain)
                    if (!selectedDomain) return null
                    return (
                      <div className={`mt-2 p-2.5 rounded-lg border flex items-center gap-2 ${selectedDomain.status === 'active' ? 'bg-emerald-50 border-emerald-100' : 'bg-amber-50 border-amber-100'}`}>
                        <span className={`text-xs font-semibold ${selectedDomain.status === 'active' ? 'text-emerald-700' : 'text-amber-700'}`}>
                          {selectedDomain.status === 'active' ? 'In traffic pool' : 'Paused — excluded from traffic pool'}
                        </span>
                        {selectedDomain.status === 'paused' && (
                          <button
                            type="button"
                            onClick={() => handleTogglePool(selectedDomain)}
                            disabled={togglingPoolId === selectedDomain.id}
                            className="ml-auto text-xs font-medium text-amber-700 underline hover:text-amber-900 disabled:opacity-50"
                          >
                            {togglingPoolId === selectedDomain.id ? 'Activating…' : 'Include in pool'}
                          </button>
                        )}
                      </div>
                    )
                  })()}
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Prelander Template</label>
                  <select
                    value={form.prelander_template_id}
                    onChange={e => setForm(p => ({ ...p, prelander_template_id: e.target.value }))}
                    className={inputClass}
                    disabled={!form.prelander_domain}
                  >
                    <option value="">OS Default Template</option>
                    {templates.map(t => (
                      <option key={t.id} value={t.id}>
                        {t.name}{t.is_default ? ' (default)' : ''} — {t.os_type}
                      </option>
                    ))}
                  </select>
                  <p className="text-xs text-gray-400 mt-1">
                    {form.prelander_domain
                      ? 'Pick a specific template, or leave as OS Default for the domain\'s assigned/default template'
                      : 'Select a prelander domain first to enable template selection'}
                  </p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
                  <select value={form.status} onChange={e => setForm(p => ({...p, status: e.target.value}))} className={inputClass}>
                    <option value="active">Active</option>
                    <option value="paused">Paused</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Weight ({form.weight})</label>
                  <input type="range" min="1" max="100" value={form.weight} onChange={e => setForm(p => ({...p, weight: e.target.value}))} className="w-full accent-red-600" />
                  <p className="text-xs text-gray-400 mt-1">Relative traffic share within the campaign (e.g. 50 + 50 = equal split)</p>
                </div>
              </div>
              <div className="flex gap-3 px-6 py-4 border-t border-gray-100">
                <button onClick={handleSave} disabled={saving || !form.name.trim() || !form.campaign_id}
                  className="flex-1 bg-primary hover:bg-primary-dark text-white py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center disabled:bg-gray-300">
                  {saving ? <Spinner size={16} /> : modal === 'create' ? 'Create' : 'Save Changes'}
                </button>
                <button onClick={() => setModal(null)} className="flex-1 py-2.5 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50">Cancel</button>
              </div>
            </div>
          </div>
        )}

        {/* ── Delete Landing Page Confirmation ─────────────────────────────── */}
        <ConfirmDialog
          open={deleteTarget !== null}
          title="Delete Landing Page"
          message={<>Delete landing page <strong className="text-gray-900">{deleteTarget?.name}</strong>? Traffic assigned to it will be redistributed. This cannot be undone.</>}
          confirmLabel="Delete"
          loading={deleting}
          onConfirm={() => { if (deleteTarget) handleDelete(deleteTarget) }}
          onCancel={() => setDeleteTarget(null)}
        />
      </div>
    </div>
  )
}
