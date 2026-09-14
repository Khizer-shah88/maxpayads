'use client'

import { useState, useEffect, useCallback } from 'react'
import { ShieldAlert, ShieldX, AlertCircle, Trash2 } from 'lucide-react'
import { toast } from 'sonner'
import Sidebar from '@/components/shared/Sidebar'
import ConfirmDialog from '@/components/ui/ConfirmDialog'
import StatCard from '@/components/shared/StatCard'
import { analyticsApi } from '@/lib/api'
import { useAuth } from '@/lib/hooks/useAuth'

export default function FraudPage() {
  const { initialize } = useAuth()
  const [stats, setStats] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [deleting, setDeleting] = useState<string | null>(null)

  // Styled delete confirmations (replace native confirm() / alert())
  const [deleteReasonTarget, setDeleteReasonTarget] = useState<string | null>(null)
  const [deleteIpTarget, setDeleteIpTarget] = useState<string | null>(null)

  useEffect(() => { initialize() }, [])

  const loadStats = useCallback(() => {
    setLoading(true)
    analyticsApi.getFraudStats(30)
      .then(res => setStats(res.data.stats))
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { loadStats() }, [loadStats])

  const handleDeleteReason = async (reason: string) => {
    setDeleting(`reason:${reason}`)
    try {
      await analyticsApi.deleteFraudByReason(reason)
      setDeleteReasonTarget(null)
      loadStats()
    } catch (err) {
      console.error(err)
      toast.error('Failed to delete')
    } finally {
      setDeleting(null)
    }
  }

  const handleDeleteIp = async (ip: string) => {
    setDeleting(`ip:${ip}`)
    try {
      await analyticsApi.deleteFraudByIp(ip)
      setDeleteIpTarget(null)
      loadStats()
    } catch (err) {
      console.error(err)
      toast.error('Failed to delete')
    } finally {
      setDeleting(null)
    }
  }

  const fraudByReason = stats?.fraud_by_reason || {}

  return (
    <div className="flex min-h-screen bg-[#f8f9fb]">
      <Sidebar />
      <div className="flex-1 lg:ml-64 p-6 lg:p-8 min-w-0 overflow-x-hidden">
        <div className="mb-8 pt-12 lg:pt-0">
          <h1 className="text-2xl font-bold text-gray-900">Fraud Detection</h1>
          <p className="text-gray-400 text-sm mt-0.5">Rule-based + Machine Learning fraud protection</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <StatCard title="Total Fraud Blocked" value={stats?.total_fraud || 0} icon={<ShieldX size={20} />} color="danger" loading={loading} />
          <StatCard title="Today's Fraud" value={stats?.today_fraud || 0} icon={<ShieldAlert size={20} />} color="warning" loading={loading} />
          <StatCard title="Fraud Rate" value={`${stats?.fraud_rate || 0}%`} icon={<AlertCircle size={20} />} color="danger" loading={loading} />
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
          {/* Fraud by Reason */}
          <div className="bg-white rounded-2xl border border-gray-100 p-6">
            <h2 className="text-base font-semibold text-gray-900 mb-4">Fraud by Reason</h2>
            <div className="space-y-4">
              {Object.entries(fraudByReason).map(([reason, count]: any) => {
                const total = stats?.total_fraud || 1
                const pct = Math.round((count / total) * 100)
                const isDeleting = deleting === `reason:${reason}`
                return (
                  <div key={reason}>
                    <div className="flex justify-between items-center text-sm mb-1">
                      <span className="text-gray-600 capitalize">{reason.replace(/_/g, ' ')}</span>
                      <div className="flex items-center gap-2">
                        <span className="text-gray-900 font-mono font-medium">{count.toLocaleString()} ({pct}%)</span>
                        <button
                          onClick={() => setDeleteReasonTarget(reason)}
                          disabled={isDeleting}
                          className="p-1.5 rounded-xl text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors disabled:opacity-50"
                          title={`Delete all "${reason.replace(/_/g, ' ')}" fraud clicks`}
                        >
                          <Trash2 size={14} className={isDeleting ? 'animate-spin' : ''} />
                        </button>
                      </div>
                    </div>
                    <div className="h-2 rounded-full bg-gray-100 overflow-hidden">
                      <div className="h-full rounded-full bg-red-500 transition-all duration-1000" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                )
              })}
              {Object.keys(fraudByReason).length === 0 && !loading && (
                <p className="text-gray-400 text-sm text-center py-6">No fraud data in last 30 days</p>
              )}
            </div>
          </div>

          {/* Top Fraud IPs */}
          <div className="bg-white rounded-2xl border border-gray-100 p-6">
            <h2 className="text-base font-semibold text-gray-900 mb-4">Top Fraud IPs</h2>
            <div className="space-y-2">
              {(stats?.top_fraud_ips || []).map((item: any, i: number) => {
                const isDeleting = deleting === `ip:${item.ip}`
                return (
                  <div key={item.ip} className="flex items-center justify-between p-3 rounded-xl bg-red-50 border border-red-100">
                    <div className="flex items-center gap-3">
                      <span className="text-xs text-gray-400 font-mono">#{i + 1}</span>
                      <span className="font-mono text-sm text-gray-900">{item.ip}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-red-600 font-mono text-sm font-semibold">{item.count} hits</span>
                      <button
                        onClick={() => setDeleteIpTarget(item.ip)}
                        disabled={isDeleting}
                        className="p-1.5 rounded-xl text-red-400 hover:text-red-700 hover:bg-red-100 transition-colors disabled:opacity-50"
                        title={`Delete all fraud clicks from ${item.ip}`}
                      >
                        <Trash2 size={14} className={isDeleting ? 'animate-spin' : ''} />
                      </button>
                    </div>
                  </div>
                )
              })}
              {(!stats?.top_fraud_ips?.length) && !loading && (
                <p className="text-gray-400 text-sm text-center py-6">No fraud IPs recorded</p>
              )}
            </div>
          </div>
        </div>

        {/* Detection Rules */}
        <div className="bg-white rounded-2xl border border-gray-100 p-6 mt-6">
          <h2 className="text-base font-semibold text-gray-900 mb-4">Active Detection Rules</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {[
              { rule: 'Bot User Agent', desc: 'Detects known bots, crawlers, headless browsers' },
              { rule: 'Datacenter IPs', desc: 'Blocks AWS, GCP, Azure, DigitalOcean IPs' },
              { rule: 'Rate Limiting', desc: 'Max 10 clicks/IP/minute' },
              { rule: 'ML Anomaly (Isolation Forest)', desc: 'Detects unusual click patterns' },
              { rule: 'Duplicate Clicks', desc: 'Same IP+publisher within 10 minutes' },
            ].map(item => (
              <div key={item.rule} className="p-4 rounded-xl bg-emerald-50 border border-emerald-200">
                <div className="flex items-center gap-2 mb-1">
                  <div className="w-2 h-2 rounded-full bg-green-500" />
                  <span className="text-sm font-semibold text-gray-900">{item.rule}</span>
                </div>
                <p className="text-xs text-gray-500">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>

        {/* ── Styled delete confirmations ──────────────────────────────────── */}
        <ConfirmDialog
          open={deleteReasonTarget !== null}
          title="Delete Fraud Clicks"
          message={<>Delete all fraud clicks with reason <strong className="text-gray-900 capitalize">{deleteReasonTarget?.replace(/_/g, ' ')}</strong>? This cannot be undone.</>}
          confirmLabel="Delete All"
          loading={deleting === `reason:${deleteReasonTarget}`}
          onConfirm={() => { if (deleteReasonTarget) handleDeleteReason(deleteReasonTarget) }}
          onCancel={() => setDeleteReasonTarget(null)}
        />
        <ConfirmDialog
          open={deleteIpTarget !== null}
          title="Delete Fraud Clicks"
          message={<>Delete all fraud clicks from IP <strong className="text-gray-900 font-mono">{deleteIpTarget}</strong>? This cannot be undone.</>}
          confirmLabel="Delete All"
          loading={deleting === `ip:${deleteIpTarget}`}
          onConfirm={() => { if (deleteIpTarget) handleDeleteIp(deleteIpTarget) }}
          onCancel={() => setDeleteIpTarget(null)}
        />
      </div>
    </div>
  )
}
