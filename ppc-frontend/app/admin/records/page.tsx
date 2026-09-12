'use client'

import { useState, useEffect, useCallback } from 'react'
import { ChevronDown, ChevronRight, Download, Trash2, Globe, BarChart3 } from 'lucide-react'
import { toast } from 'sonner'
import Sidebar from '@/components/shared/Sidebar'
import { StatusBadge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/loading'
import { adminApi, downloadBlob } from '@/lib/api'
import { useAuth } from '@/lib/hooks/useAuth'

export default function RecordsPage() {
  const { initialize } = useAuth()
  const [records, setRecords] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [deleteModal, setDeleteModal] = useState<any>(null)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => { initialize() }, [])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params: any = {}
      if (dateFrom) params.date_from = dateFrom
      if (dateTo) params.date_to = dateTo
      if (!dateFrom && !dateTo) params.days = 30
      const res = await adminApi.getRecords(params)
      setRecords(res.data.records.filter((r: any) => r.publisher?.role !== 'admin'))
    } catch { toast.error('Failed to load records') }
    finally { setLoading(false) }
  }, [dateFrom, dateTo])

  useEffect(() => { load() }, [load])

  const toggleExpand = (id: string) => {
    setExpanded(prev => { const next = new Set(prev); if (next.has(id)) next.delete(id); else next.add(id); return next })
  }

  const handleExportAll = async () => {
    try {
      // Forward the on-screen date range so the CSV matches what's displayed.
      const params: any = {}
      if (dateFrom) params.date_from = dateFrom
      if (dateTo) params.date_to = dateTo
      if (!dateFrom && !dateTo) params.days = 30
      const res = await adminApi.exportRecordsCSV(params)
      downloadBlob(res.data, `records_${Date.now()}.csv`)
      toast.success('Records exported')
    } catch { toast.error('Export failed') }
  }

  const handleDownloadPublisher = async (pub: any) => {
    try {
      const res = await adminApi.downloadPublisherCSV(pub.publisher.id)
      downloadBlob(res.data, `publisher_${pub.publisher.name}_${Date.now()}.csv`)
      toast.success('Downloaded')
    } catch { toast.error('Download failed') }
  }

  const handleDelete = async () => {
    if (!deleteModal) return
    setDeleting(true)
    try {
      await adminApi.deletePublisher(deleteModal.publisher.id)
      toast.success('Publisher and all records deleted')
      setDeleteModal(null)
      load()
    } catch { toast.error('Delete failed') }
    finally { setDeleting(false) }
  }

  const inputClass = "px-3 py-2 border border-gray-200 rounded-xl text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary text-sm"

  return (
    <div className="flex min-h-screen bg-[#f8f9fb]">
      <Sidebar />
      <div className="flex-1 lg:ml-64 p-6 lg:p-8 min-w-0">
        <div className="flex items-center justify-between mb-8 pt-12 lg:pt-0">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Records & History</h1>
            <p className="text-gray-400 text-sm mt-0.5">Publisher data records and activity logs</p>
          </div>
          <button onClick={handleExportAll} className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium border border-gray-200 text-gray-700 hover:bg-gray-50">
            <Download size={16} /> Export All CSV
          </button>
        </div>

        {/* Custom Date Range */}
        <div className="bg-white rounded-2xl border border-gray-100 p-4 mb-6 flex flex-wrap gap-3 items-end">
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">From Date</label>
            <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} className={inputClass} />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">To Date</label>
            <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} className={inputClass} />
          </div>
          <button onClick={load} className="bg-primary hover:bg-primary-dark text-white px-4 py-2 rounded-xl text-sm font-medium">Apply</button>
        </div>

        {/* Records */}
        {loading ? (
          <div className="space-y-3">{[1,2,3].map(i => <div key={i} className="shimmer h-20 rounded-2xl" />)}</div>
        ) : records.length === 0 ? (
          <div className="text-center py-16 text-gray-400">
            <BarChart3 size={48} className="mx-auto mb-4 opacity-30" />
            <p>No records found for the selected period</p>
          </div>
        ) : (
          <div className="space-y-3">
            {records.map((record) => {
              const pub = record.publisher
              const isExpanded = expanded.has(pub.id)
              return (
                <div key={pub.id} className="bg-white rounded-2xl border border-gray-100 overflow-hidden">
                  <div className="flex items-center justify-between p-4 cursor-pointer hover:bg-gray-50 transition-colors" onClick={() => toggleExpand(pub.id)}>
                    <div className="flex items-center gap-4">
                      <div className="w-10 h-10 rounded-xl bg-primary/10 flex items-center justify-center font-bold text-primary text-sm flex-shrink-0">
                        {pub.name?.[0]?.toUpperCase()}
                      </div>
                      <div>
                        <p className="font-semibold text-gray-900">{pub.name}</p>
                        <p className="text-xs text-gray-500">{pub.email}</p>
                      </div>
                      <StatusBadge status={pub.status} />
                    </div>
                    <div className="flex items-center gap-6">
                      <div className="text-right hidden md:block">
                        <p className="text-xs text-gray-500">Clicks</p>
                        <p className="text-sm font-mono text-gray-900">{(record.stats?.total_clicks ?? 0).toLocaleString()}</p>
                      </div>
                      <div className="text-right hidden md:block">
                        <p className="text-xs text-gray-500">Earnings</p>
                        <p className="text-sm font-mono text-red-600 font-semibold">${(record.stats?.earnings ?? 0).toFixed(2)}</p>
                      </div>
                      <div className="flex items-center gap-1">
                        <button onClick={e => { e.stopPropagation(); handleDownloadPublisher(record) }}
                          className="p-2 rounded text-gray-400 hover:text-gray-900 hover:bg-gray-100"><Download size={16} /></button>
                        <button onClick={e => { e.stopPropagation(); setDeleteModal(record) }}
                          className="p-2 rounded text-red-400 hover:text-red-600 hover:bg-red-50"><Trash2 size={16} /></button>
                        {isExpanded ? <ChevronDown size={18} className="text-gray-400" /> : <ChevronRight size={18} className="text-gray-400" />}
                      </div>
                    </div>
                  </div>

                  {isExpanded && (
                    <div className="border-t border-gray-100 bg-gray-50 p-4">
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                        {[
                          { label: 'Total Clicks', value: (record.stats?.total_clicks ?? 0).toLocaleString() },
                          { label: 'Valid Clicks', value: (record.stats?.valid_clicks ?? 0).toLocaleString(), color: 'text-green-600' },
                          { label: 'Invalid Clicks', value: (record.stats?.invalid_clicks ?? 0).toLocaleString(), color: 'text-red-600' },
                          { label: 'Earnings', value: `$${(record.stats?.earnings ?? 0).toFixed(4)}`, color: 'text-red-600' },
                        ].map(s => (
                          <div key={s.label} className="p-3 rounded-xl bg-white border border-gray-100">
                            <p className="text-xs text-gray-500 mb-1">{s.label}</p>
                            <p className={`font-mono font-semibold ${s.color || 'text-gray-900'}`}>{s.value}</p>
                          </div>
                        ))}
                      </div>
                      {record.websites?.length > 0 && (
                        <div>
                          <p className="text-sm font-semibold text-gray-900 mb-2 flex items-center gap-2"><Globe size={14} /> Websites ({record.websites.length})</p>
                          <div className="space-y-2">
                            {record.websites.map((w: any) => (
                              <div key={w.id} className="flex items-center justify-between px-4 py-3 rounded-xl bg-white border border-gray-100">
                                <div>
                                  <p className="text-sm text-gray-900 font-medium">{w.domain}</p>
                                  <p className="text-xs text-gray-500">Clicks: {w.total_clicks ?? 0} | Valid: {w.valid_clicks ?? 0}</p>
                                </div>
                                <span className="text-red-600 font-mono text-sm font-semibold">${(w.total_earnings ?? 0).toFixed(4)}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}

        {deleteModal && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-6 w-full max-w-sm text-center shadow-2xl border border-gray-100">
              <div className="w-12 h-12 rounded-xl flex items-center justify-center mx-auto mb-4 bg-red-50">
                <Trash2 className="text-red-600" size={24} />
              </div>
              <h3 className="text-lg font-bold text-gray-900 mb-2">Delete Publisher Record</h3>
              <p className="text-gray-500 text-sm mb-6">Delete all records for <strong className="text-gray-900">{deleteModal.publisher.name}</strong>? This cannot be undone.</p>
              <div className="flex gap-3">
                <button onClick={handleDelete} disabled={deleting}
                  className="flex-1 bg-red-600 hover:bg-red-700 text-white py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center">
                  {deleting ? <Spinner size={16} /> : 'Yes, Delete All'}
                </button>
                <button onClick={() => setDeleteModal(null)}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50">Cancel</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
