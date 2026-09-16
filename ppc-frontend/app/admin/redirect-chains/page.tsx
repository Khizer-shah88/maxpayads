'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  Plus, Edit, Trash2, ArrowRight, Globe2, Link2, Eye, 
  Shield, Clock, Shuffle, AlertTriangle, CheckCircle2,
  Layers, FileText, Save, X, RefreshCw
} from 'lucide-react'
import { toast } from 'sonner'
import Sidebar from '@/components/shared/Sidebar'
import ConfirmDialog from '@/components/ui/ConfirmDialog'
import { StatusBadge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/loading'
import { adminApi, redirectChainApi } from '@/lib/api'
import { useAuth } from '@/lib/hooks/useAuth'

// ─── Types ────────────────────────────────────────────────────────────────────

interface RedirectChain {
  id: string
  name: string
  anchor_domain: string
  inter_domain: string
  prelander_pool: string[]
  extra_domains: string[]
  session_validation: boolean
  cookie_lifetime: number // in minutes
  status: 'active' | 'paused' | 'archived'
  created_at: string
  total_sessions: number
  valid_sessions: number
  blocked_sessions: number
  conversion_rate: number
}

interface Domain {
  id: string
  domain: string
  domain_type: 'anchor' | 'inter' | 'prelander'
  status: 'active' | 'paused'
  dns_status: 'verified' | 'failed' | 'pending'
}

const EMPTY_CHAIN = {
  name: '',
  anchor_domain: '',
  inter_domain: '',
  extra_domains: [] as string[],
  prelander_pool: [] as string[],
  session_validation: true,
  cookie_lifetime: 60, // 1 hour
  status: 'active' as 'active' | 'paused' | 'archived',
}

// ─── Components ───────────────────────────────────────────────────────────────

function ChainFlow({ chain }: { chain: RedirectChain | typeof EMPTY_CHAIN }) {
  return (
    <div className="bg-gradient-to-r from-slate-50 to-blue-50 rounded-xl p-4 border border-gray-200">
      <div className="flex flex-col md:flex-row md:items-center gap-4 flex-wrap">
        {/* Anchor Domain */}
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <div className="w-10 h-10 bg-blue-100 rounded-xl flex items-center justify-center flex-shrink-0">
            <Globe2 size={16} className="text-blue-600" />
          </div>
          <div className="min-w-0">
            <p className="text-xs font-medium text-blue-700 uppercase tracking-wide">Anchor Domain</p>
            <p className="font-mono text-sm text-gray-900 truncate">{chain.anchor_domain || 'Not set'}</p>
            <p className="text-xs text-gray-500">Entry point + session cookie</p>
          </div>
        </div>

        <ArrowRight size={16} className="text-gray-300 flex-shrink-0 hidden md:block" />

        {/* Inter Domain */}
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <div className="w-10 h-10 bg-amber-100 rounded-xl flex items-center justify-center flex-shrink-0">
            <Layers size={16} className="text-amber-600" />
          </div>
          <div className="min-w-0">
            <p className="text-xs font-medium text-amber-700 uppercase tracking-wide">Inter Domain</p>
            <p className="font-mono text-sm text-gray-900 truncate">{chain.inter_domain || 'Not set'}</p>
            <p className="text-xs text-gray-500">Cookie validation + referrer strip</p>
          </div>
        </div>

        {/* Extra hops (configurable length: Anchor → Inter → C → D → … → N) */}
        {(chain.extra_domains || []).map((domain, i) => (
          <div key={`${domain}-${i}`} className="flex items-center gap-3">
            <ArrowRight size={16} className="text-gray-300 flex-shrink-0 hidden md:block" />
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-10 h-10 bg-violet-100 rounded-xl flex items-center justify-center flex-shrink-0">
                <Link2 size={16} className="text-violet-600" />
              </div>
              <div className="min-w-0">
                <p className="text-xs font-medium text-violet-700 uppercase tracking-wide">Extra Hop {i + 1}</p>
                <p className="font-mono text-sm text-gray-900 truncate">{domain}</p>
                <p className="text-xs text-gray-500">Intermediate hop</p>
              </div>
            </div>
          </div>
        ))}

        <ArrowRight size={16} className="text-gray-300 flex-shrink-0 hidden md:block" />

        {/* Prelander Pool */}
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <div className="w-10 h-10 bg-emerald-100 rounded-xl flex items-center justify-center flex-shrink-0">
            <Shuffle size={16} className="text-emerald-600" />
          </div>
          <div className="min-w-0">
            <p className="text-xs font-medium text-emerald-700 uppercase tracking-wide">Prelander Pool</p>
            <p className="font-mono text-sm text-gray-900">
              {chain.prelander_pool.length > 0 
                ? `${chain.prelander_pool.length} domain${chain.prelander_pool.length !== 1 ? 's' : ''}`
                : 'No domains'
              }
            </p>
            <p className="text-xs text-gray-500">Dynamic rotation per session</p>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function RedirectChainsPage() {
  const { initialize } = useAuth()
  const [chains, setChains] = useState<RedirectChain[]>([])
  const [domains, setDomains] = useState<Domain[]>([])
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState<'create' | 'edit' | null>(null)
  const [editTarget, setEditTarget] = useState<RedirectChain | null>(null)
  const [form, setForm] = useState({ ...EMPTY_CHAIN })
  const [saving, setSaving] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<RedirectChain | null>(null)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => { initialize() }, [initialize])

  // ── Load data ──────────────────────────────────────────────────────────────
  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const [chainsRes, domainsRes] = await Promise.all([
        redirectChainApi.getAll(),
        adminApi.getRedirectionDomains()
      ])
      
      setChains(chainsRes.data?.chains ?? [])
      setDomains(domainsRes.data?.domains ?? [])
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to load redirect chains')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  // ── Form handlers ──────────────────────────────────────────────────────────

  // All active Prelander domains — the default pool content. A new chain
  // starts with EVERY Prelander domain pre-selected; the admin can remove the
  // ones this chain shouldn't use.
  const prelanderDomainNames = domains
    .filter(d => d.domain_type === 'prelander' && d.status === 'active')
    .map(d => d.domain)

  const openCreate = () => {
    setForm({ ...EMPTY_CHAIN, prelander_pool: [...prelanderDomainNames] })
    setEditTarget(null)
    setModal('create')
  }

  const openEdit = (chain: RedirectChain) => {
    setEditTarget(chain)
    setForm({
      name: chain.name,
      anchor_domain: chain.anchor_domain,
      inter_domain: chain.inter_domain,
      extra_domains: [...(chain.extra_domains || [])],
      prelander_pool: [...chain.prelander_pool],
      session_validation: chain.session_validation,
      cookie_lifetime: chain.cookie_lifetime,
      status: chain.status,
    })
    setModal('edit')
  }

  const addToPool = (domain: string) => {
    if (domain && !form.prelander_pool.includes(domain)) {
      setForm(prev => ({
        ...prev,
        prelander_pool: [...prev.prelander_pool, domain]
      }))
    }
  }

  const removeFromPool = (domain: string) => {
    setForm(prev => ({
      ...prev,
      prelander_pool: prev.prelander_pool.filter(d => d !== domain)
    }))
  }

  const addExtraDomain = (domain: string) => {
    if (domain && !form.extra_domains.includes(domain)) {
      setForm(prev => ({ ...prev, extra_domains: [...prev.extra_domains, domain] }))
    }
  }

  const removeExtraDomain = (domain: string) => {
    setForm(prev => ({ ...prev, extra_domains: prev.extra_domains.filter(d => d !== domain) }))
  }

  const moveExtraDomain = (index: number, dir: -1 | 1) => {
    setForm(prev => {
      const arr = [...prev.extra_domains]
      const j = index + dir
      if (j < 0 || j >= arr.length) return prev
      ;[arr[index], arr[j]] = [arr[j], arr[index]]
      return { ...prev, extra_domains: arr }
    })
  }

  const handleSave = async () => {
    if (!form.name.trim()) {
      toast.error('Chain name is required')
      return
    }
    if (!form.anchor_domain.trim()) {
      toast.error('Anchor domain is required')
      return
    }
    if (!form.inter_domain.trim()) {
      toast.error('Inter domain is required')
      return
    }
    if (form.prelander_pool.length === 0) {
      toast.error('At least one Prelander domain is required')
      return
    }

    setSaving(true)
    try {
      const payload = {
        ...form,
        name: form.name.trim(),
        anchor_domain: form.anchor_domain.trim(),
        inter_domain: form.inter_domain.trim(),
      }

      if (modal === 'edit' && editTarget) {
        await redirectChainApi.update(editTarget.id, payload)
        toast.success('Redirect chain updated')
      } else {
        await redirectChainApi.create(payload)
        toast.success('Redirect chain created')
      }

      setModal(null)
      loadData()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to save redirect chain')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (chain: RedirectChain) => {
    setDeleting(true)
    try {
      await redirectChainApi.delete(chain.id)
      toast.success('Redirect chain deleted')
      setDeleteTarget(null)
      loadData()
    } catch {
      toast.error('Failed to delete redirect chain')
    } finally {
      setDeleting(false)
    }
  }

  // ── Filter domains ─────────────────────────────────────────────────────────
  const anchorDomains = domains.filter(d => d.domain_type === 'anchor' && d.status === 'active')
  const interDomains = domains.filter(d => d.domain_type === 'inter' && d.status === 'active')
  const prelanderDomains = domains.filter(d => d.domain_type === 'prelander' && d.status === 'active')

  const inputClass = 'w-full px-4 py-2.5 border border-gray-200 rounded-xl text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary text-sm'

  return (
    <div className="flex min-h-screen bg-[#f8f9fb]">
      <Sidebar />
      <div className="flex-1 lg:ml-64 p-6 lg:p-8 min-w-0 overflow-x-hidden">

        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 pt-12 lg:pt-0">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Redirection Chain Builder</h1>
            <p className="text-gray-400 text-sm mt-0.5">
              Admin-configured chains of configurable length — every chain works for every publisher
            </p>
          </div>
          <button
            onClick={openCreate}
            className="bg-primary hover:bg-primary-dark text-white px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2 self-start"
          >
            <Plus size={18} /> Build Chain
          </button>
        </div>

        {/* Info Card */}
        <div className="bg-gradient-to-r from-blue-900 to-indigo-900 rounded-2xl p-6 mb-6 text-white">
          <div className="flex items-start gap-4">
            <Shield size={24} className="flex-shrink-0 mt-0.5" />
            <div>
              <h3 className="font-bold text-lg mb-2">Redirection Chain Builder</h3>
              <p className="text-blue-100 text-sm leading-relaxed mb-3">
                Chains are created here in the Admin Panel — never auto-generated and never per-publisher.
                Each chain pairs an Anchor domain with an Inter domain, any number of extra hops, and a Prelander pool.
                After saving, the chain applies to ALL publishers: no chain is tied to or created for an individual publisher.
              </p>
              <div className="flex flex-wrap gap-4 text-xs">
                <div className="flex items-center gap-1.5">
                  <CheckCircle2 size={14} />
                  <span>Cookie-based session validation</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <CheckCircle2 size={14} />
                  <span>Dynamic domain rotation</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <CheckCircle2 size={14} />
                  <span>Direct access blocking</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Summary Stats */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <div className="bg-white rounded-2xl border border-gray-100 p-4">
            <div className="flex items-center gap-3 mb-2">
              <Link2 size={16} className="text-primary" />
              <span className="text-xs font-medium text-gray-500 uppercase">Active Chains</span>
            </div>
            <p className="text-2xl font-bold text-gray-900">{chains.filter(c => c.status === 'active').length}</p>
          </div>
          
          <div className="bg-white rounded-2xl border border-gray-100 p-4">
            <div className="flex items-center gap-3 mb-2">
              <Eye size={16} className="text-blue-600" />
              <span className="text-xs font-medium text-gray-500 uppercase">Total Sessions</span>
            </div>
            <p className="text-2xl font-bold text-gray-900">
              {chains.reduce((sum, c) => sum + c.total_sessions, 0).toLocaleString()}
            </p>
          </div>

          <div className="bg-white rounded-2xl border border-gray-100 p-4">
            <div className="flex items-center gap-3 mb-2">
              <CheckCircle2 size={16} className="text-emerald-600" />
              <span className="text-xs font-medium text-gray-500 uppercase">Valid Sessions</span>
            </div>
            <p className="text-2xl font-bold text-gray-900">
              {chains.reduce((sum, c) => sum + c.valid_sessions, 0).toLocaleString()}
            </p>
          </div>

          <div className="bg-white rounded-2xl border border-gray-100 p-4">
            <div className="flex items-center gap-3 mb-2">
              <AlertTriangle size={16} className="text-red-500" />
              <span className="text-xs font-medium text-gray-500 uppercase">Blocked Sessions</span>
            </div>
            <p className="text-2xl font-bold text-gray-900">
              {chains.reduce((sum, c) => sum + c.blocked_sessions, 0).toLocaleString()}
            </p>
          </div>
        </div>

        {/* Chains List */}
        <div className="bg-white rounded-2xl border border-gray-100 overflow-hidden">
          {loading ? (
            <div className="p-8 flex justify-center">
              <Spinner size={24} />
            </div>
          ) : chains.length === 0 ? (
            <div className="text-center py-20 text-gray-400">
              <Link2 size={48} className="mx-auto mb-4 opacity-30" />
              <p className="text-lg font-medium mb-2">No Redirect Chains</p>
              <p className="text-sm">Create your first 3-tier redirection chain to secure traffic flow</p>
            </div>
          ) : (
            <div className="divide-y divide-gray-100">
              {chains.map(chain => (
                <div key={chain.id} className="p-6">
                  <div className="flex items-start justify-between mb-4">
                    <div>
                      <div className="flex items-center gap-3 mb-2">
                        <h3 className="text-lg font-semibold text-gray-900">{chain.name}</h3>
                        <StatusBadge status={chain.status} />
                      </div>
                      <div className="flex items-center gap-6 text-sm text-gray-500">
                        <div className="flex items-center gap-1">
                          <Clock size={14} />
                          <span>Cookie: {chain.cookie_lifetime}min</span>
                        </div>
                        <div className="flex items-center gap-1">
                          <Shield size={14} />
                          <span>Validation: {chain.session_validation ? 'Enabled' : 'Disabled'}</span>
                        </div>
                        <div className="flex items-center gap-1">
                          <Shuffle size={14} />
                          <span>Pool: {chain.prelander_pool.length} domains</span>
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => openEdit(chain)}
                        className="p-2 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100"
                        title="Edit chain"
                      >
                        <Edit size={16} />
                      </button>
                      <button
                        onClick={() => setDeleteTarget(chain)}
                        className="p-2 rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50"
                        title="Delete chain"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </div>

                  {/* Chain Flow Visualization */}
                  <ChainFlow chain={chain} />

                  {/* Stats */}
                  <div className="grid grid-cols-4 gap-4 mt-4 pt-4 border-t border-gray-100">
                    <div className="text-center">
                      <p className="text-lg font-semibold text-gray-900">{chain.total_sessions.toLocaleString()}</p>
                      <p className="text-xs text-gray-500">Total Sessions</p>
                    </div>
                    <div className="text-center">
                      <p className="text-lg font-semibold text-emerald-600">{chain.valid_sessions.toLocaleString()}</p>
                      <p className="text-xs text-gray-500">Valid</p>
                    </div>
                    <div className="text-center">
                      <p className="text-lg font-semibold text-red-500">{chain.blocked_sessions.toLocaleString()}</p>
                      <p className="text-xs text-gray-500">Blocked</p>
                    </div>
                    <div className="text-center">
                      <p className="text-lg font-semibold text-blue-600">{chain.conversion_rate}%</p>
                      <p className="text-xs text-gray-500">Conversion</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Create/Edit Modal */}
        {modal && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-6 w-full max-w-3xl shadow-2xl border border-gray-100 max-h-[90vh] overflow-y-auto">
              <h3 className="text-xl font-bold text-gray-900 mb-6">
                {modal === 'create' ? 'Build Redirect Chain' : `Edit Chain: ${editTarget?.name}`}
              </h3>

              <div className="space-y-6">
                {/* Chain Name */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">Chain Name</label>
                  <input
                    type="text"
                    value={form.name}
                    onChange={e => setForm(prev => ({ ...prev, name: e.target.value }))}
                    placeholder="e.g. High Security Campaign Chain"
                    className={inputClass}
                  />
                </div>

                {/* Flow Visualization */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">Chain Flow Preview</label>
                  <ChainFlow chain={form} />
                </div>

                {/* Domain Selection */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {/* Anchor Domain */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Anchor Domain <span className="text-red-500">*</span>
                    </label>
                    <select
                      value={form.anchor_domain}
                      onChange={e => setForm(prev => ({ ...prev, anchor_domain: e.target.value }))}
                      className={inputClass}
                    >
                      <option value="">Select anchor domain...</option>
                      {anchorDomains.map(domain => (
                        <option key={domain.id} value={domain.domain}>
                          {domain.domain}
                        </option>
                      ))}
                    </select>
                    <p className="text-xs text-gray-500 mt-1">
                      Entry point that generates session cookies
                    </p>
                  </div>

                  {/* Inter Domain */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Inter Domain <span className="text-red-500">*</span>
                    </label>
                    <select
                      value={form.inter_domain}
                      onChange={e => setForm(prev => ({ ...prev, inter_domain: e.target.value }))}
                      className={inputClass}
                    >
                      <option value="">Select Inter domain...</option>
                      {interDomains.map(domain => (
                        <option key={domain.id} value={domain.domain}>
                          {domain.domain}
                        </option>
                      ))}
                    </select>
                    <p className="text-xs text-gray-500 mt-1">
                      Validates session cookies before forwarding
                    </p>
                  </div>
                </div>

                {/* Extra Hops — configurable chain length */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Extra Hops <span className="text-gray-400 font-normal">(optional — configurable chain length)</span>
                  </label>

                  {/* Add Domain Selector */}
                  <div className="flex gap-2 mb-3">
                    <select
                      className={`${inputClass} flex-1`}
                      onChange={e => {
                        if (e.target.value) {
                          addExtraDomain(e.target.value)
                          e.target.value = ''
                        }
                      }}
                    >
                      <option value="">Add intermediate hop...</option>
                      {domains
                        .filter(d => d.status === 'active' && !form.extra_domains.includes(d.domain))
                        .map(domain => (
                          <option key={domain.id} value={domain.domain}>
                            [{domain.domain_type}] {domain.domain}
                          </option>
                        ))}
                    </select>
                  </div>

                  {/* Hop Display */}
                  <div className="space-y-2">
                    {form.extra_domains.length === 0 ? (
                      <p className="text-sm text-gray-400 py-3 px-4 bg-gray-50 rounded-xl text-center">
                        No extra hops — chain is Anchor → Inter → Prelander Pool
                      </p>
                    ) : (
                      form.extra_domains.map((domain, index) => (
                        <div key={domain} className="flex items-center justify-between p-3 bg-violet-50/50 rounded-xl">
                          <div className="flex items-center gap-3">
                            <span className="text-xs font-medium text-violet-600 bg-white px-2 py-1 rounded">
                              #{index + 1}
                            </span>
                            <span className="font-mono text-sm text-gray-900">{domain}</span>
                          </div>
                          <div className="flex items-center gap-1">
                            <button onClick={() => moveExtraDomain(index, -1)} disabled={index === 0}
                              className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-white disabled:opacity-30"
                              title="Move up">↑</button>
                            <button onClick={() => moveExtraDomain(index, 1)} disabled={index === form.extra_domains.length - 1}
                              className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-white disabled:opacity-30"
                              title="Move down">↓</button>
                            <button
                              onClick={() => removeExtraDomain(domain)}
                              className="p-1.5 rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50"
                            >
                              <X size={14} />
                            </button>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                  <p className="text-xs text-gray-500 mt-2">
                    Ordered hops traversed after the Inter domain: Anchor → Inter → C → D → … → N → Prelander Pool
                  </p>
                </div>

                {/* Prelander Pool */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Prelander Domain Pool <span className="text-red-500">*</span>
                  </label>
                  <p className="text-xs text-gray-500 mb-2">
                    Pre-populated with every active Prelander domain — remove the ones this chain should not use.
                  </p>
                  
                  {/* Add Domain Selector — lists ALL active Prelander domains
                      (pool entries are pre-populated; picking an already-added
                      domain is a no-op) */}
                  <div className="flex gap-2 mb-3">
                    <select
                      className={`${inputClass} flex-1`}
                      onChange={e => {
                        if (e.target.value) {
                          addToPool(e.target.value)
                          e.target.value = ''
                        }
                      }}
                    >
                      <option value="">Add domain to pool...</option>
                      {prelanderDomains.map(domain => (
                        <option key={domain.id} value={domain.domain}>
                          {domain.domain}{form.prelander_pool.includes(domain.domain) ? '  ✓ (in pool)' : ''}
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* Pool Display */}
                  <div className="space-y-2">
                    {form.prelander_pool.length === 0 ? (
                      <p className="text-sm text-gray-400 py-3 px-4 bg-gray-50 rounded-xl text-center">
                        No domains in pool. Add at least one domain.
                      </p>
                    ) : (
                      form.prelander_pool.map((domain, index) => (
                        <div key={domain} className="flex items-center justify-between p-3 bg-gray-50 rounded-xl">
                          <div className="flex items-center gap-3">
                            <span className="text-xs font-medium text-gray-500 bg-white px-2 py-1 rounded">
                              #{index + 1}
                            </span>
                            <span className="font-mono text-sm text-gray-900">{domain}</span>
                          </div>
                          <button
                            onClick={() => removeFromPool(domain)}
                            className="p-1.5 rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50"
                          >
                            <X size={14} />
                          </button>
                        </div>
                      ))
                    )}
                  </div>
                  <p className="text-xs text-gray-500 mt-2">
                    Domains are rotated dynamically per session to avoid detection
                  </p>
                </div>

                {/* Settings */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">Cookie Lifetime</label>
                    <select
                      value={form.cookie_lifetime}
                      onChange={e => setForm(prev => ({ ...prev, cookie_lifetime: parseInt(e.target.value) }))}
                      className={inputClass}
                    >
                      <option value={30}>30 minutes</option>
                      <option value={60}>1 hour</option>
                      <option value={120}>2 hours</option>
                      <option value={240}>4 hours</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">Session Validation</label>
                    <select
                      value={form.session_validation ? 'enabled' : 'disabled'}
                      onChange={e => setForm(prev => ({ ...prev, session_validation: e.target.value === 'enabled' }))}
                      className={inputClass}
                    >
                      <option value="enabled">Enabled</option>
                      <option value="disabled">Disabled</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">Status</label>
                    <select
                      value={form.status}
                      onChange={e => setForm(prev => ({ ...prev, status: e.target.value as typeof form.status }))}
                      className={inputClass}
                    >
                      <option value="active">Active</option>
                      <option value="paused">Paused</option>
                      <option value="archived">Archived</option>
                    </select>
                  </div>
                </div>
              </div>

              {/* Modal Actions */}
              <div className="flex gap-3 mt-8">
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="flex-1 bg-primary hover:bg-primary-dark text-white py-3 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 disabled:bg-gray-300"
                >
                  {saving ? (
                    <Spinner size={16} />
                  ) : (
                    <>
                      <Save size={16} />
                      {modal === 'create' ? 'Build Chain' : 'Save Changes'}
                    </>
                  )}
                </button>
                <button
                  onClick={() => setModal(null)}
                  className="flex-1 py-3 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── Delete Chain Confirmation ────────────────────────────────────── */}
        <ConfirmDialog
          open={deleteTarget !== null}
          title="Delete Redirect Chain"
          message={<>Delete redirect chain <strong className="text-gray-900">{deleteTarget?.name}</strong>? Traffic using this chain will fall back to Domain Glossary routing. This cannot be undone.</>}
          confirmLabel="Delete Chain"
          loading={deleting}
          onConfirm={() => { if (deleteTarget) handleDelete(deleteTarget) }}
          onCancel={() => setDeleteTarget(null)}
        />

      </div>
    </div>
  )
}