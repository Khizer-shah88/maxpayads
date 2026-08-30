'use client'

import { useState, useEffect, useCallback } from 'react'
import { Search, Download, Trash2, Edit, DollarSign, Plus, Globe } from 'lucide-react'
import { toast } from 'sonner'
import Sidebar from '@/components/shared/Sidebar'
import DataTable from '@/components/tables/DataTable'
import { StatusBadge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/loading'
import { adminApi, downloadBlob } from '@/lib/api'
import { useAuth } from '@/lib/hooks/useAuth'
import type { Publisher } from '@/types'

const EMPTY_PUB_FORM = {
  name: '', email: '', password: '', website_domain: '',
  status: 'active', revenue_share: 0.80, custom_cpc: '',
}

const EMPTY_SITE_FORM = { domain: '', name: '' }

export default function PublishersPage() {
  const { initialize } = useAuth()
  const [publishers, setPublishers] = useState<Publisher[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState('')
  const [searchTerm, setSearchTerm] = useState('')

  // Existing modals
  const [editModal, setEditModal] = useState<Publisher | null>(null)
  const [deleteModal, setDeleteModal] = useState<Publisher | null>(null)
  const [balanceModal, setBalanceModal] = useState<Publisher | null>(null)
  const [editForm, setEditForm] = useState({ status: '', revenue_share: 0, custom_cpc: '' })
  const [balanceAmount, setBalanceAmount] = useState('')
  const [actionLoading, setActionLoading] = useState(false)

  // New: add publisher modal
  const [addModal, setAddModal] = useState(false)
  const [addForm, setAddForm] = useState({ ...EMPTY_PUB_FORM })
  const [addLoading, setAddLoading] = useState(false)

  // New: add website for publisher modal
  const [siteModal, setSiteModal] = useState<Publisher | null>(null)
  const [siteForm, setSiteForm] = useState({ ...EMPTY_SITE_FORM })
  const [siteLoading, setSiteLoading] = useState(false)

  useEffect(() => { initialize() }, [])

  const loadPublishers = useCallback(async () => {
    setLoading(true)
    try {
      const res = await adminApi.getPublishers({ status: statusFilter || undefined, page, limit: 20 })
      setPublishers(res.data?.publishers ?? [])
      setTotal(res.data?.total ?? 0)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to load publishers')
    } finally {
      setLoading(false)
    }
  }, [statusFilter, page])

  useEffect(() => { loadPublishers() }, [loadPublishers])

  // ── Add publisher ──────────────────────────────────────────────────────────
  const handleAddPublisher = async () => {
    if (!addForm.name.trim() || !addForm.email.trim() || !addForm.password.trim()) {
      toast.error('Name, email and password are required')
      return
    }
    if (addForm.password.length < 8) { toast.error('Password must be at least 8 characters'); return }
    setAddLoading(true)
    try {
      await adminApi.createPublisher({
        name: addForm.name.trim(),
        email: addForm.email.trim().toLowerCase(),
        password: addForm.password,
        website_domain: addForm.website_domain.trim() || undefined,
        status: addForm.status,
        revenue_share: parseFloat(addForm.revenue_share as any) || 0.80,
        custom_cpc: addForm.custom_cpc ? parseFloat(addForm.custom_cpc) : undefined,
      })
      toast.success('Publisher created')
      setAddModal(false)
      setAddForm({ ...EMPTY_PUB_FORM })
      loadPublishers()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to create publisher')
    } finally {
      setAddLoading(false)
    }
  }

  // ── Add website for publisher ──────────────────────────────────────────────
  const handleAddWebsite = async () => {
    if (!siteModal || !siteForm.domain.trim()) { toast.error('Domain is required'); return }
    setSiteLoading(true)
    try {
      await adminApi.addPublisherWebsite(siteModal.id, {
        domain: siteForm.domain.trim(),
        name: siteForm.name.trim() || siteForm.domain.trim(),
      })
      toast.success('Website added')
      setSiteModal(null)
      setSiteForm({ ...EMPTY_SITE_FORM })
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to add website')
    } finally {
      setSiteLoading(false)
    }
  }

  // ── Existing actions ───────────────────────────────────────────────────────
  const handleEditSave = async () => {
    if (!editModal) return
    setActionLoading(true)
    try {
      const data: any = {}
      if (editForm.status) data.status = editForm.status
      if (editForm.revenue_share) data.revenue_share = editForm.revenue_share
      if (editForm.custom_cpc) data.custom_cpc = parseFloat(editForm.custom_cpc)
      await adminApi.updatePublisher(editModal.id, data)
      toast.success('Publisher updated')
      setEditModal(null)
      loadPublishers()
    } catch { toast.error('Update failed') }
    finally { setActionLoading(false) }
  }

  const handleDelete = async () => {
    if (!deleteModal) return
    setActionLoading(true)
    try {
      await adminApi.deletePublisher(deleteModal.id)
      toast.success('Publisher deleted')
      setDeleteModal(null)
      loadPublishers()
    } catch { toast.error('Delete failed') }
    finally { setActionLoading(false) }
  }

  const handleDownloadCSV = async (publisher: Publisher) => {
    try {
      const res = await adminApi.downloadPublisherCSV(publisher.id)
      downloadBlob(res.data, `publisher_${publisher.id}.csv`)
      toast.success('CSV downloaded')
    } catch { toast.error('Download failed') }
  }

  const handleBalanceAdjust = async () => {
    if (!balanceModal) return
    setActionLoading(true)
    try {
      await adminApi.adjustBalance(balanceModal.id, parseFloat(balanceAmount))
      toast.success('Balance adjusted')
      setBalanceModal(null)
      setBalanceAmount('')
      loadPublishers()
    } catch { toast.error('Balance adjustment failed') }
    finally { setActionLoading(false) }
  }

  const filtered = searchTerm
    ? publishers.filter(p =>
        p.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        p.email.toLowerCase().includes(searchTerm.toLowerCase()))
    : publishers

  const inp = 'w-full px-4 py-2.5 border border-gray-200 rounded-xl text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary text-sm'

  const columns = [
    { key: 'name', label: 'Name', render: (p: Publisher) => <span className="font-medium text-gray-900">{p.name}</span> },
    { key: 'email', label: 'Email' },
    { key: 'status', label: 'Status', render: (p: Publisher) => <StatusBadge status={p.status} /> },
    { key: 'revenue_share', label: 'Rev Share', render: (p: Publisher) => <span className="font-mono">{((p.revenue_share ?? 0) * 100).toFixed(0)}%</span> },
    { key: 'balance', label: 'Balance', render: (p: Publisher) => <span className="text-red-600 font-mono font-semibold">${(p.balance ?? 0).toFixed(2)}</span> },
    { key: 'total_clicks', label: 'Clicks', render: (p: Publisher) => (p.total_clicks ?? 0).toLocaleString() },
    { key: 'created_at', label: 'Joined', render: (p: Publisher) => new Date(p.created_at).toLocaleDateString() },
    { key: 'actions', label: 'Actions', render: (p: Publisher) => (
      <div className="flex items-center gap-1">
        <button onClick={() => { setEditModal(p); setEditForm({ status: p.status, revenue_share: p.revenue_share, custom_cpc: p.custom_cpc?.toString() || '' }) }}
          className="p-1.5 rounded text-gray-500 hover:text-gray-900 hover:bg-gray-100" title="Edit"><Edit size={15} /></button>
        <button onClick={() => { setSiteModal(p); setSiteForm({ ...EMPTY_SITE_FORM }) }}
          className="p-1.5 rounded text-gray-500 hover:text-blue-600 hover:bg-blue-50" title="Add Website"><Globe size={15} /></button>
        <button onClick={() => setBalanceModal(p)}
          className="p-1.5 rounded text-gray-500 hover:text-gray-900 hover:bg-gray-100" title="Adjust Balance"><DollarSign size={15} /></button>
        <button onClick={() => handleDownloadCSV(p)}
          className="p-1.5 rounded text-gray-500 hover:text-gray-900 hover:bg-gray-100" title="Download CSV"><Download size={15} /></button>
        <button onClick={() => setDeleteModal(p)}
          className="p-1.5 rounded text-red-400 hover:text-red-600 hover:bg-red-50" title="Delete"><Trash2 size={15} /></button>
      </div>
    )},
  ]

  return (
    <div className="flex min-h-screen bg-[#f8f9fb]">
      <Sidebar />
      <div className="flex-1 lg:ml-64 p-6 lg:p-8">
        <div className="flex items-center justify-between mb-8 pt-12 lg:pt-0">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Publishers</h1>
            <p className="text-gray-400 text-sm mt-0.5">Manage publisher accounts</p>
          </div>
          <button onClick={() => { setAddModal(true); setAddForm({ ...EMPTY_PUB_FORM }) }}
            className="bg-primary hover:bg-primary-dark text-white px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2">
            <Plus size={18} /> Add Publisher
          </button>
        </div>

        {/* Filters */}
        <div className="bg-white rounded-2xl border border-gray-100 p-4 mb-6 flex flex-wrap gap-4 items-center">
          <div className="relative flex-1 min-w-48">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={16} />
            <input value={searchTerm} onChange={e => setSearchTerm(e.target.value)}
              placeholder="Search by name or email..." className={`${inp} pl-9`} />
          </div>
          <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className={inp} style={{ width: 'auto' }}>
            <option value="">All Status</option>
            <option value="active">Active</option>
            <option value="pending">Pending</option>
            <option value="suspended">Suspended</option>
          </select>
          <span className="text-gray-500 text-sm">{total} publishers</span>
        </div>

        <div className="bg-white rounded-2xl border border-gray-100 p-6">
          <DataTable columns={columns} data={filtered} loading={loading}
            pagination={{ page, total, limit: 20, onPageChange: setPage }}
            emptyMessage="No publishers found" />
        </div>

        {/* ── Add Publisher Modal ─────────────────────────────────────────── */}
        {addModal && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-2xl border border-gray-100 max-h-[92vh] overflow-y-auto">
              <h3 className="text-lg font-bold text-gray-900 mb-5">Add Publisher</h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-900 mb-1">Full Name <span className="text-red-500">*</span></label>
                  <input value={addForm.name} onChange={e => setAddForm(p => ({ ...p, name: e.target.value }))}
                    placeholder="John Doe" className={inp} />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-900 mb-1">Email <span className="text-red-500">*</span></label>
                  <input type="email" value={addForm.email} onChange={e => setAddForm(p => ({ ...p, email: e.target.value }))}
                    placeholder="publisher@example.com" className={inp} />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-900 mb-1">Password <span className="text-red-500">*</span> <span className="text-gray-400 font-normal">(min 8 chars)</span></label>
                  <input type="password" value={addForm.password} onChange={e => setAddForm(p => ({ ...p, password: e.target.value }))}
                    placeholder="Min 8 characters" className={inp} />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-900 mb-1">Website Domain <span className="text-gray-400 font-normal">(optional)</span></label>
                  <input value={addForm.website_domain} onChange={e => setAddForm(p => ({ ...p, website_domain: e.target.value }))}
                    placeholder="myblog.com" className={inp} />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-900 mb-1">Status</label>
                    <select value={addForm.status} onChange={e => setAddForm(p => ({ ...p, status: e.target.value }))} className={inp}>
                      <option value="active">Active</option>
                      <option value="pending">Pending</option>
                      <option value="suspended">Suspended</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-900 mb-1">Revenue Share</label>
                    <input type="number" step="0.01" min="0" max="1" value={addForm.revenue_share}
                      onChange={e => setAddForm(p => ({ ...p, revenue_share: parseFloat(e.target.value) }))} className={inp} />
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-900 mb-1">Custom CPC <span className="text-gray-400 font-normal">(optional)</span></label>
                  <input type="number" step="0.001" min="0" value={addForm.custom_cpc}
                    onChange={e => setAddForm(p => ({ ...p, custom_cpc: e.target.value }))}
                    placeholder="Leave blank for default" className={inp} />
                </div>
              </div>
              <div className="flex gap-3 mt-6">
                <button onClick={handleAddPublisher} disabled={addLoading}
                  className="flex-1 bg-primary hover:bg-primary-dark text-white py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center disabled:bg-gray-300">
                  {addLoading ? <Spinner size={16} /> : 'Create Publisher'}
                </button>
                <button onClick={() => setAddModal(false)}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50">Cancel</button>
              </div>
            </div>
          </div>
        )}

        {/* ── Add Website Modal ───────────────────────────────────────────── */}
        {siteModal && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-6 w-full max-w-sm shadow-2xl border border-gray-100">
              <h3 className="text-lg font-bold text-gray-900 mb-1">Add Website</h3>
              <p className="text-sm text-gray-400 mb-4">Publisher: <strong className="text-gray-700">{siteModal.name}</strong></p>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-900 mb-1">Domain <span className="text-red-500">*</span></label>
                  <input value={siteForm.domain} onChange={e => setSiteForm(p => ({ ...p, domain: e.target.value }))}
                    placeholder="myblog.com" className={inp} />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-900 mb-1">Site Name <span className="text-gray-400 font-normal">(optional)</span></label>
                  <input value={siteForm.name} onChange={e => setSiteForm(p => ({ ...p, name: e.target.value }))}
                    placeholder="My Blog" className={inp} />
                </div>
              </div>
              <div className="flex gap-3 mt-6">
                <button onClick={handleAddWebsite} disabled={siteLoading || !siteForm.domain.trim()}
                  className="flex-1 bg-primary hover:bg-primary-dark text-white py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center disabled:bg-gray-300">
                  {siteLoading ? <Spinner size={16} /> : 'Add Website'}
                </button>
                <button onClick={() => setSiteModal(null)}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50">Cancel</button>
              </div>
            </div>
          </div>
        )}

        {/* ── Edit Modal ──────────────────────────────────────────────────── */}
        {editModal && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-2xl border border-gray-100">
              <h3 className="text-lg font-bold mb-4 text-gray-900">Edit Publisher: {editModal.name}</h3>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-900 mb-1">Status</label>
                  <select value={editForm.status} onChange={e => setEditForm(p => ({ ...p, status: e.target.value }))} className={inp}>
                    <option value="active">Active</option>
                    <option value="pending">Pending</option>
                    <option value="suspended">Suspended</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-900 mb-1">Revenue Share (0–1)</label>
                  <input type="number" step="0.01" min="0" max="1" value={editForm.revenue_share}
                    onChange={e => setEditForm(p => ({ ...p, revenue_share: parseFloat(e.target.value) }))} className={inp} />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-900 mb-1">Custom CPC <span className="text-gray-400 font-normal">(optional)</span></label>
                  <input type="number" step="0.001" min="0" value={editForm.custom_cpc}
                    onChange={e => setEditForm(p => ({ ...p, custom_cpc: e.target.value }))}
                    placeholder="Leave empty for default" className={inp} />
                </div>
              </div>
              <div className="flex gap-3 mt-6">
                <button onClick={handleEditSave} disabled={actionLoading}
                  className="flex-1 bg-primary hover:bg-primary-dark text-white py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center disabled:bg-gray-300">
                  {actionLoading ? <Spinner size={16} /> : 'Save Changes'}
                </button>
                <button onClick={() => setEditModal(null)}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50">Cancel</button>
              </div>
            </div>
          </div>
        )}

        {/* ── Delete Modal ────────────────────────────────────────────────── */}
        {deleteModal && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-6 w-full max-w-sm text-center shadow-2xl border border-gray-100">
              <div className="w-12 h-12 rounded-xl flex items-center justify-center mx-auto mb-4 bg-red-50">
                <Trash2 className="text-red-600" size={24} />
              </div>
              <h3 className="text-lg font-bold text-gray-900 mb-2">Delete Publisher</h3>
              <p className="text-gray-500 text-sm mb-6">Delete <strong className="text-gray-900">{deleteModal.name}</strong>? All clicks, withdrawals, and records will be removed.</p>
              <div className="flex gap-3">
                <button onClick={handleDelete} disabled={actionLoading}
                  className="flex-1 bg-red-600 hover:bg-red-700 text-white py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center">
                  {actionLoading ? <Spinner size={16} /> : 'Yes, Delete'}
                </button>
                <button onClick={() => setDeleteModal(null)}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50">Cancel</button>
              </div>
            </div>
          </div>
        )}

        {/* ── Balance Modal ───────────────────────────────────────────────── */}
        {balanceModal && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-6 w-full max-w-sm shadow-2xl border border-gray-100">
              <h3 className="text-lg font-bold text-gray-900 mb-2">Adjust Balance</h3>
              <p className="text-gray-500 text-sm mb-4">{balanceModal.name} — Current: <span className="text-red-600 font-mono font-semibold">${(balanceModal.balance ?? 0).toFixed(2)}</span></p>
              <input type="number" step="0.01" value={balanceAmount} onChange={e => setBalanceAmount(e.target.value)}
                placeholder="Amount (negative to deduct)" className={`${inp} mb-4`} />
              <div className="flex gap-3">
                <button onClick={handleBalanceAdjust} disabled={actionLoading || !balanceAmount}
                  className="flex-1 bg-primary hover:bg-primary-dark text-white py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center disabled:bg-gray-300">
                  {actionLoading ? <Spinner size={16} /> : 'Adjust'}
                </button>
                <button onClick={() => setBalanceModal(null)}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50">Cancel</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
