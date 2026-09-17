'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  Plus, Edit, Trash2, Globe2, Link2, Layers, FileText, RefreshCw,
  CheckCircle2, XCircle, Clock, Star, Users, Info, ArrowRight,
} from 'lucide-react'
import { toast } from 'sonner'
import Sidebar from '@/components/shared/Sidebar'
import DataTable from '@/components/tables/DataTable'
import { StatusBadge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/loading'
import { adminApi } from '@/lib/api'
import { useAuth } from '@/lib/hooks/useAuth'
import type { RedirectionDomain, RedirectionDomainType, Publisher } from '@/types'

const DOMAIN_TYPES: {
  key: RedirectionDomainType
  label: string
  short: string
  description: string
  icon: typeof Link2
  color: string
}[] = [
  {
    key: 'anchor',
    label: 'Anchor Domain',
    short: 'Anchor',
    description: 'First redirect domain — receives the Smartlink and ad embed codes.',
    icon: Link2,
    color: 'text-blue-600 bg-blue-50 border-blue-100',
  },
  {
    key: 'inter',
    label: 'Inter Domain',
    short: 'Inter',
    description: 'Intermediate redirect hop after the Anchor (referrer stripping).',
    icon: Layers,
    color: 'text-amber-600 bg-amber-50 border-amber-100',
  },
  {
    key: 'prelander',
    label: 'Prelander Domain',
    short: 'Prelander',
    description: 'Page shown before the Offer, with a copyable download link (/d/slug). Skipped when direct redirect is on.',
    icon: FileText,
    color: 'text-emerald-600 bg-emerald-50 border-emerald-100',
  },
]

const EMPTY_FORM = {
  domain: '',
  domain_type: 'anchor' as RedirectionDomainType,
  publisher_ids: [] as string[],
  is_default: false,
  status: 'active' as 'active' | 'paused',
  template: 'default' as 'default' | 'windows' | 'mac',
  weight: 100,
  notes: '',
}

function DnsBadge({ status }: { status: string }) {
  if (status === 'verified') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
        <CheckCircle2 size={12} /> Verified
      </span>
    )
  }
  if (status === 'failed') {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-red-50 text-red-600 border border-red-200">
        <XCircle size={12} /> Failed
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-gray-100 text-gray-600 border border-gray-200">
      <Clock size={12} /> Pending
    </span>
  )
}

