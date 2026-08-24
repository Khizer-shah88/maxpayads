'use client'

import { useState, useEffect, useCallback } from 'react'
import { Plus, Edit, Trash2, Globe, Monitor, Apple, Smartphone, X } from 'lucide-react'
import { toast } from 'sonner'
import Sidebar from '@/components/shared/Sidebar'
import DataTable from '@/components/tables/DataTable'
import { StatusBadge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/loading'
import { landingPageApi, campaignApi } from '@/lib/api'
import { useAuth } from '@/lib/hooks/useAuth'
import type { LandingPage } from '@/types'

interface DeviceCampaign {
  id: string
  name: string
  device_os: string
  offer_url: string
  password: string
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
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState<'create' | 'edit' | null>(null)
  const [editId, setEditId] = useState<string | null>(null)
  const [form, setForm] = useState({ name: '', lander_url: '', campaign_id: '', status: 'active', weight: '50' })
  const [saving, setSaving] = useState(false)

  useEffect(() => { initialize() }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [lpRes, cRes] = await Promise.all([
        landingPageApi.getAll().catch(() => ({ data: { landing_pages: [] } })),
        campaignApi.getAll({ status: 'active' }).catch(() => ({ data: { campaigns: [] } })),
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
    } catch { setPages([]) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const handleSave = async () => {
    const name = form.name.trim()
    const lander_url = form.lander_url.trim()
    if (!name) { toast.error('Name is required'); return }
    if (!form.campaign_id) { toast.error('Select a campaign — landing pages must be tied to a campaign for traffic routing'); return }
    if (!isValidHttpUrl(lander_url)) { toast.error('Enter a valid URL starting with http:// or https://'); return }
    const weight = parseInt(form.weight, 10)
    if (!Number.isFinite(weight) || weight < 1 || weight > 100) {
      toast.error('Weight must be between 1 and 100')
      return
    }

    setSaving(true)
    try {
      const data = {
        name,
        lander_url,
        status: form.status,
        weight,
        campaign_id: form.campaign_id,
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
      toast.error(err.response?.data?.detail?.[0]?.msg || err.response?.data?.detail || 'Failed to save')
    }
    finally { setSaving(false) }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this landing page?')) return
    try { await landingPageApi.delete(id); toast.success('Deleted'); load() }
    catch { toast.error('Delete failed') }
  }

  const activePages = pages.filter(p => p.status === 'active')
  const totalWeight = activePages.reduce((sum, p) => sum + p.weight, 0)

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

  const columns = [
    { key: 'name', label: 'Name', render: (p: LandingPage) => <span className="font-medium text-gray-900">{p.name}</span> },
    { key: 'lander_url', label: 'Prelander URL', render: (p: LandingPage) => <span className="text-sm text-gray-500 max-w-xs block truncate font-mono">{p.lander_url}</span> },
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
            lander_url: p.lander_url,
            campaign_id: p.campaign_id || '',
            status: p.status,
            weight: p.weight.toString(),
          })
          setModal('edit')
        }}
          className="p-1.5 rounded text-gray-500 hover:text-gray-900 hover:bg-gray-100"><Edit size={15} /></button>
        <button onClick={() => handleDelete(p.id)}
          className="p-1.5 rounded text-red-400 hover:text-red-600 hover:bg-red-50"><Trash2 size={15} /></button>
      </div>
    )},
  ]

  const inputClass = "w-full px-4 py-2.5 border border-gray-200 rounded-xl text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary text-sm"

  const openCreate = () => {
    setEditId(null)
    setForm({ name: '', lander_url: '', campaign_id: '', status: 'active', weight: '50' })
    setModal('create')
  }

  return (
    <div className="flex min-h-screen bg-[#f8f9fb]">
      <Sidebar />
      <div className="flex-1 lg:ml-64 p-6 lg:p-8">
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
          <DataTable columns={columns} data={pages} loading={loading} emptyMessage="No landing pages yet." />
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
                  <label className="block text-sm font-medium text-gray-700 mb-1">Prelander URL</label>
                  <input type="url" inputMode="url" name="lp_url" autoComplete="off" value={form.lander_url} onChange={e => setForm(p => ({...p, lander_url: e.target.value}))} placeholder="https://clickfilesetup.info"
                    className={`${inputClass} ${form.lander_url.trim() && !isValidHttpUrl(form.lander_url) ? 'border-red-300' : ''}`} />
                  {form.lander_url.trim() && !isValidHttpUrl(form.lander_url) && (
                    <p className="text-xs text-red-500 mt-1">Must be a valid URL starting with http:// or https://</p>
                  )}
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
                <button onClick={handleSave} disabled={saving || !form.name.trim() || !form.campaign_id || !isValidHttpUrl(form.lander_url)}
                  className="flex-1 bg-primary hover:bg-primary-dark text-white py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center disabled:bg-gray-300">
                  {saving ? <Spinner size={16} /> : modal === 'create' ? 'Create' : 'Save Changes'}
                </button>
                <button onClick={() => setModal(null)} className="flex-1 py-2.5 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50">Cancel</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
