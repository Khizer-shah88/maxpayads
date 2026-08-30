'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  Plus, Edit, Trash2, Play, Link, ChevronRight, Activity,
  Globe, LayoutTemplate, ExternalLink, Settings, AlertTriangle,
} from 'lucide-react'
import { toast } from 'sonner'
import Sidebar from '@/components/shared/Sidebar'
import { StatusBadge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/loading'
import { redirectChainApi, prlanderTemplateApi } from '@/lib/api'
import { useAuth } from '@/lib/hooks/useAuth'

// ─── Types ────────────────────────────────────────────────────────────────────

interface RedirectStep {
  step_order: number
  step_type: 'domain' | 'prelander' | 'offer'
  domain?: string
  prelander_template_id?: string
  offer_url?: string
  geo_conditions: string[]
  device_conditions: string[]
  weight: number
  delay_seconds: number
  custom_headers: Record<string, string>
}

interface RedirectChain {
  id: string
  name: string
  description?: string
  status: 'active' | 'paused' | 'archived'
  entry_domain: string
  steps: RedirectStep[]
  enable_spinning: boolean
  spinning_rules: Record<string, any>
  fallback_url?: string
  error_redirect_url?: string
  total_hits: number
  successful_completions: number
  error_count: number
  created_by: string
  tags: string[]
  notes?: string
  created_at: string
  updated_at: string
}

interface PrlanderTemplate {
  id: string
  name: string
  status: string
  os_type: string
}

const EMPTY_FORM = {
  name: '',
  description: '',
  entry_domain: '',
  steps: [] as RedirectStep[],
  enable_spinning: false,
  spinning_rules: {},
  fallback_url: '',
  error_redirect_url: '',
  tags: '',
  notes: '',
}
const EMPTY_STEP: RedirectStep = {
  step_order: 1,
  step_type: 'domain',
  domain: '',
  prelander_template_id: '',
  offer_url: '',
  geo_conditions: [],
  device_conditions: [],
  weight: 100,
  delay_seconds: 0,
  custom_headers: {},
}

// ─── Step Type Icons ──────────────────────────────────────────────────────────

function StepIcon({ stepType }: { stepType: string }) {
  switch (stepType) {
    case 'domain': return <Globe size={16} className="text-blue-500" />
    case 'prelander': return <LayoutTemplate size={16} className="text-purple-500" />
    case 'offer': return <ExternalLink size={16} className="text-green-500" />
    default: return <Link size={16} className="text-gray-400" />
  }
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function RedirectChainsPage() {
  const { initialize } = useAuth()
  const [chains, setChains] = useState<RedirectChain[]>([])
  const [templates, setTemplates] = useState<PrlanderTemplate[]>([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState('')
  const [modal, setModal] = useState<'create' | 'edit' | 'view' | 'analytics' | null>(null)
  const [selected, setSelected] = useState<RedirectChain | null>(null)
  const [form, setForm] = useState({ ...EMPTY_FORM })
  const [saving, setSaving] = useState(false)
  const [executing, setExecuting] = useState<string | null>(null)

  useEffect(() => { initialize() }, [initialize])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [chainsRes, templatesRes] = await Promise.all([
        redirectChainApi.getAll({ status: statusFilter || undefined }),
        prlanderTemplateApi.getAll({ status: 'active' }),
      ])
      setChains(chainsRes.data?.chains ?? [])
      setTemplates(templatesRes.data?.templates ?? [])
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to load redirect chains')
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => {
    load()
  }, [load])
  const openCreate = () => {
    setSelected(null)
    setForm({ ...EMPTY_FORM })
    setModal('create')
  }

  const openEdit = (chain: RedirectChain) => {
    setSelected(chain)
    setForm({
      name: chain.name,
      description: chain.description || '',
      entry_domain: chain.entry_domain,
      steps: [...chain.steps],
      enable_spinning: chain.enable_spinning,
      spinning_rules: chain.spinning_rules,
      fallback_url: chain.fallback_url || '',
      error_redirect_url: chain.error_redirect_url || '',
      tags: chain.tags.join(', '),
      notes: chain.notes || '',
    })
    setModal('edit')
  }

  const openView = (chain: RedirectChain) => {
    setSelected(chain)
    setModal('view')
  }

  const addStep = () => {
    const newStep = { 
      ...EMPTY_STEP, 
      step_order: form.steps.length + 1 
    }
    setForm(p => ({ ...p, steps: [...p.steps, newStep] }))
  }

  const removeStep = (index: number) => {
    const updatedSteps = form.steps.filter((_, i) => i !== index)
    // Reorder steps
    updatedSteps.forEach((step, i) => step.step_order = i + 1)
    setForm(p => ({ ...p, steps: updatedSteps }))
  }

  const updateStep = (index: number, updates: Partial<RedirectStep>) => {
    const updatedSteps = [...form.steps]
    updatedSteps[index] = { ...updatedSteps[index], ...updates }
    setForm(p => ({ ...p, steps: updatedSteps }))
  }

  const handleSave = async () => {
    if (!form.name.trim() || !form.entry_domain.trim()) {
      toast.error('Name and entry domain are required')
      return
    }

    setSaving(true)
    try {
      const data = {
        ...form,
        tags: form.tags.split(',').map(t => t.trim()).filter(Boolean),
      }

      if (modal === 'create') {
        await redirectChainApi.create(data)
        toast.success('Redirect chain created')
      } else {
        await redirectChainApi.update(selected!.id, data)
        toast.success('Redirect chain updated')
      }
      
      setModal(null)
      load()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to save chain')
    } finally {
      setSaving(false)
    }
  }
  const handleExecute = async (chainId: string) => {
    setExecuting(chainId)
    try {
      const res = await redirectChainApi.execute(chainId)
      if (res.data?.final_destination) {
        toast.success('Chain executed successfully')
        window.open(res.data.final_destination, '_blank')
      } else {
        toast.error(res.data?.message || 'Chain execution failed')
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to execute chain')
    } finally {
      setExecuting(null)
    }
  }

  const handleDelete = async (chain: RedirectChain) => {
    if (!confirm(`Archive redirect chain "${chain.name}"?`)) return
    
    try {
      await redirectChainApi.delete(chain.id)
      toast.success('Redirect chain archived')
      load()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to archive chain')
    }
  }

  const inp = "w-full px-3 py-2 border border-gray-200 rounded-xl text-gray-700 focus:outline-none focus:ring-2 focus:ring-primary/30 text-sm"

  return (
    <div className="flex min-h-screen bg-[#f8f9fb]">
      <Sidebar />
      <div className="flex-1 lg:ml-64 p-6 lg:p-8">

        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 pt-12 lg:pt-0">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Redirect Chain Builder</h1>
            <p className="text-gray-400 text-sm mt-0.5">
              Create sequential domain routing: Anchor → Inter-Domain → Pre-Lander → Target
            </p>
          </div>
          <button onClick={openCreate}
            className="bg-primary hover:bg-primary-dark text-white px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2 self-start">
            <Plus size={18} /> Create Chain
          </button>
        </div>

        {/* Filters */}
        <div className="bg-white rounded-2xl border border-gray-100 p-4 mb-6 flex flex-wrap gap-3 items-center">
          <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-xl text-sm text-gray-700 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20">
            <option value="">All Status</option>
            <option value="active">Active</option>
            <option value="paused">Paused</option>
            <option value="archived">Archived</option>
          </select>
          <span className="text-sm text-gray-400 ml-auto">{chains.length} chain{chains.length !== 1 ? 's' : ''}</span>
        </div>
        {/* Chains List */}
        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[1,2,3,4].map(i => <div key={i} className="shimmer h-48 rounded-2xl" />)}
          </div>
        ) : chains.length === 0 ? (
          <div className="text-center py-20 text-gray-400">
            <Link size={48} className="mx-auto mb-4 opacity-30" />
            <p className="text-base mb-4">No redirect chains yet</p>
            <button onClick={openCreate}
              className="bg-primary hover:bg-primary-dark text-white px-6 py-2.5 rounded-xl text-sm font-semibold inline-flex items-center gap-2">
              <Plus size={16} /> Create First Chain
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {chains.map(chain => {
              const successRate = chain.total_hits > 0 ? 
                (chain.successful_completions / chain.total_hits * 100) : 0
              
              return (
                <div key={chain.id} className="bg-white rounded-2xl border border-gray-100 p-5">
                  <div className="flex items-start justify-between mb-4">
                    <div className="flex-1 min-w-0">
                      <h3 className="font-semibold text-gray-900 truncate">{chain.name}</h3>
                      {chain.description && (
                        <p className="text-xs text-gray-400 mt-0.5 line-clamp-2">{chain.description}</p>
                      )}
                    </div>
                    <StatusBadge status={chain.status} />
                  </div>

                  {/* Entry Domain */}
                  <div className="flex items-center gap-2 mb-3 p-2 bg-gray-50 rounded-lg">
                    <Globe size={14} className="text-blue-500 flex-shrink-0" />
                    <span className="text-sm text-gray-700 truncate">{chain.entry_domain}</span>
                  </div>

                  {/* Steps Flow */}
                  {chain.steps.length > 0 && (
                    <div className="mb-4">
                      <p className="text-xs font-medium text-gray-500 mb-2">CHAIN FLOW</p>
                      <div className="flex items-center gap-1 flex-wrap">
                        {chain.steps.slice(0, 3).map((step, i) => (
                          <div key={i} className="flex items-center gap-1">
                            <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-gray-100 text-xs">
                              <StepIcon stepType={step.step_type} />
                              <span className="text-gray-700 capitalize">{step.step_type}</span>
                            </div>
                            {i < Math.min(chain.steps.length, 3) - 1 && (
                              <ChevronRight size={12} className="text-gray-300" />
                            )}
                          </div>
                        ))}
                        {chain.steps.length > 3 && (
                          <span className="text-xs text-gray-400 ml-1">+{chain.steps.length - 3}</span>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Stats */}
                  <div className="grid grid-cols-3 gap-3 mb-4 text-center">
                    <div>
                      <p className="text-xs text-gray-400">Hits</p>
                      <p className="text-sm font-semibold text-gray-700">{chain.total_hits.toLocaleString()}</p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-400">Success</p>
                      <p className="text-sm font-semibold text-emerald-600">{chain.successful_completions.toLocaleString()}</p>
                    </div>
                    <div>
                      <p className="text-xs text-gray-400">Rate</p>
                      <p className={`text-sm font-semibold ${
                        successRate >= 80 ? 'text-emerald-600' :
                        successRate >= 60 ? 'text-amber-600' : 'text-red-500'
                      }`}>
                        {successRate.toFixed(1)}%
                      </p>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-1.5">
                    {chain.status === 'active' && (
                      <button 
                        onClick={() => handleExecute(chain.id)}
                        disabled={executing === chain.id}
                        className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl text-xs font-medium text-emerald-600 hover:bg-emerald-50 border border-emerald-200 transition-colors disabled:opacity-50"
                      >
                        {executing === chain.id ? <Spinner size={13} /> : <Play size={13} />}
                        Test
                      </button>
                    )}
                    <button onClick={() => openView(chain)}
                      className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl text-xs font-medium text-gray-600 hover:bg-gray-50 border border-gray-200 transition-colors">
                      <Activity size={13} /> View
                    </button>
                    <button onClick={() => openEdit(chain)}
                      className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl text-xs font-medium text-primary hover:bg-primary/5 border border-primary/20 transition-colors">
                      <Edit size={13} /> Edit
                    </button>
                    <button onClick={() => handleDelete(chain)} title="Archive"
                      className="p-2 rounded-xl text-red-400 hover:bg-red-50 border border-red-200 transition-colors">
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
        {/* Create/Edit Modal */}
        {(modal === 'create' || modal === 'edit') && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-6 w-full max-w-4xl shadow-2xl border border-gray-100 max-h-[92vh] overflow-y-auto">
              <h3 className="text-lg font-bold text-gray-900 mb-5">
                {modal === 'create' ? 'Create Redirect Chain' : `Edit — ${selected?.name}`}
              </h3>

              <div className="space-y-6">
                {/* Basic Info */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Chain Name <span className="text-red-500">*</span>
                    </label>
                    <input value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))}
                      placeholder="e.g. Main Funnel Chain" className={inp} />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Entry Domain <span className="text-red-500">*</span>
                    </label>
                    <input value={form.entry_domain} onChange={e => setForm(p => ({ ...p, entry_domain: e.target.value }))}
                      placeholder="domain.com" className={inp} />
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                  <input value={form.description} onChange={e => setForm(p => ({ ...p, description: e.target.value }))}
                    placeholder="Optional description" className={inp} />
                </div>

                {/* Chain Steps */}
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <h4 className="text-sm font-semibold text-gray-700">Redirect Steps</h4>
                    <button onClick={addStep}
                      className="bg-primary/10 hover:bg-primary/20 text-primary px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1">
                      <Plus size={14} /> Add Step
                    </button>
                  </div>

                  {form.steps.length === 0 ? (
                    <div className="text-center py-8 border border-dashed border-gray-200 rounded-xl">
                      <Link size={32} className="mx-auto text-gray-300 mb-2" />
                      <p className="text-sm text-gray-400">No steps added yet</p>
                      <button onClick={addStep}
                        className="mt-2 text-primary hover:underline text-sm">
                        Add first step
                      </button>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {form.steps.map((step, index) => (
                        <div key={index} className="border border-gray-200 rounded-xl p-4">
                          <div className="flex items-center justify-between mb-3">
                            <div className="flex items-center gap-2">
                              <span className="w-6 h-6 bg-primary text-white rounded-full text-xs flex items-center justify-center font-semibold">
                                {step.step_order}
                              </span>
                              <StepIcon stepType={step.step_type} />
                              <span className="text-sm font-medium text-gray-700 capitalize">
                                {step.step_type} Step
                              </span>
                            </div>
                            <button onClick={() => removeStep(index)}
                              className="text-red-400 hover:bg-red-50 p-1.5 rounded-lg">
                              <Trash2 size={14} />
                            </button>
                          </div>

                          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                            <div>
                              <label className="block text-sm font-medium text-gray-600 mb-1">Step Type</label>
                              <select 
                                value={step.step_type} 
                                onChange={e => updateStep(index, { step_type: e.target.value as any })}
                                className={inp}
                              >
                                <option value="domain">Domain Redirect</option>
                                <option value="prelander">Prelander Template</option>
                                <option value="offer">Final Offer URL</option>
                              </select>
                            </div>

                            {step.step_type === 'domain' && (
                              <div className="md:col-span-2">
                                <label className="block text-sm font-medium text-gray-600 mb-1">Domain</label>
                                <input 
                                  value={step.domain || ''} 
                                  onChange={e => updateStep(index, { domain: e.target.value })}
                                  placeholder="intermediate-domain.com" 
                                  className={inp} 
                                />
                              </div>
                            )}

                            {step.step_type === 'prelander' && (
                              <div className="md:col-span-2">
                                <label className="block text-sm font-medium text-gray-600 mb-1">Template</label>
                                <select 
                                  value={step.prelander_template_id || ''} 
                                  onChange={e => updateStep(index, { prelander_template_id: e.target.value })}
                                  className={inp}
                                >
                                  <option value="">Select template...</option>
                                  {templates.map(t => (
                                    <option key={t.id} value={t.id}>{t.name} ({t.os_type})</option>
                                  ))}
                                </select>
                              </div>
                            )}

                            {step.step_type === 'offer' && (
                              <div className="md:col-span-2">
                                <label className="block text-sm font-medium text-gray-600 mb-1">Offer URL</label>
                                <input 
                                  value={step.offer_url || ''} 
                                  onChange={e => updateStep(index, { offer_url: e.target.value })}
                                  placeholder="https://final-offer.com" 
                                  className={inp} 
                                />
                              </div>
                            )}
                          </div>

                          {/* Advanced Options */}
                          <details className="mt-3">
                            <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-600">
                              Advanced Options
                            </summary>
                            <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-3">
                              <div>
                                <label className="block text-xs text-gray-500 mb-1">Weight %</label>
                                <input 
                                  type="number" 
                                  min="0" 
                                  max="100"
                                  value={step.weight} 
                                  onChange={e => updateStep(index, { weight: parseInt(e.target.value) || 100 })}
                                  className={inp + " text-xs"} 
                                />
                              </div>
                              <div>
                                <label className="block text-xs text-gray-500 mb-1">Delay (sec)</label>
                                <input 
                                  type="number" 
                                  min="0"
                                  value={step.delay_seconds} 
                                  onChange={e => updateStep(index, { delay_seconds: parseInt(e.target.value) || 0 })}
                                  className={inp + " text-xs"} 
                                />
                              </div>
                              <div>
                                <label className="block text-xs text-gray-500 mb-1">Geo Conditions</label>
                                <input 
                                  value={step.geo_conditions.join(', ')} 
                                  onChange={e => updateStep(index, { geo_conditions: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })}
                                  placeholder="US, GB, CA"
                                  className={inp + " text-xs"} 
                                />
                              </div>
                            </div>
                          </details>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                {/* Advanced Chain Options */}
                <div className="border-t border-gray-100 pt-4">
                  <h4 className="text-sm font-semibold text-gray-700 mb-3">Chain Configuration</h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Fallback URL</label>
                      <input value={form.fallback_url} onChange={e => setForm(p => ({ ...p, fallback_url: e.target.value }))}
                        placeholder="https://fallback.com" className={inp} />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Error Redirect URL</label>
                      <input value={form.error_redirect_url} onChange={e => setForm(p => ({ ...p, error_redirect_url: e.target.value }))}
                        placeholder="https://error-page.com" className={inp} />
                    </div>
                  </div>

                  <div className="mt-4">
                    <label className="flex items-center gap-2.5 cursor-pointer select-none">
                      <input type="checkbox" checked={form.enable_spinning}
                        onChange={e => setForm(p => ({ ...p, enable_spinning: e.target.checked }))}
                        className="rounded border-gray-300 text-primary focus:ring-primary/30 w-4 h-4" />
                      <span className="text-sm text-gray-700">Enable prelander spinning/rotation</span>
                    </label>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Tags</label>
                      <input value={form.tags} onChange={e => setForm(p => ({ ...p, tags: e.target.value }))}
                        placeholder="funnel, main, test" className={inp} />
                    </div>
                  </div>

                  <div className="mt-4">
                    <label className="block text-sm font-medium text-gray-700 mb-1">Notes</label>
                    <textarea value={form.notes} onChange={e => setForm(p => ({ ...p, notes: e.target.value }))}
                      rows={2} placeholder="Internal notes..." className={inp} />
                  </div>
                </div>
              </div>

              <div className="flex gap-3 mt-6">
                <button onClick={handleSave} disabled={saving || !form.name.trim() || !form.entry_domain.trim()}
                  className="flex-1 bg-primary hover:bg-primary-dark text-white py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 disabled:bg-gray-300">
                  {saving ? <Spinner size={16} /> : (modal === 'create' ? 'Create Chain' : 'Save Changes')}
                </button>
                <button onClick={() => setModal(null)}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50">
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}

        {/* View Modal */}
        {modal === 'view' && selected && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-6 w-full max-w-3xl shadow-2xl border border-gray-100 max-h-[90vh] overflow-y-auto">
              <div className="flex items-start justify-between gap-3 mb-5">
                <div>
                  <h3 className="text-lg font-bold text-gray-900">{selected.name}</h3>
                  {selected.description && <p className="text-sm text-gray-400 mt-0.5">{selected.description}</p>}
                </div>
                <StatusBadge status={selected.status} />
              </div>

              {/* Chain Flow Visualization */}
              <div className="mb-6">
                <h4 className="text-sm font-semibold text-gray-700 mb-3">Chain Flow</h4>
                <div className="flex items-center gap-2 flex-wrap">
                  <div className="flex items-center gap-2 px-3 py-2 bg-blue-50 border border-blue-200 rounded-lg">
                    <Globe size={16} className="text-blue-500" />
                    <span className="text-sm text-blue-700 font-medium">Entry: {selected.entry_domain}</span>
                  </div>
                  {selected.steps.map((step, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <ChevronRight size={16} className="text-gray-300" />
                      <div className="flex items-center gap-2 px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg">
                        <StepIcon stepType={step.step_type} />
                        <span className="text-sm text-gray-700">
                          {step.step_type === 'domain' && step.domain}
                          {step.step_type === 'prelander' && 'Template'}
                          {step.step_type === 'offer' && 'Final Offer'}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Performance Stats */}
              <div className="grid grid-cols-4 gap-4 mb-6">
                <div className="text-center p-4 bg-gray-50 rounded-xl">
                  <p className="text-2xl font-bold text-gray-900">{selected.total_hits.toLocaleString()}</p>
                  <p className="text-xs text-gray-400">Total Hits</p>
                </div>
                <div className="text-center p-4 bg-emerald-50 rounded-xl">
                  <p className="text-2xl font-bold text-emerald-600">{selected.successful_completions.toLocaleString()}</p>
                  <p className="text-xs text-gray-400">Successful</p>
                </div>
                <div className="text-center p-4 bg-red-50 rounded-xl">
                  <p className="text-2xl font-bold text-red-500">{selected.error_count.toLocaleString()}</p>
                  <p className="text-xs text-gray-400">Errors</p>
                </div>
                <div className="text-center p-4 bg-blue-50 rounded-xl">
                  <p className="text-2xl font-bold text-blue-600">
                    {selected.total_hits > 0 ? 
                      (selected.successful_completions / selected.total_hits * 100).toFixed(1) : '0'
                    }%
                  </p>
                  <p className="text-xs text-gray-400">Success Rate</p>
                </div>
              </div>

              {/* Chain Details */}
              <div className="space-y-4">
                {selected.fallback_url && (
                  <div className="flex gap-2 text-sm">
                    <span className="text-gray-400 min-w-[80px]">Fallback:</span>
                    <a href={selected.fallback_url} target="_blank" rel="noreferrer"
                      className="text-primary hover:underline truncate">{selected.fallback_url}</a>
                  </div>
                )}
                {selected.error_redirect_url && (
                  <div className="flex gap-2 text-sm">
                    <span className="text-gray-400 min-w-[80px]">Error URL:</span>
                    <a href={selected.error_redirect_url} target="_blank" rel="noreferrer"
                      className="text-primary hover:underline truncate">{selected.error_redirect_url}</a>
                  </div>
                )}
                {selected.enable_spinning && (
                  <div className="flex gap-2 text-sm">
                    <span className="text-gray-400 min-w-[80px]">Spinning:</span>
                    <span className="text-emerald-600 font-medium">Enabled</span>
                  </div>
                )}
                {selected.tags.length > 0 && (
                  <div className="flex gap-2 text-sm">
                    <span className="text-gray-400 min-w-[80px]">Tags:</span>
                    <div className="flex flex-wrap gap-1">
                      {selected.tags.map(tag => (
                        <span key={tag} className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs">
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {selected.notes && (
                  <div className="flex gap-2 text-sm">
                    <span className="text-gray-400 min-w-[80px]">Notes:</span>
                    <span className="text-gray-700">{selected.notes}</span>
                  </div>
                )}
              </div>

              <div className="flex gap-3 mt-6">
                <button onClick={() => { setModal(null); openEdit(selected) }}
                  className="flex-1 bg-primary hover:bg-primary-dark text-white py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center gap-2">
                  <Edit size={15} /> Edit Chain
                </button>
                {selected.status === 'active' && (
                  <button onClick={() => handleExecute(selected.id)}
                    className="flex-1 bg-emerald-500 hover:bg-emerald-600 text-white py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center gap-2">
                    <Play size={15} /> Test Execute
                  </button>
                )}
                <button onClick={() => setModal(null)}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50">
                  Close
                </button>
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  )
}