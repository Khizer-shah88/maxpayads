'use client'

import { useState, useEffect, useCallback } from 'react'
import { Wallet, DollarSign, AlertCircle, Paperclip, ExternalLink, CheckCircle2, ArrowRight } from 'lucide-react'
import { toast } from 'sonner'
import Link from 'next/link'
import PublisherSidebar from '@/components/shared/PublisherSidebar'
import DataTable from '@/components/tables/DataTable'
import { StatusBadge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/loading'
import { publisherApi, withdrawalApi } from '@/lib/api'
import { useAuth } from '@/lib/hooks/useAuth'
import type { Withdrawal } from '@/types'
import { format } from 'date-fns'

const API_BASE = '/api'

export default function PublisherWithdrawalsPage() {
  const { initialize } = useAuth()
  const [balance, setBalance] = useState(0)
  const [withdrawals, setWithdrawals] = useState<Withdrawal[]>([])
  const [loading, setLoading] = useState(true)
  const [amount, setAmount] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [minAmount] = useState(10)

  // Saved payment method from profile
  const [savedMethod, setSavedMethod] = useState<string | null>(null)
  const [savedDetails, setSavedDetails] = useState<string | null>(null)

  useEffect(() => { initialize() }, [])

  const load = useCallback(async () => {
    try {
      const [dashRes, wdRes] = await Promise.all([
        publisherApi.getDashboard(),
        withdrawalApi.getMyWithdrawals(),
      ])
      const pub = dashRes.data.publisher
      setBalance(pub.balance || 0)
      setSavedMethod(pub.payment_method || null)
      setSavedDetails(pub.payment_details || null)
      setWithdrawals(wdRes.data.withdrawals)
    } catch { toast.error('Failed to load') }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { load() }, [load])

  const hasPaymentMethod = savedMethod && savedDetails

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!hasPaymentMethod) {
      toast.error('Please set up a payment method first')
      return
    }
    const amt = parseFloat(amount)
    if (amt < minAmount) { toast.error(`Minimum withdrawal is $${minAmount}`); return }
    if (amt > balance) { toast.error('Insufficient balance'); return }
    setSubmitting(true)
    try {
      await withdrawalApi.request({
        amount: amt,
        payment_method: savedMethod!,
        payment_details: savedDetails!,
      })
      toast.success('Withdrawal request submitted!')
      setAmount('')
      load()
    } catch (err: any) { toast.error(err.response?.data?.detail || err.response?.data?.error || 'Request failed') }
    finally { setSubmitting(false) }
  }

  const inputClass = "w-full px-4 py-2.5 border border-gray-200 rounded-xl text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary text-sm"

  const columns = [
    { key: 'amount', label: 'Amount', render: (w: Withdrawal) => <span className="text-red-600 font-mono font-bold">${w.amount.toFixed(2)}</span> },
    { key: 'payment_method', label: 'Method', render: (w: Withdrawal) => <span className="text-gray-700 capitalize">{w.payment_method.replace(/_/g, ' ')}</span> },
    { key: 'status', label: 'Status', render: (w: Withdrawal) => <StatusBadge status={w.status} /> },
    { key: 'transaction_id', label: 'TXN ID', render: (w: Withdrawal) => <span className="font-mono text-xs text-gray-500">{w.transaction_id || '—'}</span> },
    { key: 'proof_url', label: 'Proof', render: (w: Withdrawal) => w.proof_url ? (
      <a href={`${API_BASE}${w.proof_url}`} target="_blank" rel="noreferrer"
        className="flex items-center gap-1 text-xs text-blue-600 hover:underline">
        <Paperclip size={12} /><ExternalLink size={12} />View
      </a>
    ) : <span className="text-gray-300 text-xs">—</span> },
    { key: 'admin_note', label: 'Note', render: (w: Withdrawal) => w.admin_note ? <span className="text-xs text-gray-500">{w.admin_note}</span> : <span className="text-gray-300 text-xs">—</span> },
    { key: 'requested_at', label: 'Requested', render: (w: Withdrawal) => <span className="text-xs text-gray-500">{format(new Date(w.requested_at), 'MMM d, yyyy')}</span> },
    { key: 'processed_at', label: 'Processed', render: (w: Withdrawal) => w.processed_at ? <span className="text-xs text-gray-500">{format(new Date(w.processed_at), 'MMM d, yyyy')}</span> : <span className="text-gray-300">—</span> },
  ]

  return (
    <div className="flex min-h-screen bg-[#f8f9fb]">
      <PublisherSidebar />
      <div className="flex-1 lg:ml-64 p-6 lg:p-8">
        <div className="mb-8 pt-12 lg:pt-0">
          <h1 className="text-2xl font-bold text-gray-900">Withdrawals</h1>
          <p className="text-gray-400 text-sm mt-0.5">Request payments and track your withdrawal history</p>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 mb-6">
          {/* Balance Display */}
          <div className="bg-white rounded-2xl border border-gray-100 p-8 text-center">
            <div className="w-16 h-16 rounded-xl flex items-center justify-center mx-auto mb-4 bg-primary/10">
              <Wallet size={28} className="text-primary" />
            </div>
            <p className="text-gray-500 mb-2">Available Balance</p>
            <p className="text-5xl font-bold text-primary mb-1">
              ${loading ? '—' : balance.toFixed(2)}
            </p>
            <p className="text-xs text-gray-400">Minimum withdrawal: ${minAmount}</p>
          </div>

          {/* Request Form */}
          <div className="bg-white rounded-2xl border border-gray-100 p-6">
            <h2 className="text-base font-semibold text-gray-900 mb-5">Request Withdrawal</h2>

            {/* Payment Method Display */}
            {hasPaymentMethod ? (
              <div className="mb-5 p-4 bg-emerald-50 rounded-xl border border-emerald-100">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <CheckCircle2 size={14} className="text-emerald-600" />
                    <p className="text-xs font-semibold text-emerald-700 uppercase tracking-wider">Payment Method</p>
                  </div>
                  <Link href="/publisher/payment-methods" className="text-xs text-primary font-semibold hover:underline flex items-center gap-1">
                    Change <ArrowRight size={10} />
                  </Link>
                </div>
                <p className="text-sm font-medium text-gray-900 capitalize">{savedMethod!.replace(/_/g, ' ')}</p>
                <p className="text-xs text-gray-500 mt-1 truncate">{savedDetails}</p>
              </div>
            ) : (
              <div className="mb-5 p-4 bg-amber-50 rounded-xl border border-amber-200">
                <div className="flex items-center gap-2 mb-2">
                  <AlertCircle size={14} className="text-amber-600" />
                  <p className="text-xs font-semibold text-amber-700 uppercase tracking-wider">No Payment Method</p>
                </div>
                <p className="text-sm text-amber-700 mb-3">
                  You need to set up a payment method before requesting a withdrawal.
                </p>
                <Link href="/publisher/payment-methods"
                  className="inline-flex items-center gap-2 px-4 py-2 bg-primary hover:bg-primary-dark text-white text-sm font-semibold rounded-xl transition-all">
                  <Wallet size={14} /> Set Up Payment Method <ArrowRight size={14} />
                </Link>
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Amount (USD)</label>
                <div className="relative">
                  <DollarSign className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={16} />
                  <input type="number" step="0.01" min={minAmount} max={balance}
                    value={amount} onChange={e => setAmount(e.target.value)}
                    placeholder={`Min $${minAmount}`} className={`${inputClass} !pl-8`} required />
                </div>
              </div>
              {balance < minAmount && (
                <div className="flex items-center gap-2 p-3 rounded-xl bg-amber-50 border border-amber-200">
                  <AlertCircle size={16} className="text-amber-600 flex-shrink-0" />
                  <p className="text-xs text-amber-700">Your balance is below the minimum withdrawal amount of ${minAmount}.</p>
                </div>
              )}
              <button type="submit" disabled={submitting || balance < minAmount || !amount || !hasPaymentMethod}
                className="bg-primary hover:bg-primary-dark text-white w-full py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 disabled:bg-gray-300 disabled:cursor-not-allowed transition-all">
                {submitting ? <Spinner size={16} /> : <><Wallet size={16} /> Request Withdrawal</>}
              </button>
            </form>
          </div>
        </div>

        {/* Withdrawal History */}
        <div className="bg-white rounded-2xl border border-gray-100 p-6">
          <h2 className="text-base font-semibold text-gray-900 mb-4">Withdrawal History</h2>
          <DataTable columns={columns} data={withdrawals} loading={loading} emptyMessage="No withdrawal requests yet" />
        </div>
      </div>
    </div>
  )
}
