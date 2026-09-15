'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  Plus, Edit, Trash2, LayoutTemplate, Eye, EyeOff, Archive,
  CheckCircle, MonitorSmartphone, Star, X,
} from 'lucide-react'
import { toast } from 'sonner'
import Sidebar from '@/components/shared/Sidebar'
import ConfirmDialog from '@/components/ui/ConfirmDialog'
import { StatusBadge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/loading'
import { prlanderTemplateApi } from '@/lib/api'
import { useAuth } from '@/lib/hooks/useAuth'

// ─── types ────────────────────────────────────────────────────────────────────

interface PrlanderTemplate {
  id: string
  name: string
  description?: string | null
  os_type: 'windows' | 'mac' | 'android' | 'both'
  status: 'active' | 'paused' | 'archived'
  is_default: boolean
  title: string
  subtitle: string
  button_text: string
  show_password_field: boolean
  show_video: boolean
  video_url?: string | null
  tags: string[]
  notes?: string | null
  // Full source code template
  full_html_template?: string | null
  usage_count: number
  created_at?: string | null
  updated_at?: string | null
  used_by?: { id: string; name: string; lander_url: string; status: string }[]
}

// Spec: the template form collects ONLY Template Name, Internal Notes and
// Status. Every other template field keeps its backend default (os_type "both",
// built-in page copy); on edit those fields are never sent, so existing HTML
// templates stay intact (the backend updates only what the client sends).
const EMPTY_FORM = {
  name: '',
  status: 'active' as 'active' | 'paused' | 'archived',
  notes: '',
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function PrlanderTemplatesPage() {
  const { initialize } = useAuth()
  const [templates, setTemplates] = useState<PrlanderTemplate[]>([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState('')
  const [modal, setModal] = useState<'create' | 'edit' | 'view' | null>(null)
  const [selected, setSelected] = useState<PrlanderTemplate | null>(null)
  const [form, setForm] = useState({ ...EMPTY_FORM })
  const [saving, setSaving] = useState(false)
  const [previewHtml, setPreviewHtml] = useState('')
  const [previewMeta, setPreviewMeta] = useState<{ campaign_url: string; password: string } | null>(null)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<PrlanderTemplate | null>(null)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => { initialize() }, [initialize])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await prlanderTemplateApi.getAll({
        status: statusFilter || undefined,
      })
      setTemplates(res.data?.templates ?? [])
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to load templates')
    } finally {
      setLoading(false)
    }
  }, [statusFilter])

  useEffect(() => { load() }, [load])

  // ── helpers ────────────────────────────────────────────────────────────────

  const openCreate = () => {
    setForm({ ...EMPTY_FORM })
    setSelected(null)
    setModal('create')
  }

  const openEdit = (t: PrlanderTemplate) => {
    setSelected(t)
    setForm({
      name: t.name,
      status: t.status,
      notes: t.notes || '',
    })
    setModal('edit')
  }

  const openView = async (t: PrlanderTemplate) => {
    try {
      const res = await prlanderTemplateApi.get(t.id)
      setSelected(res.data?.template ?? t)
      setModal('view')
    } catch {
      setSelected(t)
      setModal('view')
    }
  }

  const handleSave = async () => {
    if (!form.name.trim()) { toast.error('Name is required'); return }
    setSaving(true)
    try {
      // Only the three spec'd fields are sent. The backend fills defaults for
      // everything else on create, and exclude_unset keeps every other field
      // (including an existing full_html_template) untouched on update.
      const payload = {
        name: form.name.trim(),
        status: form.status,
        notes: form.notes.trim() || null,
      }
      let res: any
      if (modal === 'edit' && selected) {
        res = await prlanderTemplateApi.update(selected.id, payload)
        toast.success('Template updated')
      } else {
        res = await prlanderTemplateApi.create(payload)
        toast.success('Template created')
      }
      // Show shortcode warnings returned by backend
      const warnings: string[] = res?.data?.warnings || []
      if (warnings.length > 0) {
        warnings.forEach(w => toast.warning(w, { duration: 6000 }))
      }
      setModal(null)
      load()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const handleSetDefault = async (t: PrlanderTemplate) => {
    try {
      await prlanderTemplateApi.setDefault(t.id)
      toast.success(`"${t.name}" is now the default for OS: ${t.os_type}`)
      load()
    } catch {
      toast.error('Failed to set default')
    }
  }

  const handlePreview = async (t: PrlanderTemplate) => {
    try {
      const res = await prlanderTemplateApi.preview(t.id, { os: t.os_type === 'both' ? 'windows' : t.os_type })
      if (res.data?.html) {
        setPreviewHtml(res.data.html)
        setPreviewMeta({ campaign_url: res.data.campaign_url ?? '', password: res.data.password ?? '' })
        setPreviewOpen(true)
      } else {
        toast.error('No HTML content to preview')
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Preview failed')
    }
  }

  const handleSetStatus = async (t: PrlanderTemplate, status: string) => {
    try {
      await prlanderTemplateApi.setStatus(t.id, status)
      toast.success(`Template ${status}`)
      load()
    } catch {
      toast.error('Status update failed')
    }
  }

  const handleDelete = async (t: PrlanderTemplate) => {
    setDeleting(true)
    try {
      await prlanderTemplateApi.delete(t.id)
      toast.success('Template deleted')
      setDeleteTarget(null)
      load()
    } catch {
      toast.error('Delete failed')
    } finally {
      setDeleting(false)
    }
  }

  // ── render ─────────────────────────────────────────────────────────────────

  const inp = 'w-full px-4 py-2.5 border border-gray-200 rounded-xl text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary text-sm'

  return (
    <div className="flex min-h-screen bg-[#f8f9fb]">
      <Sidebar />
      <div className="flex-1 lg:ml-64 p-6 lg:p-8 min-w-0 overflow-x-hidden">

        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 pt-12 lg:pt-0">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Prelander Templates</h1>
            <p className="text-gray-400 text-sm mt-0.5">
              Design templates for the <code className="bg-gray-100 px-1 rounded">/d/&#123;slug&#125;</code> landing page — separate from Landing Pages and Domains
            </p>
          </div>
          <button onClick={openCreate}
            className="bg-primary hover:bg-primary-dark text-white px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2 self-start">
            <Plus size={18} /> Add Template
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
          <span className="text-sm text-gray-400 ml-auto">{templates.length} template{templates.length !== 1 ? 's' : ''}</span>
        </div>

        {/* Grid */}
        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {[1,2,3].map(i => <div key={i} className="shimmer h-48 rounded-2xl" />)}
          </div>
        ) : templates.length === 0 ? (
          <div className="text-center py-20 text-gray-400">
            <LayoutTemplate size={48} className="mx-auto mb-4 opacity-30" />
            <p className="text-base mb-4">No prelander templates yet</p>
            <button onClick={openCreate}
              className="bg-primary hover:bg-primary-dark text-white px-6 py-2.5 rounded-xl text-sm font-semibold inline-flex items-center gap-2">
              <Plus size={16} /> Create First Template
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {templates.map(t => (
              <div key={t.id} className="bg-white rounded-2xl border border-gray-100 p-5 flex flex-col gap-3 hover:shadow-md transition-shadow">
                {/* Top row */}
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-gray-900 truncate">{t.name}</p>
                    {t.notes && (
                      <p className="text-xs text-gray-400 mt-0.5 line-clamp-2">{t.notes}</p>
                    )}
                  </div>
                  <StatusBadge status={t.status} />
                </div>

                {/* Chips */}
                <div className="flex flex-wrap gap-1.5">
                  {t.is_default && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                      <Star size={10} className="fill-amber-400 text-amber-400" /> Default
                    </span>
                  )}
                  {t.full_html_template && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-blue-50 text-blue-700 border border-blue-200">
                      &lt;/&gt; HTML
                    </span>
                  )}
                </div>

                {/* Usage */}
                <div className="flex items-center justify-between text-xs text-gray-400">
                  <span className="flex items-center gap-1">
                    <CheckCircle size={12} className={t.usage_count > 0 ? 'text-emerald-500' : ''} />
                    Used by {t.usage_count} landing page{t.usage_count !== 1 ? 's' : ''}
                  </span>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-1.5 pt-1 border-t border-gray-100">
                  <button onClick={() => openView(t)}
                    className="flex items-center justify-center gap-1.5 py-2 px-3 rounded-xl text-xs font-medium text-gray-600 hover:bg-gray-50 border border-gray-200 transition-colors">
                    <Eye size={13} /> View
                  </button>
                  <button onClick={() => openEdit(t)}
                    className="flex items-center justify-center gap-1.5 py-2 px-3 rounded-xl text-xs font-medium text-primary hover:bg-primary/5 border border-primary/20 transition-colors">
                    <Edit size={13} /> Edit
                  </button>
                  {t.full_html_template && (
                    <button onClick={() => handlePreview(t)} title="Preview rendered HTML"
                      className="flex items-center justify-center gap-1 py-2 px-2 rounded-xl text-xs font-medium text-blue-600 hover:bg-blue-50 border border-blue-200 transition-colors">
                      <MonitorSmartphone size={13} />
                    </button>
                  )}
                  {!t.is_default && t.status === 'active' && (
                    <button onClick={() => handleSetDefault(t)} title="Set as default for this OS"
                      className="flex items-center justify-center gap-1 py-2 px-2 rounded-xl text-xs font-medium text-amber-600 hover:bg-amber-50 border border-amber-200 transition-colors">
                      <Star size={13} />
                    </button>
                  )}
                  {t.status === 'active' ? (
                    <button onClick={() => handleSetStatus(t, 'paused')} title="Pause"
                      className="p-2 rounded-xl text-amber-500 hover:bg-amber-50 border border-amber-200 transition-colors">
                      <EyeOff size={13} />
                    </button>
                  ) : t.status === 'paused' ? (
                    <button onClick={() => handleSetStatus(t, 'active')} title="Activate"
                      className="p-2 rounded-xl text-emerald-600 hover:bg-emerald-50 border border-emerald-200 transition-colors">
                      <Eye size={13} />
                    </button>
                  ) : null}
                  {t.status !== 'archived' && (
                    <button onClick={() => handleSetStatus(t, 'archived')} title="Archive"
                      className="p-2 rounded-xl text-gray-400 hover:bg-gray-50 border border-gray-200 transition-colors">
                      <Archive size={13} />
                    </button>
                  )}
                  <button onClick={() => setDeleteTarget(t)} title="Delete"
                    className="p-2 rounded-xl text-red-400 hover:bg-red-50 border border-red-200 transition-colors">
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* ── Create / Edit Modal ─────────────────────────────────────────── */}
        {(modal === 'create' || modal === 'edit') && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-6 w-full max-w-xl shadow-2xl border border-gray-100 max-h-[92vh] overflow-y-auto">
              <h3 className="text-lg font-bold text-gray-900 mb-5">
                {modal === 'create' ? 'Create Prelander Template' : `Edit — ${selected?.name}`}
              </h3>

              <div className="space-y-4">
                {/* Name */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Template Name <span className="text-red-500">*</span></label>
                  <input value={form.name} onChange={e => setForm(p => ({ ...p, name: e.target.value }))}
                    placeholder="e.g. Windows Download v2" className={inp} />
                </div>

                {/* Status */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
                  <select value={form.status} onChange={e => setForm(p => ({ ...p, status: e.target.value as typeof form.status }))} className={inp}>
                    <option value="active">Active</option>
                    <option value="paused">Paused</option>
                    <option value="archived">Archived</option>
                  </select>
                </div>

                {/* Notes */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Internal Notes</label>
                  <textarea value={form.notes} onChange={e => setForm(p => ({ ...p, notes: e.target.value }))}
                    rows={2} placeholder="Optional admin notes" className={inp} />
                </div>
              </div>

              <div className="flex gap-3 mt-6">
                <button onClick={handleSave} disabled={saving || !form.name.trim()}
                  className="flex-1 bg-primary hover:bg-primary-dark text-white py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 disabled:bg-gray-300">
                  {saving ? <Spinner size={16} /> : (modal === 'create' ? 'Create Template' : 'Save Changes')}
                </button>
                <button onClick={() => setModal(null)}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50">
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── View Details Modal ──────────────────────────────────────────── */}
        {modal === 'view' && selected && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-6 w-full max-w-lg shadow-2xl border border-gray-100 max-h-[90vh] overflow-y-auto">
              <div className="flex items-start justify-between gap-3 mb-5">
                <div>
                  <h3 className="text-lg font-bold text-gray-900">{selected.name}</h3>
                </div>
                <StatusBadge status={selected.status} />
              </div>

              <div className="space-y-4">
                {selected.notes && (
                  <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-sm text-amber-800">
                    <span className="font-semibold">Internal Notes: </span>{selected.notes}
                  </div>
                )}

                {/* Landing pages using this template */}
                {(selected.used_by?.length ?? 0) > 0 && (
                  <div>
                    <p className="text-sm font-semibold text-gray-700 mb-2">
                      Used by {selected.used_by!.length} landing page{selected.used_by!.length !== 1 ? 's' : ''}
                    </p>
                    <div className="space-y-1.5">
                      {selected.used_by!.map(lp => (
                        <div key={lp.id} className="flex items-center justify-between px-3 py-2 rounded-xl bg-gray-50 border border-gray-100 text-xs">
                          <span className="font-medium text-gray-800">{lp.name}</span>
                          <StatusBadge status={lp.status} />
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {(selected.used_by?.length ?? 0) === 0 && (
                  <p className="text-sm text-gray-400 italic">Not assigned to any landing page yet.</p>
                )}

                <p className="text-xs text-gray-400">
                  Created: {selected.created_at ? new Date(selected.created_at).toLocaleDateString() : '—'}
                  &nbsp;·&nbsp;
                  Updated: {selected.updated_at ? new Date(selected.updated_at).toLocaleDateString() : '—'}
                </p>
              </div>

              <div className="flex gap-3 mt-6">
                <button onClick={() => { setModal(null); openEdit(selected) }}
                  className="flex-1 bg-primary hover:bg-primary-dark text-white py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center gap-2">
                  <Edit size={15} /> Edit Template
                </button>
                <button onClick={() => setModal(null)}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50">
                  Close
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── Preview Modal ───────────────────────────────────────────────── */}
        {previewOpen && previewHtml && (
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl w-full max-w-4xl max-h-[92vh] flex flex-col shadow-2xl border border-gray-100">
              <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100 flex-shrink-0">
                <p className="text-sm font-semibold text-gray-900">Template Preview — rendered with Global Campaign values</p>
                <button onClick={() => { setPreviewOpen(false); setPreviewMeta(null) }}
                  className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500 transition-colors">
                  <X size={18} />
                </button>
              </div>
              <div className="px-5 py-2 border-b border-gray-100 bg-gray-50 text-xs text-gray-600 flex flex-wrap gap-x-5 gap-y-1 flex-shrink-0">
                <span className="min-w-0">
                  <span className="text-gray-400">Campaign URL: </span>
                  <span className="font-mono break-all">{previewMeta?.campaign_url || '—'}</span>
                </span>
                <span>
                  <span className="text-gray-400">Password: </span>
                  <span className="font-mono">{previewMeta?.password || '—'}</span>
                </span>
              </div>
              <div className="flex-1 overflow-hidden rounded-b-2xl">
                <iframe
                  srcDoc={previewHtml}
                  className="w-full h-full border-0 rounded-b-2xl"
                  style={{ minHeight: '70vh' }}
                  sandbox="allow-scripts allow-same-origin"
                  title="Template Preview"
                />
              </div>
            </div>
          </div>
        )}

        {/* ── Delete Template Confirmation ────────────────────────────────── */}
        <ConfirmDialog
          open={deleteTarget !== null}
          title="Delete Template"
          message={<>Delete template <strong className="text-gray-900">{deleteTarget?.name}</strong>? Landing pages using it will lose the reference. This cannot be undone.</>}
          confirmLabel="Delete Template"
          loading={deleting}
          onConfirm={() => { if (deleteTarget) handleDelete(deleteTarget) }}
          onCancel={() => setDeleteTarget(null)}
        />

      </div>
    </div>
  )
}