export default function RedirectionDomainsPage() {
  const { initialize } = useAuth()
  const [domains, setDomains] = useState<RedirectionDomain[]>([])
  const [publishers, setPublishers] = useState<Publisher[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<RedirectionDomainType>('anchor')
  const [modal, setModal] = useState<'create' | 'edit' | null>(null)
  const [editId, setEditId] = useState<string | null>(null)
  const [form, setForm] = useState({ ...EMPTY_FORM })
  const [saving, setSaving] = useState(false)
  const [verifyingId, setVerifyingId] = useState<string | null>(null)
  const [serverIp, setServerIp] = useState('')

  // Delete confirmation modal — domain deletion requires confirmation; the
  // backend reports chains that referenced the domain so admin can reconfigure.
  const [deleteModal, setDeleteModal] = useState<RedirectionDomain | null>(null)
  const [deleteConfirmText, setDeleteConfirmText] = useState('')
  const [deleteLoading, setDeleteLoading] = useState(false)
  const [affectedChains, setAffectedChains] = useState<{ id: string; name: string }[]>([])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [domRes, pubRes] = await Promise.all([
        adminApi.getRedirectionDomains(),
        adminApi.getPublishers({ limit: 200 }),
      ])
      setDomains(domRes.data?.domains ?? [])
      setServerIp(domRes.data?.dns_instructions?.server_ip ?? '')
      setPublishers(((pubRes.data?.publishers) ?? []).filter((p: Publisher) => p.role !== 'admin'))
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || err?.message || 'Failed to load redirection domains')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { 
    initialize()
    load() 
  }, [])

  const filtered = domains.filter(d => d.domain_type === activeTab)
  const typeMeta = DOMAIN_TYPES.find(t => t.key === activeTab)!

  const openCreate = () => {
    setForm({ ...EMPTY_FORM, domain_type: activeTab })
    setEditId(null)
    setModal('create')
  }

  const openEdit = (d: RedirectionDomain) => {
    setEditId(d.id)
    setForm({
      domain: d.domain,
      domain_type: d.domain_type,
      publisher_ids: d.publisher_ids || [],
      is_default: d.is_default,
      status: d.status,
      template: d.template || 'default',
      weight: (d as any).weight ?? 100,
      notes: d.notes || '',
    })
    setModal('edit')
  }

  const togglePublisher = (pubId: string) => {
    setForm(prev => ({
      ...prev,
      publisher_ids: prev.publisher_ids.includes(pubId)
        ? prev.publisher_ids.filter(id => id !== pubId)
        : [...prev.publisher_ids, pubId],
    }))
  }

  const handleSave = async () => {
    if (!form.domain.trim()) {
      toast.error('Domain name is required')
      return
    }
    setSaving(true)
    try {
      const payload = { ...form }
      if (modal === 'edit' && editId) {
        const res = await adminApi.updateRedirectionDomain(editId, payload)
        // Update in place instead of full reload
        setDomains(prev => prev.map(d => d.id === editId ? res.data.domain : d))
        toast.success('Domain updated')
      } else {
        const res = await adminApi.createRedirectionDomain(payload)
        // Add new domain to list instead of full reload
        setDomains(prev => [...prev, res.data.domain])
        toast.success('Domain added')
      }
      setModal(null)
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to save domain')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!deleteModal) return
    if (deleteConfirmText.trim().toUpperCase() !== 'DELETE') {
      toast.error('Type DELETE to confirm removal')
      return
    }
    setDeleteLoading(true)
    try {
      const res = await adminApi.deleteRedirectionDomain(deleteModal.id)
      const chains = res.data?.affected_chains ?? []
      if (chains.length > 0) {
        toast.warning(`${chains.length} redirect chain(s) reference this domain — reconfigure them manually`, {
          duration: 8000,
        })
      } else {
        toast.success('Domain removed')
      }
      // Remove from list instead of full reload
      setDomains(prev => prev.filter(d => d.id !== deleteModal.id))
      setDeleteModal(null)
      setDeleteConfirmText('')
      setAffectedChains([])
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Delete failed')
    } finally {
      setDeleteLoading(false)
    }
  }

  const handleVerifyDns = async (d: RedirectionDomain) => {
    setVerifyingId(d.id)
    try {
      const res = await adminApi.verifyRedirectionDomainDns(d.id)
      if (res.data.domain?.dns_status === 'verified') {
        toast.success('DNS verified — domain is pointing to the server')
        // Update in place instead of full reload
        setDomains(prev => prev.map(dom => dom.id === d.id ? { ...dom, dns_status: 'verified' } : dom))
      } else {
        toast.error(res.data.message || 'DNS verification failed')
        setDomains(prev => prev.map(dom => dom.id === d.id ? { ...dom, dns_status: 'failed' } : dom))
      }
    } catch {
      toast.error('DNS verification failed')
      setDomains(prev => prev.map(dom => dom.id === d.id ? { ...dom, dns_status: 'failed' } : dom))
    } finally {
      setVerifyingId(null)
    }
  }

  const columns = [
    {
      key: 'domain',
      label: 'Domain',
      render: (d: RedirectionDomain) => (
        <div className="flex items-center gap-2">
          <Globe2 size={15} className="text-gray-400 flex-shrink-0" />
          <div>
            <p className="font-medium text-gray-900 font-mono text-sm">{d.domain}</p>
            {d.is_default && (
              <span className="inline-flex items-center gap-0.5 text-[10px] font-semibold text-amber-700 mt-0.5">
                <Star size={10} className="fill-amber-400 text-amber-400" /> Global default
              </span>
            )}
          </div>
        </div>
      ),
    },
    {
      key: 'publishers',
      label: 'Assigned Users',
      render: (d: RedirectionDomain) => {
        if (!d.publisher_ids?.length) {
          return <span className="text-xs text-gray-400">All publishers (pool)</span>
        }
        return (
          <div className="flex flex-wrap gap-1 max-w-[220px]">
            {(d.publisher_names?.length ? d.publisher_names : d.publisher_ids).slice(0, 3).map((name, i) => (
              <span key={i} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-lg bg-gray-100 text-[11px] text-gray-700 font-medium">
                <Users size={10} /> {name}
              </span>
            ))}
            {d.publisher_ids.length > 3 && (
              <span className="text-[11px] text-gray-400">+{d.publisher_ids.length - 3} more</span>
            )}
          </div>
        )
      },
    },
    ...(activeTab === 'prelander' ? [{
      key: 'template',
      label: 'Template',
      render: (d: RedirectionDomain) => (
        <span className="text-xs font-medium text-gray-600 capitalize">{d.template || 'default'}</span>
      ),
    }, {
      key: 'weight',
      label: 'Weight',
      render: (d: RedirectionDomain) => (
        <span className="text-xs font-medium text-gray-600 font-mono">{(d as any).weight ?? 100}</span>
      ),
    }] : []),
    {
      key: 'dns',
      label: 'DNS',
      render: (d: RedirectionDomain) => <DnsBadge status={d.dns_status} />,
    },
    {
      key: 'status',
      label: 'Status',
      render: (d: RedirectionDomain) => <StatusBadge status={d.status} />,
    },
    {
      key: 'actions',
      label: 'Actions',
      render: (d: RedirectionDomain) => (
        <div className="flex items-center gap-1">
          <button
            onClick={() => handleVerifyDns(d)}
            disabled={verifyingId === d.id}
            title="Verify DNS"
            className="p-1.5 rounded-lg text-gray-500 hover:text-blue-600 hover:bg-blue-50 disabled:opacity-50"
          >
            {verifyingId === d.id ? <Spinner size={14} /> : <RefreshCw size={14} />}
          </button>
          <button onClick={() => openEdit(d)} className="p-1.5 rounded-lg text-gray-500 hover:text-gray-900 hover:bg-gray-100">
            <Edit size={14} />
          </button>
          <button onClick={() => { setDeleteModal(d); setDeleteConfirmText(''); setAffectedChains([]) }}
            className="p-1.5 rounded-lg text-red-400 hover:text-red-600 hover:bg-red-50">
            <Trash2 size={14} />
          </button>
        </div>
      ),
    },
  ]

  const inputClass = 'w-full px-4 py-2.5 border border-gray-200 rounded-xl text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary text-sm'

  return (
    <div className="flex min-h-screen bg-[#f8f9fb]">
      <Sidebar />
      <div className="flex-1 lg:ml-64 p-6 lg:p-8 min-w-0 overflow-x-hidden">
        {/* Header */}
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 mb-6 pt-12 lg:pt-0">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Redirection Domain Manager</h1>
            <p className="text-gray-400 text-sm mt-0.5">
              Manage link, intermediate, and last domains — assign unique domains per publisher
            </p>
          </div>
          <button
            onClick={openCreate}
            className="bg-primary hover:bg-primary-dark text-white px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2 self-start"
          >
            <Plus size={18} /> Add Domain
          </button>
        </div>

        {/* Flow diagram */}
        <div className="bg-white rounded-2xl border border-gray-100 p-5 mb-6">
          <div className="flex items-center gap-2 mb-4">
            <Info size={16} className="text-gray-400" />
            <h2 className="text-sm font-semibold text-gray-900">Redirection Flow</h2>
          </div>
          <div className="flex flex-col md:flex-row md:items-center gap-3 md:gap-2 text-sm">
            {DOMAIN_TYPES.map((t, i) => (
              <div key={t.key} className="flex items-center gap-2 flex-1 min-w-0">
                <div className={`flex items-center gap-2 px-3 py-2 rounded-xl border flex-1 min-w-0 ${t.color}`}>
                  <t.icon size={16} className="flex-shrink-0" />
                  <div className="min-w-0">
                    <p className="font-semibold truncate">{t.label}</p>
                    <p className="text-[11px] opacity-70 truncate hidden sm:block">{t.short}</p>
                  </div>
                </div>
                {i < DOMAIN_TYPES.length - 1 && (
                  <ArrowRight size={16} className="text-gray-300 flex-shrink-0 hidden md:block" />
                )}
              </div>
            ))}
          </div>
          <p className="text-xs text-gray-500 mt-3">
            Most campaigns use direct redirect and skip the Prelander domain. When enabled, the Prelander domain serves the download template with a copyable link at <code className="bg-gray-100 px-1 rounded">/d/&#123;slug&#125;</code>.
          </p>
        </div>

        {/* DNS setup card */}
        <div className="bg-gradient-to-r from-slate-900 to-slate-800 rounded-2xl p-5 mb-6 text-white">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <h3 className="font-semibold text-sm mb-1">DNS Setup</h3>
              <p className="text-xs text-slate-300 max-w-xl">
                Add your domain here, then create an <strong className="text-white">A record</strong> pointing to the server IP.
                Click Verify DNS once propagated — no manual server configuration needed.
              </p>
            </div>
            <div className="flex-shrink-0 bg-white/10 rounded-xl px-4 py-3 border border-white/10">
              <p className="text-[10px] uppercase tracking-wider text-slate-400 mb-0.5">Point A record to</p>
              <p className="font-mono font-bold text-lg">
                {serverIp || <span className="text-slate-400 text-sm font-normal">Set SERVER_PUBLIC_IP in .env</span>}
              </p>
            </div>
          </div>
        </div>

        {/* Type tabs */}
        <div className="flex gap-2 mb-4 overflow-x-auto pb-1">
          {DOMAIN_TYPES.map(t => {
            const count = domains.filter(d => d.domain_type === t.key).length
            const active = activeTab === t.key
            return (
              <button
                key={t.key}
                onClick={() => setActiveTab(t.key)}
                className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium whitespace-nowrap transition-all border ${
                  active
                    ? 'bg-primary text-white border-primary shadow-lg shadow-red-600/20'
                    : 'bg-white text-gray-600 border-gray-200 hover:border-gray-300'
                }`}
              >
                <t.icon size={16} />
                {t.label}
                <span className={`text-xs px-1.5 py-0.5 rounded-full ${active ? 'bg-white/20' : 'bg-gray-100'}`}>{count}</span>
              </button>
            )
          })}
        </div>

        {/* Type description */}
        <p className="text-sm text-gray-500 mb-4">{typeMeta.description}</p>

        {/* Table */}
        <div className="bg-white rounded-2xl border border-gray-100 p-6">
          <DataTable
            columns={columns}
            data={filtered}
            loading={loading}
            emptyMessage={`No ${typeMeta.label.toLowerCase()}s configured yet.`}
          />
        </div>

        {/* Modal */}
        {modal && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-6 w-full max-w-lg shadow-2xl border border-gray-100 max-h-[90vh] overflow-y-auto">
              <h3 className="text-lg font-bold text-gray-900 mb-1">
                {modal === 'create' ? 'Add Redirection Domain' : 'Edit Domain'}
              </h3>
              <p className="text-xs text-gray-400 mb-5">{typeMeta.label} — {typeMeta.description}</p>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-900 mb-1">Domain name</label>
                  <input
                    value={form.domain}
                    onChange={e => setForm(p => ({ ...p, domain: e.target.value }))}
                    placeholder="click.example.com"
                    className={inputClass}
                  />
                  <p className="text-xs text-gray-400 mt-1">Hostname only — no https:// prefix</p>
                </div>

                {modal === 'create' && (
                  <div>
                    <label className="block text-sm font-medium text-gray-900 mb-1">Domain type</label>
                    <select
                      value={form.domain_type}
                      onChange={e => setForm(p => ({ ...p, domain_type: e.target.value as RedirectionDomainType }))}
                      className={inputClass}
                    >
                      {DOMAIN_TYPES.map(t => (
                        <option key={t.key} value={t.key}>{t.label}</option>
                      ))}
                    </select>
                  </div>
                )}

                {form.domain_type === 'prelander' && (
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-sm font-medium text-gray-900 mb-1">Page template</label>
                      <select
                        value={form.template}
                        onChange={e => setForm(p => ({ ...p, template: e.target.value as typeof form.template }))}
                        className={inputClass}
                      >
                        <option value="default">Auto (OS-based)</option>
                        <option value="windows">Windows download page</option>
                        <option value="mac">Mac Terminal page</option>
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-900 mb-1">Weight</label>
                      <input
                        type="number"
                        min={0}
                        value={form.weight}
                        onChange={e => setForm(p => ({ ...p, weight: parseInt(e.target.value) || 0 }))}
                        className={inputClass}
                      />
                      <p className="text-xs text-gray-400 mt-1">Relative — 0 pauses traffic</p>
                    </div>
                  </div>
                )}

                <div>
                  <label className="block text-sm font-medium text-gray-900 mb-2">
                    Assign to publishers <span className="text-gray-400 font-normal">(optional)</span>
                  </label>
                  <div className="max-h-40 overflow-y-auto border border-gray-200 rounded-xl divide-y divide-gray-100">
                    {publishers.length === 0 ? (
                      <p className="text-xs text-gray-400 p-3">No publishers available</p>
                    ) : (
                      publishers.map(p => (
                        <label key={p.id} className="flex items-center gap-3 px-3 py-2.5 hover:bg-gray-50 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={form.publisher_ids.includes(p.id)}
                            onChange={() => togglePublisher(p.id)}
                            className="rounded border-gray-300 text-primary focus:ring-primary/30"
                          />
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-gray-900 truncate">{p.name}</p>
                            {p.publisher_type !== 'manual' && !p.email?.includes('@manual.invalid') && !p.email?.includes('@auto.invalid') && (
                              <p className="text-[11px] text-gray-400 truncate">{p.email}</p>
                            )}
                            <p className="text-[11px] text-gray-300 font-mono truncate">{p.public_id}</p>
                          </div>
                          {p.publisher_type === 'manual' && (
                            <span className="ml-auto flex-shrink-0 text-[10px] font-semibold px-1.5 py-0.5 rounded bg-amber-100 text-amber-700 border border-amber-200">Manual</span>
                          )}
                        </label>
                      ))
                    )}
                  </div>
                  <p className="text-xs text-gray-400 mt-1">Leave empty to use as a shared pool domain</p>
                </div>

                <div className="flex gap-4">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={form.is_default}
                      onChange={e => setForm(p => ({ ...p, is_default: e.target.checked }))}
                      className="rounded border-gray-300 text-primary focus:ring-primary/30"
                    />
                    <span className="text-sm text-gray-700">Global default for this type</span>
                  </label>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-900 mb-1">Status</label>
                  <select
                    value={form.status}
                    onChange={e => setForm(p => ({ ...p, status: e.target.value as 'active' | 'paused' }))}
                    className={inputClass}
                  >
                    <option value="active">Active</option>
                    <option value="paused">Paused</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-900 mb-1">Notes</label>
                  <textarea
                    value={form.notes}
                    onChange={e => setForm(p => ({ ...p, notes: e.target.value }))}
                    rows={2}
                    placeholder="Optional internal notes"
                    className={inputClass}
                  />
                </div>
              </div>

              <div className="flex gap-3 mt-6">
                <button
                  onClick={handleSave}
                  disabled={saving || !form.domain.trim()}
                  className="flex-1 bg-primary hover:bg-primary-dark text-white py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center disabled:bg-gray-300"
                >
                  {saving ? <Spinner size={16} /> : modal === 'create' ? 'Add Domain' : 'Save Changes'}
                </button>
                <button
                  onClick={() => setModal(null)}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── Delete Confirmation Modal ─────────────────────────────────────── */}
        {deleteModal && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-6 w-full max-w-sm text-center shadow-2xl border border-gray-100">
              <div className="w-12 h-12 rounded-xl flex items-center justify-center mx-auto mb-4 bg-red-50">
                <Trash2 className="text-red-600" size={24} />
              </div>
              <h3 className="text-lg font-bold text-gray-900 mb-2">Delete Domain</h3>
              <p className="text-gray-500 text-sm mb-2">
                Delete <strong className="text-gray-900 font-mono">{deleteModal.domain}</strong>?
                Historical statistics remain after deletion.
              </p>
              {affectedChains.length > 0 && (
                <p className="text-red-600 text-xs mb-3">
                  {affectedChains.length} redirect chain(s) use this domain and must be reconfigured manually —
                  no replacement will be assigned automatically.
                </p>
              )}
              <input
                value={deleteConfirmText}
                onChange={e => setDeleteConfirmText(e.target.value)}
                placeholder="Type DELETE to confirm"
                className={inputClass}
              />
              <div className="flex gap-3 mt-4">
                <button onClick={handleDelete} disabled={deleteLoading || deleteConfirmText.trim().toUpperCase() !== 'DELETE'}
                  className="flex-1 bg-red-600 hover:bg-red-700 text-white py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center disabled:bg-gray-300">
                  {deleteLoading ? <Spinner size={16} /> : 'Delete Domain'}
                </button>
                <button onClick={() => { setDeleteModal(null); setDeleteConfirmText('') }}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50">Cancel</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
