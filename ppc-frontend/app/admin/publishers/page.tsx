'use client'

import { useState, useEffect, useCallback } from 'react'
import { Search, Download, Trash2, Edit, DollarSign, Plus, Globe, Link2, Copy, UserPlus } from 'lucide-react'
import { toast } from 'sonner'
import Sidebar from '@/components/shared/Sidebar'
import DataTable from '@/components/tables/DataTable'
import { StatusBadge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/loading'
import { adminApi, downloadBlob } from '@/lib/api'
import { useAuth } from '@/lib/hooks/useAuth'
import type { Publisher } from '@/types'

const EMPTY_PUB_FORM = {
  name: '',
  status: 'active', revenue_share: 1.0, custom_cpc: '0.0',
}

const EMPTY_MANUAL_FORM = {
  name: '', revenue_share: 1.0, custom_cpc: '0.0',
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
  const [editForm, setEditForm] = useState({ status: '', revenue_share: 1.0, custom_cpc: '0.0' })
  const [balanceAmount, setBalanceAmount] = useState('')
  const [actionLoading, setActionLoading] = useState(false)

  // New: add publisher modal (name only)
  const [addModal, setAddModal] = useState(false)
  const [addForm, setAddForm] = useState({ ...EMPTY_PUB_FORM })
  const [addLoading, setAddLoading] = useState(false)

  // Manual publisher modal (name/tag only — no login, no website)
  const [manualModal, setManualModal] = useState(false)
  const [manualForm, setManualForm] = useState({ ...EMPTY_MANUAL_FORM })
  const [manualLoading, setManualLoading] = useState(false)

  // Smartlink modal (Admin → Publishers → Smartlink/Generate Link)
  const [smartlinkModal, setSmartlinkModal] = useState<{ publisher: Publisher; data: any } | null>(null)
  const [smartlinkLoading, setSmartlinkLoading] = useState(false)

  // Permanent deletion confirmation input (spec: requires admin confirmation)
  const [deleteConfirmText, setDeleteConfirmText] = useState('')

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

  // ── Add publisher (Name-only creation) ──────────────────────────────────────
  const handleAddPublisher = async () => {
    if (!addForm.name.trim()) {
      toast.error('Publisher name is required')
      return
    }
    setAddLoading(true)
    try {
      await adminApi.createPublisher({
        name: addForm.name.trim(),
        status: addForm.status,
        revenue_share: parseFloat(addForm.revenue_share as any) || 1.0,
        custom_cpc: addForm.custom_cpc !== '' ? parseFloat(addForm.custom_cpc) : 0.0,
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

  // ── Manual publisher (name/tag only) ───────────────────────────────────────
  const handleAddManualPublisher = async () => {
    if (!manualForm.name.trim()) { toast.error('A unique Name/Tag is required'); return }
    setManualLoading(true)
    try {
      await adminApi.createManualPublisher({
        name: manualForm.name.trim(),
        revenue_share: parseFloat(manualForm.revenue_share as any) || 1.0,
        custom_cpc: manualForm.custom_cpc !== '' ? parseFloat(manualForm.custom_cpc) : 0.0,
      })
      toast.success('Manual publisher created')
      setManualModal(false)
      setManualForm({ ...EMPTY_MANUAL_FORM })
      loadPublishers()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to create manual publisher')
    } finally {
      setManualLoading(false)
    }
  }

  // ── Smartlink generation ────────────────────────────────────────────────────
  const handleOpenSmartlink = async (publisher: Publisher) => {
    setSmartlinkLoading(true)
    try {
      const res = await adminApi.getPublisherSmartlink(publisher.id)
      setSmartlinkModal({ publisher, data: res.data })
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to generate Smartlink')
    } finally {
      setSmartlinkLoading(false)
    }
  }

  const copyText = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text)
      toast.success('Copied to clipboard')
    } catch {
      toast.error('Copy failed — select and copy manually')
    }
  }

  // ── Existing actions ───────────────────────────────────────────────────────
  const handleEditSave = async () => {
    if (!editModal) return
    setActionLoading(true)
    try {
      const data: any = {}
      if (editForm.status) data.status = editForm.status
      if (editForm.revenue_share !== undefined) data.revenue_share = editForm.revenue_share
      if (editForm.custom_cpc !== undefined && editForm.custom_cpc !== '') {
        data.custom_cpc = parseFloat(editForm.custom_cpc)
      } else {
        data.custom_cpc = 0.0
      }
      await adminApi.updatePublisher(editModal.id, data)
      toast.success('Publisher updated')
      setEditModal(null)
      loadPublishers()
    } catch { toast.error('Update failed') }
    finally { setActionLoading(false) }
  }

  const handleDelete = async () => {
    if (!deleteModal) return
    if (deleteConfirmText.trim().toUpperCase() !== 'DELETE') {
      toast.error('Type DELETE to confirm permanent removal')
      return
    }
    setActionLoading(true)
    try {
      await adminApi.deletePublisher(deleteModal.id)
      toast.success('Publisher permanently deleted')
      setDeleteModal(null)
      setDeleteConfirmText('')
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
        p.email?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (p.public_id && p.public_id.toLowerCase().includes(searchTerm.toLowerCase())))
    : publishers

  const inp = 'w-full px-4 py-2.5 border border-gray-200 rounded-xl text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary text-sm'

  const columns = [
    {
      key: 'name',
      label: 'Name',
      render: (p: Publisher) => (
        <div>
          <span className="font-medium text-gray-900">{p.name}</span>
          {p.public_id && <span className="block text-xs font-mono text-gray-400">{p.public_id}</span>}
        </div>
      )
    },
    {
      key: 'publisher_type',
      label: 'Type',
      render: (p: Publisher) => (
        p.publisher_type === 'manual' ? (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 border border-amber-200">
            Manual
          </span>
        ) : (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200">
            Registered
          </span>
        )
      )
    },
    {
      key: 'email',
      label: 'Email',
      render: (p: Publisher) => (
        p.publisher_type === 'manual' || p.email?.includes('@manual.invalid') ? (
          <span className="text-gray-400 font-mono">(-)</span>
        ) : (
          <span className="text-gray-600">{p.email || '(-)'}</span>
        )
      )
    },
    {
      key: 'status',
      label: 'Status',
      render: (p: Publisher) => <StatusBadge status={p.status} />
    },
    {
      key: 'custom_cpc',
      label: 'CPL',
      render: (p: Publisher) => (
        <span className="font-mono text-gray-700">
          ${(p.custom_cpc != null && p.custom_cpc !== undefined ? Number(p.custom_cpc) : 0.0).toFixed(2)}
        </span>
      )
    },
    {
      key: 'revenue_share',
      label: 'Rev Share',
      render: (p: Publisher) => (
        <span className="font-mono">{((p.revenue_share ?? 1.0) * 100).toFixed(0)}%</span>
      )
    },
    {
      key: 'balance',
      label: 'Balance',
      render: (p: Publisher) => (
        <span className="text-red-600 font-mono font-semibold">${(p.balance ?? 0).toFixed(2)}</span>
      )
    },
    {
      key: 'total_clicks',
      label: 'Clicks',
      render: (p: Publisher) => (p.total_clicks ?? 0).toLocaleString()
    },
    {
      key: 'created_at',
      label: 'Joined',
      render: (p: Publisher) => new Date(p.created_at).toLocaleDateString()
    },
    {
      key: 'actions',
      label: 'Actions',
      render: (p: Publisher) => (
        <div className="flex items-center gap-1">
          <button
            onClick={() => {
              setEditModal(p)
              setEditForm({
                status: p.status,
                revenue_share: p.revenue_share ?? 1.0,
                custom_cpc: p.custom_cpc != null ? p.custom_cpc.toString() : '0.0'
              })
            }}
            className="p-1.5 rounded text-gray-500 hover:text-gray-900 hover:bg-gray-100"
            title="Edit"
          >
            <Edit size={15} />
          </button>
          <button
            onClick={() => handleOpenSmartlink(p)}
            className="p-1.5 rounded text-gray-500 hover:text-blue-600 hover:bg-blue-50"
            title={p.publisher_type === 'manual' ? 'Smartlink & Ad Code' : 'Smartlink / Generate Link'}
          >
            <Link2 size={15} />
          </button>
          {p.publisher_type !== 'manual' && (
            <button
              onClick={() => { setSiteModal(p); setSiteForm({ ...EMPTY_SITE_FORM }) }}
              className="p-1.5 rounded text-gray-500 hover:text-blue-600 hover:bg-blue-50"
              title="Add Website"
            >
              <Globe size={15} />
            </button>
          )}
          <button
            onClick={() => setBalanceModal(p)}
            className="p-1.5 rounded text-gray-500 hover:text-gray-900 hover:bg-gray-100"
            title="Adjust Balance"
          >
            <DollarSign size={15} />
          </button>
          <button
            onClick={() => handleDownloadCSV(p)}
            className="p-1.5 rounded text-gray-500 hover:text-gray-900 hover:bg-gray-100"
            title="Download CSV"
          >
            <Download size={15} />
          </button>
          <button
            onClick={() => { setDeleteModal(p); setDeleteConfirmText('') }}
            className="p-1.5 rounded text-red-400 hover:text-red-600 hover:bg-red-50"
            title="Delete"
          >
            <Trash2 size={15} />
          </button>
        </div>
      )
    },
  ]

  return (
    <div className="flex min-h-screen bg-[#f8f9fb]">
      <Sidebar />
      <div className="flex-1 lg:ml-64 p-6 lg:p-8 min-w-0">
        <div className="flex items-center justify-between mb-8 pt-12 lg:pt-0">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Publishers</h1>
            <p className="text-gray-400 text-sm mt-0.5">Manage publisher accounts</p>
          </div>
          <div className="flex gap-2">
            <button onClick={() => { setManualModal(true); setManualForm({ ...EMPTY_MANUAL_FORM }) }}
              className="border border-gray-200 bg-white hover:bg-gray-50 text-gray-700 px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2">
              <UserPlus size={18} /> Manual Publisher
            </button>
            <button onClick={() => { setAddModal(true); setAddForm({ ...EMPTY_PUB_FORM }) }}
              className="bg-primary hover:bg-primary-dark text-white px-5 py-2.5 rounded-xl text-sm font-semibold flex items-center gap-2">
              <Plus size={18} /> Add Publisher
            </button>
          </div>
        </div>

        {/* Filters */}
        <div className="bg-white rounded-2xl border border-gray-100 p-4 mb-6 flex flex-wrap gap-4 items-center">
          <div className="relative flex-1 min-w-48">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={16} />
            <input value={searchTerm} onChange={e => setSearchTerm(e.target.value)}
              placeholder="Search by name, email, or PUB ID..." className={`${inp} pl-9`} />
          </div>
          <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className={inp} style={{ width: 'auto' }}>
            <option value="">All Status</option>
            <option value="active">Active</option>
            <option value="pending">Pending</option>
            <option value="suspended">Suspended</option>
            <option value="banned">Banned</option>
            <option value="removed">Removed</option>
          </select>
          <span className="text-gray-500 text-sm">{total} publishers</span>
        </div>

        <div className="bg-white rounded-2xl border border-gray-100 p-6 overflow-x-auto">
          <DataTable columns={columns} data={filtered} loading={loading}
            pagination={{ page, total, limit: 20, onPageChange: setPage }}
            emptyMessage="No publishers found" />
        </div>

        {/* ── Add Publisher Modal (Name-only) ─────────────────────────────── */}
        {addModal && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-2xl border border-gray-100 max-h-[92vh] overflow-y-auto">
              <h3 className="text-lg font-bold text-gray-900 mb-2">Add Publisher</h3>
              <p className="text-xs text-gray-500 mb-5">
                Add publisher by name only. Account credentials and public ID will be generated automatically.
              </p>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-900 mb-1">Publisher Name <span className="text-red-500">*</span></label>
                  <input value={addForm.name} onChange={e => setAddForm(p => ({ ...p, name: e.target.value }))}
                    placeholder="e.g. John Doe or Media Network" className={inp} />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-900 mb-1">Status</label>
                    <select value={addForm.status} onChange={e => setAddForm(p => ({ ...p, status: e.target.value }))} className={inp}>
                      <option value="active">Active</option>
                      <option value="pending">Pending</option>
                      <option value="suspended">Suspended</option>
                      <option value="banned">Banned</option>
                      <option value="removed">Removed</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-900 mb-1">Revenue Share</label>
                    <input type="number" step="0.01" min="0" max="1" value={addForm.revenue_share}
                      onChange={e => setAddForm(p => ({ ...p, revenue_share: parseFloat(e.target.value) }))} className={inp} />
                    <span className="text-[11px] text-gray-400 mt-0.5 block">Default 1.0 (100%)</span>
                  </div>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-900 mb-1">Custom CPL (CPC)</label>
                  <input type="number" step="0.001" min="0" value={addForm.custom_cpc}
                    onChange={e => setAddForm(p => ({ ...p, custom_cpc: e.target.value }))}
                    placeholder="0.0" className={inp} />
                  <span className="text-[11px] text-gray-400 mt-0.5 block">Default 0.0</span>
                </div>
              </div>
              <div className="flex gap-3 mt-6">
                <button onClick={handleAddPublisher} disabled={addLoading || !addForm.name.trim()}
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
                    <option value="banned">Banned (links keep redirecting, stats preserved, Direct Link Stats off)</option>
                    <option value="removed">Removed (links keep redirecting, stats preserved, Direct Link Stats off)</option>
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

        {/* ── Delete Modal (permanent deletion — requires confirmation) ─────── */}
        {deleteModal && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-6 w-full max-w-sm text-center shadow-2xl border border-gray-100">
              <div className="w-12 h-12 rounded-xl flex items-center justify-center mx-auto mb-4 bg-red-50">
                <Trash2 className="text-red-600" size={24} />
              </div>
              <h3 className="text-lg font-bold text-gray-900 mb-2">Permanently Delete Publisher</h3>
              <p className="text-gray-500 text-sm mb-4">
                Permanently delete <strong className="text-gray-900">{deleteModal.name}</strong>?
                The publisher and all related records (clicks, withdrawals, fraud logs, websites) will be deleted.
                This cannot be undone.
              </p>
              <p className="text-gray-400 text-xs mb-4">
                To ban instead, set status to <strong>Banned</strong> in Edit — links keep redirecting and statistics are preserved.
              </p>
              <input value={deleteConfirmText} onChange={e => setDeleteConfirmText(e.target.value)}
                placeholder="Type DELETE to confirm" className={inp} />
              <div className="flex gap-3 mt-4">
                <button onClick={handleDelete} disabled={actionLoading || deleteConfirmText.trim().toUpperCase() !== 'DELETE'}
                  className="flex-1 bg-red-600 hover:bg-red-700 text-white py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center disabled:bg-gray-300">
                  {actionLoading ? <Spinner size={16} /> : 'Delete Permanently'}
                </button>
                <button onClick={() => { setDeleteModal(null); setDeleteConfirmText('') }}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50">Cancel</button>
              </div>
            </div>
          </div>
        )}

        {/* ── Manual Publisher Modal (name/tag only) ──────────────────────── */}
        {manualModal && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-2xl border border-gray-100 max-h-[92vh] overflow-y-auto">
              <h3 className="text-lg font-bold text-gray-900 mb-1">Add Manual Publisher</h3>
              <p className="text-sm text-gray-400 mb-5">
                Name/Tag only — no login, no website. The Publisher ID is auto-generated;
                the Smartlink is <span className="font-mono">?pub=PUB_ID</span> with no site param, ever.
              </p>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-900 mb-1">Unique Name/Tag <span className="text-red-500">*</span></label>
                  <input value={manualForm.name} onChange={e => setManualForm(p => ({ ...p, name: e.target.value }))}
                    placeholder="e.g. push-network-a" className={inp} />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-900 mb-1">Revenue Share</label>
                    <input type="number" step="0.01" min="0" max="1" value={manualForm.revenue_share}
                      onChange={e => setManualForm(p => ({ ...p, revenue_share: parseFloat(e.target.value) }))} className={inp} />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-900 mb-1">Custom CPC</label>
                    <input type="number" step="0.001" min="0" value={manualForm.custom_cpc}
                      onChange={e => setManualForm(p => ({ ...p, custom_cpc: e.target.value }))}
                      placeholder="Default" className={inp} />
                  </div>
                </div>
              </div>
              <div className="flex gap-3 mt-6">
                <button onClick={handleAddManualPublisher} disabled={manualLoading}
                  className="flex-1 bg-primary hover:bg-primary-dark text-white py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center disabled:bg-gray-300">
                  {manualLoading ? <Spinner size={16} /> : 'Create Manual Publisher'}
                </button>
                <button onClick={() => setManualModal(false)}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50">Cancel</button>
              </div>
            </div>
          </div>
        )}

        {/* ── Smartlink Modal ─────────────────────────────────────────────── */}
        {smartlinkLoading && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-8 shadow-2xl border border-gray-100 flex items-center gap-3">
              <Spinner size={20} /> <span className="text-gray-600 text-sm">Generating Smartlink…</span>
            </div>
          </div>
        )}
        {smartlinkModal && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-6 w-full max-w-lg shadow-2xl border border-gray-100 max-h-[92vh] overflow-y-auto">
              <h3 className="text-lg font-bold text-gray-900 mb-1">
                {smartlinkModal.data?.publisher_type === 'manual' ? 'Smartlink & Ad Code' : 'Smartlink'} — {smartlinkModal.publisher.name}
              </h3>
              <p className="text-sm text-gray-400 mb-4">
                Publisher ID: <span className="font-mono font-bold text-gray-700">{smartlinkModal.data?.public_id}</span>
                {' · '}Type:{' '}
                {smartlinkModal.data?.publisher_type === 'manual' ? (
                  <span className="text-amber-700 font-semibold">Manual (?pub={smartlinkModal.data?.public_id})</span>
                ) : (
                  <span className="text-blue-700 font-semibold">Registered (?pub={smartlinkModal.data?.public_id}&site=SITE_ID)</span>
                )}
              </p>
              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-semibold text-gray-500 uppercase mb-1">
                    {smartlinkModal.data?.publisher_type === 'manual' ? 'Smartlink URL' : (smartlinkModal.data?.website_smartlinks?.length ? 'Publisher-level fallback link' : 'Smartlink')}
                  </label>
                  <div className="flex gap-2">
                    <input readOnly value={smartlinkModal.data?.smartlink || ''} className={`${inp} font-mono text-xs`} />
                    <button onClick={() => copyText(smartlinkModal.data?.smartlink || '')}
                      className="px-3 rounded-xl border border-gray-200 hover:bg-gray-50 text-gray-600 flex items-center" title="Copy"><Copy size={16} /></button>
                  </div>
                </div>

                {smartlinkModal.data?.publisher_type === 'manual' && (
                  <div>
                    <label className="block text-xs font-semibold text-gray-500 uppercase mb-1">
                      Ad Code (Embed Script)
                    </label>
                    <div className="flex gap-2">
                      <textarea
                        readOnly
                        rows={2}
                        value={`<script src="${smartlinkModal.data?.anchor_domain ? 'https://' + smartlinkModal.data.anchor_domain : ''}/ad.js?pub=${smartlinkModal.data?.public_id}"></script>`}
                        className={`${inp} font-mono text-xs resize-none`}
                      />
                      <button
                        onClick={() => copyText(`<script src="${smartlinkModal.data?.anchor_domain ? 'https://' + smartlinkModal.data.anchor_domain : ''}/ad.js?pub=${smartlinkModal.data?.public_id}"></script>`)}
                        className="px-3 rounded-xl border border-gray-200 hover:bg-gray-50 text-gray-600 flex items-center"
                        title="Copy"
                      >
                        <Copy size={16} />
                      </button>
                    </div>
                  </div>
                )}

                {(smartlinkModal.data?.website_smartlinks || []).map((ws: any, idx: number) => (
                  <div key={ws.website_id}>
                    <label className="block text-xs font-semibold text-gray-700 mb-1">
                      Website: <span className="font-mono text-blue-600">{ws.domain || ws.name || ws.website_id || `Site ${idx + 1}`}</span>
                    </label>
                    <div className="flex gap-2">
                      <input readOnly value={ws.smartlink} className={`${inp} font-mono text-xs`} />
                      <button onClick={() => copyText(ws.smartlink)}
                        className="px-3 rounded-xl border border-gray-200 hover:bg-gray-50 text-gray-600 flex items-center" title="Copy"><Copy size={16} /></button>
                    </div>
                  </div>
                ))}
              </div>
              <div className="flex gap-3 mt-6">
                <button onClick={() => setSmartlinkModal(null)}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50">Close</button>
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
