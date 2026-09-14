'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { CheckCircle, XCircle, CreditCard, Trash2, Paperclip, ExternalLink, Pencil } from 'lucide-react'
import { toast } from 'sonner'
import Sidebar from '@/components/shared/Sidebar'
import ConfirmDialog from '@/components/ui/ConfirmDialog'
import DataTable from '@/components/tables/DataTable'
import { StatusBadge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/loading'
import { withdrawalApi } from '@/lib/api'
import { useAuth } from '@/lib/hooks/useAuth'
import type { Withdrawal } from '@/types'
import { format } from 'date-fns'

const API_BASE = '/api'

export default function AdminWithdrawalsPage() {
  const { initialize } = useAuth()
  const [withdrawals, setWithdrawals] = useState<Withdrawal[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState('')
  const [rejectModal, setRejectModal] = useState<Withdrawal | null>(null)
  const [rejectNote, setRejectNote] = useState('')
  const [payModal, setPayModal] = useState<Withdrawal | null>(null)
  const [payForm, setPayForm] = useState({ transaction_id: '', admin_note: '' })
  const [proofFile, setProofFile] = useState<File | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const [saving, setSaving] = useState(false)
  const [editModal, setEditModal] = useState<Withdrawal | null>(null)
  const [editForm, setEditForm] = useState({ transaction_id: '', admin_note: '' })
  const [editProofFile, setEditProofFile] = useState<File | null>(null)
  const editFileRef = useRef<HTMLInputElement>(null)

  // Styled confirmations (replace native confirm())
  const [approveTarget, setApproveTarget] = useState<Withdrawal | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Withdrawal | null>(null)
  const [approving, setApproving] = useState(false)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => { initialize() }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await withdrawalApi.getAdminWithdrawals({ status: statusFilter || undefined, page, limit: 50 })
      setWithdrawals(res.data.withdrawals)
      setTotal(res.data.total)
    } catch { toast.error('Failed to load withdrawals') }
    finally { setLoading(false) }
  }, [statusFilter, page])

  useEffect(() => { load() }, [load])

  const handleApprove = async (w: Withdrawal) => {
    setApproving(true)
    try {
      await withdrawalApi.processWithdrawal(w.id, { action: 'approve' })
      toast.success('Withdrawal approved')
      setApproveTarget(null)
      load()
    } catch { toast.error('Failed to approve') }
    finally { setApproving(false) }
  }

  const handleReject = async () => {
    if (!rejectModal) return
    setSaving(true)
    try {
      await withdrawalApi.processWithdrawal(rejectModal.id, { action: 'reject', admin_note: rejectNote })
      toast.success('Withdrawal rejected')
      setRejectModal(null)
      setRejectNote('')
      load()
    } catch { toast.error('Failed to reject') }
    finally { setSaving(false) }
  }

  const handlePay = async () => {
    if (!payModal) return
    if (!payForm.transaction_id.trim()) { toast.error('Transaction ID is required'); return }
    setSaving(true)
    try {
      const fd = new FormData()
      fd.append('transaction_id', payForm.transaction_id)
      if (payForm.admin_note) fd.append('admin_note', payForm.admin_note)
      if (proofFile) fd.append('proof_file', proofFile)
      await withdrawalApi.payWithdrawal(payModal.id, fd)
      toast.success('Withdrawal marked as paid')
      setPayModal(null)
      setPayForm({ transaction_id: '', admin_note: '' })
      setProofFile(null)
      load()
    } catch { toast.error('Failed to mark as paid') }
    finally { setSaving(false) }
  }

  const handleDelete = async (w: Withdrawal) => {
    setDeleting(true)
    try {
      await withdrawalApi.deleteWithdrawal(w.id)
      toast.success('Withdrawal deleted')
      setDeleteTarget(null)
      load()
    } catch { toast.error('Failed to delete') }
    finally { setDeleting(false) }
  }

  const openEditModal = (w: Withdrawal) => {
    setEditModal(w)
    setEditForm({ transaction_id: w.transaction_id || '', admin_note: w.admin_note || '' })
    setEditProofFile(null)
  }

  const handleEdit = async () => {
    if (!editModal) return
    setSaving(true)
    try {
      const fd = new FormData()
      fd.append('transaction_id', editForm.transaction_id)
      fd.append('admin_note', editForm.admin_note)
      if (editProofFile) fd.append('proof_file', editProofFile)
      await withdrawalApi.editWithdrawal(editModal.id, fd)
      toast.success('Withdrawal updated')
      setEditModal(null)
      load()
    } catch { toast.error('Failed to update') }
    finally { setSaving(false) }
  }

  const inputClass = "w-full px-4 py-2.5 border border-gray-200 rounded-xl text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary text-sm"

  const columns = [
    { key: 'publisher_name', label: 'Publisher', render: (w: Withdrawal) => <span className="font-medium text-gray-900">{w.publisher_name}</span> },
    { key: 'amount', label: 'Amount', render: (w: Withdrawal) => <span className="text-red-600 font-mono font-bold">${w.amount.toFixed(2)}</span> },
    { key: 'payment_method', label: 'Method', render: (w: Withdrawal) => <span className="capitalize text-sm">{w.payment_method.replace(/_/g, ' ')}</span> },
    { key: 'status', label: 'Status', render: (w: Withdrawal) => <StatusBadge status={w.status} /> },
    { key: 'transaction_id', label: 'TXN ID', render: (w: Withdrawal) => <span className="font-mono text-xs text-gray-400">{w.transaction_id || '—'}</span> },
    { key: 'proof_url', label: 'Proof', render: (w: Withdrawal) => w.proof_url ? (
      <a href={`${API_BASE}${w.proof_url}`} target="_blank" rel="noreferrer"
        className="flex items-center gap-1 text-xs text-blue-600 hover:underline">
        <Paperclip size={12} /><ExternalLink size={12} />View
      </a>
    ) : <span className="text-gray-300 text-xs">—</span> },
    { key: 'admin_note', label: 'Note', render: (w: Withdrawal) => <span className="text-xs text-gray-500 max-w-[120px] block truncate">{w.admin_note || '—'}</span> },
    { key: 'requested_at', label: 'Requested', render: (w: Withdrawal) => <span className="text-xs text-gray-500">{format(new Date(w.requested_at), 'MMM d, HH:mm')}</span> },
    {
      key: 'actions', label: 'Actions',
      render: (w: Withdrawal) => (
        <div className="flex items-center gap-1">
          {w.status === 'pending' && (<>
            <button onClick={() => setApproveTarget(w)} title="Approve"
              className="p-1.5 rounded text-green-600 hover:bg-green-50 transition-colors">
              <CheckCircle size={15} />
            </button>
            <button onClick={() => { setRejectModal(w); setRejectNote('') }} title="Reject"
              className="p-1.5 rounded text-red-500 hover:bg-red-50 transition-colors">
              <XCircle size={15} />
            </button>
          </>)}
          {w.status === 'approved' && (
            <button onClick={() => { setPayModal(w); setPayForm({ transaction_id: '', admin_note: '' }); setProofFile(null) }} title="Mark as Paid"
              className="p-1.5 rounded text-blue-600 hover:bg-blue-50 transition-colors">
              <CreditCard size={15} />
            </button>
          )}
          <button onClick={() => openEditModal(w)} title="Edit"
            className="p-1.5 rounded text-gray-400 hover:text-amber-600 hover:bg-amber-50 transition-colors">
            <Pencil size={15} />
          </button>
          <button onClick={() => setDeleteTarget(w)} title="Delete"
            className="p-1.5 rounded text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors">
            <Trash2 size={15} />
          </button>
        </div>
      )
    },
  ]

  return (
    <div className="flex min-h-screen bg-[#f8f9fb]">
      <Sidebar />
      <div className="flex-1 lg:ml-64 p-6 lg:p-8 min-w-0 overflow-x-hidden">
        <div className="mb-8 pt-12 lg:pt-0">
          <h1 className="text-2xl font-bold text-gray-900">Withdrawals</h1>
          <p className="text-gray-400 text-sm mt-0.5">Manage publisher payment requests</p>
        </div>

        <div className="flex gap-2 mb-6 flex-wrap">
          {['', 'pending', 'approved', 'rejected', 'paid'].map(s => (
            <button key={s} onClick={() => { setStatusFilter(s); setPage(1) }}
              className={`px-4 py-2 rounded-xl text-sm font-medium border transition-colors ${
                statusFilter === s ? 'bg-primary text-white border-primary' : 'text-gray-500 border-gray-200 hover:bg-gray-50'
              }`}>
              {s === '' ? 'All' : s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>

        <div className="bg-white rounded-2xl border border-gray-100 p-6">
          <DataTable columns={columns} data={withdrawals} loading={loading}
            pagination={{ page, total, limit: 50, onPageChange: setPage }}
            emptyMessage="No withdrawals found" />
        </div>

        {rejectModal && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-6 w-full max-w-sm shadow-2xl border border-gray-100">
              <h3 className="text-lg font-bold text-gray-900 mb-1">Reject Withdrawal</h3>
              <p className="text-gray-500 text-sm mb-4">
                {rejectModal.publisher_name} — <span className="text-red-600 font-bold">${rejectModal.amount.toFixed(2)}</span>
              </p>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Reason / Note (optional)</label>
                <textarea value={rejectNote} onChange={e => setRejectNote(e.target.value)}
                  placeholder="Reason for rejection..." rows={3}
                  className={`${inputClass} resize-none`} />
              </div>
              <div className="flex gap-3 mt-5">
                <button onClick={handleReject} disabled={saving}
                  className="flex-1 bg-red-600 hover:bg-red-700 text-white py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center disabled:bg-gray-300">
                  {saving ? <Spinner size={16} /> : 'Reject'}
                </button>
                <button onClick={() => setRejectModal(null)}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50">Cancel</button>
              </div>
            </div>
          </div>
        )}

        {payModal && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-2xl border border-gray-100">
              <h3 className="text-lg font-bold text-gray-900 mb-1">Mark as Paid</h3>
              <p className="text-gray-500 text-sm mb-3">
                {payModal.publisher_name} — <span className="text-red-600 font-bold">${payModal.amount.toFixed(2)}</span>
                <span className="ml-2 text-gray-400 capitalize">({payModal.payment_method.replace(/_/g, ' ')})</span>
              </p>

              {/* Payment Details */}
              <div className="bg-gray-50 rounded-xl border border-gray-100 p-3 mb-4">
                <p className="text-xs font-medium text-gray-500 mb-1">Payment Details</p>
                <p className="text-sm font-mono text-gray-900 break-all">{payModal.payment_details}</p>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Transaction ID <span className="text-red-500">*</span></label>
                  <input value={payForm.transaction_id} onChange={e => setPayForm(p => ({ ...p, transaction_id: e.target.value }))}
                    placeholder="TX hash / receipt number" className={inputClass} />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Proof (image or PDF)</label>
                  <div onClick={() => fileRef.current?.click()}
                    className="border-2 border-dashed border-gray-200 rounded-xl p-4 text-center cursor-pointer hover:border-primary/50 transition-colors">
                    {proofFile ? (
                      <p className="text-sm text-gray-900 font-medium">{proofFile.name}</p>
                    ) : (
                      <p className="text-sm text-gray-400">Click to upload image or PDF</p>
                    )}
                  </div>
                  <input ref={fileRef} type="file" accept="image/*,.pdf" className="hidden"
                    onChange={e => setProofFile(e.target.files?.[0] || null)} />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Admin Note (optional)</label>
                  <input value={payForm.admin_note} onChange={e => setPayForm(p => ({ ...p, admin_note: e.target.value }))}
                    placeholder="Internal note..." className={inputClass} />
                </div>
              </div>
              <div className="flex gap-3 mt-6">
                <button onClick={handlePay} disabled={saving || !payForm.transaction_id.trim()}
                  className="flex-1 bg-primary hover:bg-primary-dark text-white py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 disabled:bg-gray-300">
                  {saving ? <Spinner size={16} /> : <><CreditCard size={16} /> Confirm Payment</>}
                </button>
                <button onClick={() => setPayModal(null)}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50">Cancel</button>
              </div>
            </div>
          </div>
        )}
        {editModal && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-2xl border border-gray-100">
              <h3 className="text-lg font-bold text-gray-900 mb-1">Edit Withdrawal</h3>
              <p className="text-gray-500 text-sm mb-3">
                {editModal.publisher_name} — <span className="text-red-600 font-bold">${editModal.amount.toFixed(2)}</span>
                <span className="ml-2 capitalize text-gray-400">({editModal.payment_method.replace(/_/g, ' ')})</span>
              </p>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Transaction ID</label>
                  <input value={editForm.transaction_id} onChange={e => setEditForm(p => ({ ...p, transaction_id: e.target.value }))}
                    placeholder="TX hash / receipt number" className={inputClass} />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Replace Proof (image or PDF)</label>
                  {editModal.proof_url && !editProofFile && (
                    <div className="mb-2 flex items-center gap-2 text-xs text-blue-600">
                      <Paperclip size={12} />
                      <a href={`${API_BASE}${editModal.proof_url}`} target="_blank" rel="noreferrer" className="hover:underline">Current proof</a>
                    </div>
                  )}
                  <div onClick={() => editFileRef.current?.click()}
                    className="border-2 border-dashed border-gray-200 rounded-xl p-4 text-center cursor-pointer hover:border-primary/50 transition-colors">
                    {editProofFile ? (
                      <p className="text-sm text-gray-900 font-medium">{editProofFile.name}</p>
                    ) : (
                      <p className="text-sm text-gray-400">Click to upload new image or PDF</p>
                    )}
                  </div>
                  <input ref={editFileRef} type="file" accept="image/*,.pdf" className="hidden"
                    onChange={e => setEditProofFile(e.target.files?.[0] || null)} />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Admin Note</label>
                  <input value={editForm.admin_note} onChange={e => setEditForm(p => ({ ...p, admin_note: e.target.value }))}
                    placeholder="Internal note..." className={inputClass} />
                </div>
              </div>
              <div className="flex gap-3 mt-6">
                <button onClick={handleEdit} disabled={saving}
                  className="flex-1 bg-amber-500 hover:bg-amber-600 text-white py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 disabled:bg-gray-300">
                  {saving ? <Spinner size={16} /> : <><Pencil size={16} /> Save Changes</>}
                </button>
                <button onClick={() => setEditModal(null)}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50">Cancel</button>
              </div>
            </div>
          </div>
        )}

        {/* ── Styled approve / delete confirmations ───────────────────────── */}
        <ConfirmDialog
          open={approveTarget !== null}
          title="Approve Withdrawal"
          tone="info"
          message={<>Approve <strong className="text-gray-900 font-mono">${approveTarget?.amount.toFixed(2)}</strong> for <strong className="text-gray-900">{approveTarget?.publisher_name}</strong>?</>}
          confirmLabel="Approve"
          loading={approving}
          onConfirm={() => { if (approveTarget) handleApprove(approveTarget) }}
          onCancel={() => setApproveTarget(null)}
        />
        <ConfirmDialog
          open={deleteTarget !== null}
          title="Delete Withdrawal Request"
          message={<>Delete this withdrawal request from <strong className="text-gray-900">{deleteTarget?.publisher_name}</strong>? This cannot be undone.</>}
          confirmLabel="Delete"
          loading={deleting}
          onConfirm={() => { if (deleteTarget) handleDelete(deleteTarget) }}
          onCancel={() => setDeleteTarget(null)}
        />
      </div>
    </div>
  )
}
