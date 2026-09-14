'use client'

import { useState, useEffect, useCallback } from 'react'
import { Plus, Globe, Trash2, Edit2, BarChart3 } from 'lucide-react'
import { toast } from 'sonner'
import PublisherSidebar from '@/components/shared/PublisherSidebar'
import ConfirmDialog from '@/components/ui/ConfirmDialog'
import { StatusBadge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/loading'
import { publisherApi } from '@/lib/api'
import { useAuth } from '@/lib/hooks/useAuth'
import type { Website } from '@/types'

export default function PublisherWebsitesPage() {
  const { initialize } = useAuth()
  const [websites, setWebsites] = useState<Website[]>([])
  const [loading, setLoading] = useState(true)
  const [addModal, setAddModal] = useState(false)
  const [addForm, setAddForm] = useState({ domain: '', name: '' })
  const [saving, setSaving] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<Website | null>(null)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => { initialize() }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await publisherApi.getWebsites()
      setWebsites(res.data.websites)
    } catch { toast.error('Failed to load websites') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const domainRegex = /^(?!-)[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$/
  const isDomainValid = domainRegex.test(addForm.domain.replace(/^(https?:\/\/)?(www\.)?/, '').replace(/\/.*$/, ''))

  const handleAdd = async () => {
    // Strip protocol and trailing slashes
    const cleanDomain = addForm.domain.replace(/^(https?:\/\/)?(www\.)?/, '').replace(/\/+$/, '')
    if (!domainRegex.test(cleanDomain)) {
      toast.error('Enter a valid domain (e.g. myblog.com)')
      return
    }
    setSaving(true)
    try {
      await publisherApi.addWebsite({ ...addForm, domain: cleanDomain })
      toast.success('Website added')
      setAddModal(false)
      setAddForm({ domain: '', name: '' })
      load()
    } catch { toast.error('Failed to add website') }
    finally { setSaving(false) }
  }

  const handleDelete = async (w: Website) => {
    setDeleting(true)
    try {
      await publisherApi.deleteWebsite(w.id)
      toast.success('Website removed')
      setDeleteTarget(null)
      load()
    } catch { toast.error('Failed to remove') }
    finally { setDeleting(false) }
  }

  const inputClass = "w-full px-4 py-2.5 border border-gray-200 rounded-xl text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary text-sm"

  return (
    <div className="flex min-h-screen bg-[#f8f9fb]">
      <PublisherSidebar />
      <div className="flex-1 lg:ml-64 p-6 lg:p-8">
        <div className="flex items-center justify-between mb-8 pt-12 lg:pt-0">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Websites</h1>
            <p className="text-gray-500 mt-1">Manage your websites and view per-site performance</p>
          </div>
          <button onClick={() => setAddModal(true)}
            className="bg-primary hover:bg-primary-dark text-white px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2">
            <Plus size={18} /> Add Website
          </button>
        </div>

        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map(i => <div key={i} className="shimmer h-24 rounded-2xl" />)}
          </div>
        ) : websites.length === 0 ? (
          <div className="text-center py-16 text-gray-400">
            <Globe size={48} className="mx-auto mb-4 opacity-30" />
            <p className="mb-4">No websites added yet</p>
            <button onClick={() => setAddModal(true)}
              className="bg-primary hover:bg-primary-dark text-white px-6 py-3 rounded-xl text-sm font-semibold inline-flex items-center gap-2">
              <Plus size={16} /> Add Your First Website
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            {websites.map((website) => (
              <div key={website.id} className="bg-white rounded-2xl border border-gray-100 p-5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center flex-shrink-0">
                      <Globe size={22} className="text-primary" />
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold text-gray-900 text-lg">{website.name}</h3>
                        <StatusBadge status={website.status} />
                      </div>
                      <p className="text-sm text-gray-500">{website.domain}</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-6">
                    <div className="hidden md:grid grid-cols-3 gap-6 text-right">
                      <div>
                        <p className="text-xs text-gray-500">Total Clicks</p>
                        <p className="text-sm font-mono font-semibold text-gray-900">{(website.total_clicks ?? 0).toLocaleString()}</p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-500">Valid Clicks</p>
                        <p className="text-sm font-mono font-semibold text-green-600">{(website.valid_clicks ?? 0).toLocaleString()}</p>
                      </div>
                      <div>
                        <p className="text-xs text-gray-500">Earnings</p>
                        <p className="text-sm font-mono font-semibold text-red-600">${(website.total_earnings ?? 0).toFixed(4)}</p>
                      </div>
                    </div>
                    <button onClick={() => setDeleteTarget(website)}
                      className="p-2 rounded text-red-400 hover:text-red-600 hover:bg-red-50 transition-colors">
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>

                {/* Mobile stats */}
                <div className="md:hidden grid grid-cols-3 gap-3 mt-4">
                  <div className="text-center p-2 rounded-xl bg-gray-50 border border-gray-100">
                    <p className="text-xs text-gray-500">Clicks</p>
                    <p className="text-sm font-mono font-semibold text-gray-900">{(website.total_clicks ?? 0).toLocaleString()}</p>
                  </div>
                  <div className="text-center p-2 rounded-xl bg-gray-50 border border-gray-100">
                    <p className="text-xs text-gray-500">Valid</p>
                    <p className="text-sm font-mono font-semibold text-green-600">{(website.valid_clicks ?? 0).toLocaleString()}</p>
                  </div>
                  <div className="text-center p-2 rounded-xl bg-gray-50 border border-gray-100">
                    <p className="text-xs text-gray-500">Earnings</p>
                    <p className="text-sm font-mono font-semibold text-red-600">${(website.total_earnings ?? 0).toFixed(4)}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Add Website Modal */}
        {addModal && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-2xl border border-gray-100">
              <h3 className="text-lg font-bold text-gray-900 mb-6">Add Website</h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Domain</label>
                  <input value={addForm.domain} onChange={e => setAddForm(p => ({ ...p, domain: e.target.value }))}
                    placeholder="myblog.com (without http://)" className={`${inputClass} ${addForm.domain && !isDomainValid ? 'border-red-400 focus:ring-red-200 focus:border-red-400' : ''}`} />
                  {addForm.domain && !isDomainValid && (
                    <p className="text-xs text-red-500 mt-1">Enter a valid domain like example.com or blog.example.co.uk</p>
                  )}
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Website Name</label>
                  <input value={addForm.name} onChange={e => setAddForm(p => ({ ...p, name: e.target.value }))}
                    placeholder="My Blog" className={inputClass} />
                </div>
              </div>
              <div className="flex gap-3 mt-6">
                <button onClick={handleAdd} disabled={saving || !addForm.domain || !isDomainValid}
                  className="flex-1 bg-primary hover:bg-primary-dark text-white py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center">
                  {saving ? <Spinner size={16} /> : 'Add Website'}
                </button>
                <button onClick={() => setAddModal(false)}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50">
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ── Remove Website Confirmation ──────────────────────────────────── */}
        <ConfirmDialog
          open={deleteTarget !== null}
          title="Remove Website"
          message={<>Remove <strong className="text-gray-900">{deleteTarget?.name || deleteTarget?.domain}</strong> and all its data? This cannot be undone.</>}
          confirmLabel="Remove Website"
          loading={deleting}
          onConfirm={() => { if (deleteTarget) handleDelete(deleteTarget) }}
          onCancel={() => setDeleteTarget(null)}
        />
      </div>
    </div>
  )
}
