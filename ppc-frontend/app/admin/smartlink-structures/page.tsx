'use client'

import { useState, useEffect, useCallback } from 'react'
import { Plus, Edit, Trash2, Link2, Star, X, Copy, Wand2 } from 'lucide-react'
import { toast } from 'sonner'
import Sidebar from '@/components/shared/Sidebar'
import ConfirmDialog from '@/components/ui/ConfirmDialog'
import { StatusBadge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/loading'
import { adminApi } from '@/lib/api'
import { useAuth } from '@/lib/hooks/useAuth'

interface SmartlinkStructure {
  id: string
  name: string
  publisher_param: string
  website_param: string | null
  include_website: boolean
  extra_params: { key: string; value: string }[]
  is_default: boolean
  status: 'active' | 'paused'
  pattern: string
  created_at?: string | null
}

const EMPTY_FORM = {
  name: '',
  publisher_param: 'pub',
  website_param: 'site',
  include_website: true,
  extra_params: [] as { key: string; value: string }[],
  is_default: false,
  status: 'active' as 'active' | 'paused',
}

export default function SmartlinkStructuresPage() {
  const { initialize } = useAuth()
  const [structures, setStructures] = useState<SmartlinkStructure[]>([])
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState<'create' | 'edit' | null>(null)
  const [editId, setEditId] = useState<string | null>(null)
  const [form, setForm] = useState({ ...EMPTY_FORM })
  const [saving, setSaving] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<SmartlinkStructure | null>(null)
  const [deleting, setDeleting] = useState(false)

  // Generator state
  const [genStructureId, setGenStructureId] = useState('')
  const [genDomain, setGenDomain] = useState('')
  const [genPublisher, setGenPublisher] = useState('')
  const [genSite, setGenSite] = useState('')
  const [genResult, setGenResult] = useState('')
  const [generating, setGenerating] = useState(false)

  useEffect(() => { initialize() }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await adminApi.getSmartlinkStructures()
      setStructures(res.data?.structures ?? [])
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to load structures')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const inp = 'w-full px-4 py-2.5 border border-gray-200 rounded-xl text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary text-sm'

  const openCreate = () => {
    setForm({ ...EMPTY_FORM })
    setEditId(null)
    setModal('create')
  }

  const openEdit = (s: SmartlinkStructure) => {
    setEditId(s.id)
    setForm({
      name: s.name,
      publisher_param: s.publisher_param,
      website_param: s.website_param || '',
      include_website: s.include_website,
      extra_params: s.extra_params.map(e => ({ ...e })),
      is_default: s.is_default,
      status: s.status,
    })
    setModal('edit')
  }

  const preview = `https://{DOMAIN}/?${form.publisher_param}={PUBLISHER_ID}${form.include_website && form.website_param ? `&${form.website_param}={SITE_ID}` : ''}${form.extra_params.filter(e => e.key).map(e => `&${e.key}=${e.value}`).join('')}`

  const handleSave = async () => {
    if (!form.name.trim()) { toast.error('Name is required'); return }
    if (!form.publisher_param.trim()) { toast.error('Publisher parameter is required'); return }
    setSaving(true)
    try {
      const payload = {
        name: form.name.trim(),
        publisher_param: form.publisher_param.trim(),
        website_param: form.include_website && form.website_param.trim() ? form.website_param.trim() : null,
        include_website: form.include_website && !!form.website_param.trim(),
        extra_params: form.extra_params.filter(e => e.key.trim()),
        is_default: form.is_default,
        status: form.status,
      }
      if (modal === 'edit' && editId) {
        await adminApi.updateSmartlinkStructure(editId, payload)
        toast.success('Structure updated')
      } else {
        await adminApi.createSmartlinkStructure(payload)
        toast.success('Structure created')
      }
      setModal(null)
      load()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await adminApi.deleteSmartlinkStructure(deleteTarget.id)
      toast.success('Structure deleted')
      setDeleteTarget(null)
      load()
    } catch {
      toast.error('Delete failed')
    } finally {
      setDeleting(false)
    }
  }

  const handleGenerate = async () => {
    if (!genPublisher.trim()) { toast.error('Publisher ID is required'); return }
    setGenerating(true)
    try {
      const res = await adminApi.generateSmartlink({
        structure_id: genStructureId || undefined,
        domain: genDomain.trim() || undefined,
        publisher_id: genPublisher.trim(),
        site_id: genSite.trim() || undefined,
      })
      setGenResult(res.data?.smartlink || '')
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Generation failed')
    } finally {
      setGenerating(false)
    }
  }

  const copy = (text: string) => {
    navigator.clipboard.writeText(text)
    toast.success('Copied to clipboard')
  }

  return (
    <div className="flex min-h-screen bg-[#f8f9fb]">
      <Sidebar />
      <div className="flex-1 lg:ml-64 p-6 lg:p-8 min-w-0 overflow-x-hidden">

        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 pt-12 lg:pt-0">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Smartlink Structures</h1>
            <p className="text-gray-400 text-sm mt-0.5">
              Define the query-parameter schemes used to build Smartlinks — parameter names are fully manageable
            </p>
          </div>
          <button onClick={openCreate}
            className="bg-primary hover:bg-primary-dark text-white px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2 self-start">
            <Plus size={18} /> Add Structure
          </button>
        </div>

        {/* Structures grid */}
        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 mb-8">
            {[1, 2, 3].map(i => <div key={i} className="shimmer h-44 rounded-2xl" />)}
          </div>
        ) : structures.length === 0 ? (
          <div className="text-center py-16 text-gray-400 bg-white rounded-2xl border border-gray-100 mb-8">
            <Link2 size={48} className="mx-auto mb-4 opacity-30" />
            <p className="text-base mb-4">No smartlink structures yet</p>
            <button onClick={openCreate}
              className="bg-primary hover:bg-primary-dark text-white px-6 py-2.5 rounded-xl text-sm font-semibold inline-flex items-center gap-2">
              <Plus size={16} /> Create First Structure
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 mb-8">
            {structures.map(s => (
              <div key={s.id} className="bg-white rounded-2xl border border-gray-100 p-5 flex flex-col gap-3 hover:shadow-md transition-shadow">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="font-semibold text-gray-900 truncate">{s.name}</p>
                  </div>
                  <div className="flex items-center gap-1.5 flex-shrink-0">
                    {s.is_default && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                        <Star size={10} className="fill-amber-400 text-amber-400" /> Default
                      </span>
                    )}
                    <StatusBadge status={s.status} />
                  </div>
                </div>

                <div className="bg-gray-50 rounded-xl p-3">
                  <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wide mb-1">Result Pattern</p>
                  <p className="text-xs font-mono text-gray-800 break-all">{s.pattern}</p>
                </div>

                <div className="flex flex-wrap gap-1.5 text-[11px]">
                  <span className="px-2 py-0.5 rounded-lg bg-blue-50 text-blue-700 border border-blue-100 font-mono">
                    pub: {s.publisher_param}
                  </span>
                  {s.include_website && s.website_param ? (
                    <span className="px-2 py-0.5 rounded-lg bg-emerald-50 text-emerald-700 border border-emerald-100 font-mono">
                      site: {s.website_param}
                    </span>
                  ) : (
                    <span className="px-2 py-0.5 rounded-lg bg-gray-100 text-gray-500 border border-gray-200">
                      no site param
                    </span>
                  )}
                  {s.extra_params.length > 0 && (
                    <span className="px-2 py-0.5 rounded-lg bg-purple-50 text-purple-700 border border-purple-100">
                      +{s.extra_params.length} extra
                    </span>
                  )}
                </div>

                <div className="flex gap-1.5 pt-2 border-t border-gray-100">
                  <button onClick={() => openEdit(s)}
                    className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl text-xs font-medium text-primary hover:bg-primary/5 border border-primary/20 transition-colors">
                    <Edit size={13} /> Edit
                  </button>
                  <button onClick={() => setDeleteTarget(s)}
                    className="p-2 rounded-xl text-red-400 hover:bg-red-50 border border-red-200 transition-colors" title="Delete">
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Generator */}
        <div className="bg-white rounded-2xl border border-gray-100 p-6">
          <div className="flex items-center gap-2 mb-1">
            <Wand2 size={18} className="text-primary" />
            <h2 className="text-lg font-bold text-gray-900">Smartlink Generator</h2>
          </div>
          <p className="text-sm text-gray-400 mb-5">Pick a structure, supply identifiers, get the final link</p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Structure</label>
              <select value={genStructureId} onChange={e => setGenStructureId(e.target.value)} className={inp}>
                <option value="">Default structure</option>
                {structures.filter(s => s.status === 'active').map(s => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Domain <span className="text-gray-400 font-normal">(optional — default anchor)</span></label>
              <input value={genDomain} onChange={e => setGenDomain(e.target.value)}
                placeholder="https://trustedcloudmedia.com" className={inp} />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Publisher ID <span className="text-red-500">*</span></label>
              <input value={genPublisher} onChange={e => setGenPublisher(e.target.value)}
                placeholder="PUB_LUKLLIZW" className={inp} />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Site ID <span className="text-gray-400 font-normal">(if the structure includes it)</span></label>
              <input value={genSite} onChange={e => setGenSite(e.target.value)}
                placeholder="SITE_2PRBE5E1" className={inp} />
            </div>
          </div>

          <button onClick={handleGenerate} disabled={generating || !genPublisher.trim()}
            className="mt-4 bg-primary hover:bg-primary-dark text-white px-6 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2 disabled:bg-gray-300">
            {generating ? <Spinner size={16} /> : <><Wand2 size={16} /> Generate Smartlink</>}
          </button>

          {genResult && (
            <div className="mt-4 flex items-center gap-2 bg-gray-50 border border-gray-200 rounded-xl p-3">
              <Link2 size={14} className="text-gray-400 flex-shrink-0" />
              <code className="flex-1 text-sm font-mono text-gray-800 break-all">{genResult}</code>
              <button onClick={() => copy(genResult)}
                className="px-3 py-1.5 rounded-lg bg-primary text-white text-xs font-semibold flex items-center gap-1 hover:bg-primary-dark">
                <Copy size={12} /> Copy
              </button>
            </div>
          )}
        </div>

        {/* ── Create / Edit Modal ─────────────────────────────────────────── */}
        {modal && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-6 w-full max-w-lg shadow-2xl border border-gray-100 max-h-[92vh] overflow-y-auto">
              <h3 className="text-lg font-bold text-gray-900 mb-5">
                {modal === 'create' ? 'Create Smartlink Structure' : 'Edit Smartlink Structure'}
              </h3>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Structure Name <span className="text-red-500">*</span></label>
                  <input value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))}
                    placeholder="e.g. Tag + SID" className={inp} />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Publisher Parameter <span className="text-red-500">*</span></label>
                    <input value={form.publisher_param}
                      onChange={e => setForm(p => ({ ...p, publisher_param: e.target.value }))}
                      placeholder="pub / tag / …" className={inp} />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Website Parameter</label>
                    <input value={form.website_param}
                      onChange={e => setForm(p => ({ ...p, website_param: e.target.value }))}
                      placeholder="site / sid / … (empty = none)" className={inp} />
                  </div>
                </div>

                <label className="flex items-center gap-2.5 cursor-pointer select-none">
                  <input type="checkbox" checked={form.include_website}
                    onChange={e => setForm(p => ({ ...p, include_website: e.target.checked }))}
                    className="rounded border-gray-300 text-primary focus:ring-primary/30 w-4 h-4" />
                  <span className="text-sm text-gray-700">Include website parameter in generated links</span>
                </label>

                {/* Extra static params */}
                <div className="border border-gray-200 rounded-xl p-4">
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Extra Static Parameters</p>
                    <button
                      onClick={() => setForm(p => ({ ...p, extra_params: [...p.extra_params, { key: '', value: '' }] }))}
                      className="text-xs font-semibold text-primary hover:underline">+ Add</button>
                  </div>
                  {form.extra_params.length === 0 ? (
                    <p className="text-xs text-gray-400 italic">None — optional static params appended to every link</p>
                  ) : (
                    <div className="space-y-2">
                      {form.extra_params.map((ep, i) => (
                        <div key={i} className="flex gap-2 items-center">
                          <input value={ep.key} placeholder="key (e.g. utm_source)"
                            onChange={e => setForm(p => {
                              const arr = [...p.extra_params]
                              arr[i] = { ...arr[i], key: e.target.value }
                              return { ...p, extra_params: arr }
                            })} className={inp} />
                          <input value={ep.value} placeholder="value"
                            onChange={e => setForm(p => {
                              const arr = [...p.extra_params]
                              arr[i] = { ...arr[i], value: e.target.value }
                              return { ...p, extra_params: arr }
                            })} className={inp} />
                          <button onClick={() => setForm(p => ({ ...p, extra_params: p.extra_params.filter((_, j) => j !== i) }))}
                            className="p-2 text-gray-400 hover:text-red-500"><X size={14} /></button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
                    <select value={form.status} onChange={e => setForm(p => ({ ...p, status: e.target.value as typeof form.status }))} className={inp}>
                      <option value="active">Active</option>
                      <option value="paused">Paused</option>
                    </select>
                  </div>
                  <label className="flex items-end gap-2.5 cursor-pointer select-none pb-2.5">
                    <input type="checkbox" checked={form.is_default}
                      onChange={e => setForm(p => ({ ...p, is_default: e.target.checked }))}
                      className="rounded border-gray-300 text-primary focus:ring-primary/30 w-4 h-4" />
                    <span className="text-sm text-gray-700">Set as default structure</span>
                  </label>
                </div>

                {/* Live pattern preview */}
                <div className="bg-blue-50 border border-blue-100 rounded-xl p-3">
                  <p className="text-[10px] font-semibold text-blue-400 uppercase tracking-wide mb-1">Result</p>
                  <p className="text-xs font-mono text-blue-800 break-all">{preview}</p>
                </div>
              </div>

              <div className="flex gap-3 mt-6">
                <button onClick={handleSave} disabled={saving || !form.name.trim() || !form.publisher_param.trim()}
                  className="flex-1 bg-primary hover:bg-primary-dark text-white py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 disabled:bg-gray-300">
                  {saving ? <Spinner size={16} /> : (modal === 'create' ? 'Create Structure' : 'Save Changes')}
                </button>
                <button onClick={() => setModal(null)}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50">
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── Delete Confirmation ─────────────────────────────────────────── */}
        <ConfirmDialog
          open={deleteTarget !== null}
          title="Delete Smartlink Structure"
          message={<>Delete structure <strong className="text-gray-900">{deleteTarget?.name}</strong>? Links already generated are unaffected. This cannot be undone.</>}
          confirmLabel="Delete"
          loading={deleting}
          onConfirm={handleDelete}
          onCancel={() => setDeleteTarget(null)}
        />
      </div>
    </div>
  )
}