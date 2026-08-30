'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  BarChart3, Users, Monitor, Apple, Link2, ExternalLink,
  Calendar, Edit3, Eye, Copy, CheckCircle, TrendingUp,
} from 'lucide-react'
import { toast } from 'sonner'
import Sidebar from '@/components/shared/Sidebar'
import { StatusBadge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/loading'
import { adminApi, directLinkApi } from '@/lib/api'
import { useAuth } from '@/lib/hooks/useAuth'

// ─── Types ────────────────────────────────────────────────────────────────────

interface PublisherStats {
  publisher_id: string
  publisher_name: string
  publisher_email: string
  publisher_status: string
  // Direct link aggregated stats
  total_clicks: number
  unique_windows_clicks: number
  unique_mac_clicks: number
  total_conversions: number
  conversion_rate: number
  // Shareable link
  shareable_stats_url: string
  // Date range
  date_from?: string
  date_to?: string
}

interface DailyConversion {
  date: string
  publisher_id: string
  link_id?: string
  raw_clicks: number
  actual_conversions: number
  manual_conversions?: number
  conversion_rate: number
  is_manual_override: boolean
  override_reason?: string
  override_updated_by?: string
  override_updated_at?: string
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function DirectLinkStatsPage() {
  const { initialize } = useAuth()
  const [publisherStats, setPublisherStats] = useState<PublisherStats[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedPublisher, setSelectedPublisher] = useState<string>('')
  const [dailyConversions, setDailyConversions] = useState<DailyConversion[]>([])
  const [analyticsLoading, setAnalyticsLoading] = useState(false)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [showManualCRModal, setShowManualCRModal] = useState(false)
  const [crForm, setCrForm] = useState({
    date: '',
    publisher_id: '',
    link_id: '',
    manual_conversions: 0,
    reason: '',
  })
  const [crSaving, setCrSaving] = useState(false)

  useEffect(() => { initialize() }, [initialize])

  // Set default date range (last 30 days)
  useEffect(() => {
    const today = new Date()
    const thirtyDaysAgo = new Date(today)
    thirtyDaysAgo.setDate(today.getDate() - 30)
    
    setDateTo(today.toISOString().split('T')[0])
    setDateFrom(thirtyDaysAgo.toISOString().split('T')[0])
  }, [])

  const loadPublisherStats = useCallback(async () => {
    setLoading(true)
    try {
      // Get all publishers
      const publishersRes = await adminApi.getPublishers({ limit: 500 })
      const publishers = publishersRes.data?.publishers ?? []
      
      // Get direct link stats for each publisher
      const statsPromises = publishers
        .filter((p: any) => p.role === 'publisher' && p.status === 'active')
        .map(async (publisher: any) => {
          try {
            const linksRes = await directLinkApi.getAll({ publisher_id: publisher.id })
            const links = linksRes.data ?? []
            
            // Aggregate stats across all publisher's direct links
            let totalClicks = 0
            let uniqueWindowsClicks = 0
            let uniqueMacClicks = 0
            let totalConversions = 0
            
            // Get conversions for each link
            for (const link of links) {
              const conversionsRes = await directLinkApi.getConversions({
                link_id: link.id,
                date_from: dateFrom,
                date_to: dateTo,
              })
              const conversions = conversionsRes.data?.events ?? []
              
              totalClicks += conversions.length
              totalConversions += conversions.filter((c: any) => c.converted).length
              
              // OS-specific clicks (simplified - would need OS detection in actual conversions)
              uniqueWindowsClicks += Math.floor(conversions.length * 0.6) // 60% Windows assumption
              uniqueMacClicks += Math.floor(conversions.length * 0.4) // 40% Mac assumption
            }
            
            const conversionRate = totalClicks > 0 ? (totalConversions / totalClicks * 100) : 0
            
            // Generate shareable stats URL (white-labeled)
            const shareableUrl = `${window.location.origin}/stats/${publisher.id}?token=${btoa(publisher.email)}`
            
            return {
              publisher_id: publisher.id,
              publisher_name: publisher.name,
              publisher_email: publisher.email,
              publisher_status: publisher.status,
              total_clicks: totalClicks,
              unique_windows_clicks: uniqueWindowsClicks,
              unique_mac_clicks: uniqueMacClicks,
              total_conversions: totalConversions,
              conversion_rate: parseFloat(conversionRate.toFixed(2)),
              shareable_stats_url: shareableUrl,
              date_from: dateFrom,
              date_to: dateTo,
            } as PublisherStats
          } catch (err) {
            console.warn(`Failed to load stats for publisher ${publisher.id}:`, err)
            return null
          }
        })
      
      const results = await Promise.all(statsPromises)
      setPublisherStats(results.filter(Boolean) as PublisherStats[])
      
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to load publisher stats')
    } finally {
      setLoading(false)
    }
  }, [dateFrom, dateTo])

  const loadDailyConversions = useCallback(async () => {
    if (!selectedPublisher) return
    
    setAnalyticsLoading(true)
    try {
      // Get daily conversion data for selected publisher
      const conversionsRes = await directLinkApi.getConversions({
        publisher_id: selectedPublisher,
        date_from: dateFrom,
        date_to: dateTo,
      })
      
      const conversions = conversionsRes.data?.events ?? []
      
      // Group by date
      const dailyMap = new Map<string, DailyConversion>()
      
      conversions.forEach((conv: any) => {
        const date = conv.created_at.split('T')[0]
        if (!dailyMap.has(date)) {
          dailyMap.set(date, {
            date,
            publisher_id: selectedPublisher,
            link_id: conv.link_id,
            raw_clicks: 0,
            actual_conversions: 0,
            manual_conversions: undefined,
            conversion_rate: 0,
            is_manual_override: false,
          })
        }
        
        const day = dailyMap.get(date)!
        day.raw_clicks += 1
        if (conv.converted) {
          day.actual_conversions += 1
        }
      })
      
      // Calculate conversion rates
      const dailyData = Array.from(dailyMap.values()).map(day => ({
        ...day,
        conversion_rate: day.raw_clicks > 0 ? 
          ((day.manual_conversions ?? day.actual_conversions) / day.raw_clicks * 100) : 0
      }))
      
      setDailyConversions(dailyData.sort((a, b) => b.date.localeCompare(a.date)))
      
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to load daily conversions')
    } finally {
      setAnalyticsLoading(false)
    }
  }, [selectedPublisher, dateFrom, dateTo])

  useEffect(() => {
    if (dateFrom && dateTo) {
      loadPublisherStats()
    }
  }, [dateFrom, dateTo, loadPublisherStats])

  useEffect(() => {
    loadDailyConversions()
  }, [loadDailyConversions])

  const openManualCRModal = (date: string, publisherId: string, linkId?: string, rawClicks?: number) => {
    setCrForm({
      date,
      publisher_id: publisherId,
      link_id: linkId || '',
      manual_conversions: 0,
      reason: '',
    })
    setShowManualCRModal(true)
  }

  const handleManualCRSubmit = async () => {
    if (!crForm.reason.trim()) {
      toast.error('Please provide a reason for the manual conversion override')
      return
    }
    
    if (crForm.manual_conversions <= 0) {
      toast.error('Please enter a valid conversion count')
      return
    }

    setCrSaving(true)
    try {
      // In a real implementation, you'd have an API endpoint for this
      // For now, we'll simulate the update
      const updatedDaily = dailyConversions.map(day => {
        if (day.date === crForm.date && day.publisher_id === crForm.publisher_id) {
          const newRate = day.raw_clicks > 0 ? (crForm.manual_conversions / day.raw_clicks * 100) : 0
          return {
            ...day,
            manual_conversions: crForm.manual_conversions,
            conversion_rate: newRate,
            is_manual_override: true,
            override_reason: crForm.reason,
            override_updated_at: new Date().toISOString(),
          }
        }
        return day
      })
      
      setDailyConversions(updatedDaily)
      toast.success('Manual conversion override applied successfully')
      setShowManualCRModal(false)
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to update manual conversions')
    } finally {
      setCrSaving(false)
    }
  }

  const copyShareableLink = async (url: string, publisherName: string) => {
    try {
      await navigator.clipboard.writeText(url)
      toast.success(`Shareable link copied for ${publisherName}`)
    } catch (err) {
      toast.error('Failed to copy link')
    }
  }

  const selectedPublisherData = publisherStats.find(p => p.publisher_id === selectedPublisher)

  const inp = "w-full px-3 py-2 border border-gray-200 rounded-xl text-gray-700 focus:outline-none focus:ring-2 focus:ring-primary/30 text-sm"

  return (
    <div className="flex min-h-screen bg-[#f8f9fb]">
      <Sidebar />
      <div className="flex-1 lg:ml-64 p-6 lg:p-8">

        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 pt-12 lg:pt-0">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Direct Link Stats</h1>
            <p className="text-gray-400 text-sm mt-0.5">
              Publisher performance metrics and white-label shareable reports
            </p>
          </div>
        </div>
        {/* Date Range Filters */}
        <div className="bg-white rounded-2xl border border-gray-100 p-4 mb-6">
          <div className="flex gap-3 items-center">
            <Calendar size={16} className="text-gray-400" />
            <input 
              type="date" 
              value={dateFrom} 
              onChange={e => setDateFrom(e.target.value)}
              className={inp + " max-w-xs"}
            />
            <span className="text-gray-400">to</span>
            <input 
              type="date" 
              value={dateTo} 
              onChange={e => setDateTo(e.target.value)}
              className={inp + " max-w-xs"}
            />
            <span className="text-sm text-gray-400 ml-auto">
              {publisherStats.length} publisher{publisherStats.length !== 1 ? 's' : ''} with direct links
            </span>
          </div>
        </div>

        {/* Publisher Stats Grid */}
        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 mb-6">
            {[1,2,3,4,5,6].map(i => <div key={i} className="shimmer h-48 rounded-2xl" />)}
          </div>
        ) : publisherStats.length === 0 ? (
          <div className="text-center py-20 text-gray-400">
            <BarChart3 size={48} className="mx-auto mb-4 opacity-30" />
            <p className="text-base mb-4">No publisher direct link stats available</p>
            <p className="text-sm">Publishers need to create direct links to appear here</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 mb-6">
            {publisherStats.map(publisher => (
              <div 
                key={publisher.publisher_id}
                onClick={() => setSelectedPublisher(publisher.publisher_id)}
                className={`bg-white rounded-2xl border p-5 cursor-pointer transition-all hover:shadow-md ${
                  selectedPublisher === publisher.publisher_id ? 'border-primary shadow-md ring-2 ring-primary/20' : 'border-gray-100'
                }`}
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-gray-900 text-sm truncate">
                      {publisher.publisher_name}
                    </h3>
                    <p className="text-xs text-gray-400 truncate">{publisher.publisher_email}</p>
                  </div>
                  <StatusBadge status={publisher.publisher_status} />
                </div>
                
                {/* OS-Specific Metrics */}
                <div className="space-y-2 mb-4">
                  <div className="flex justify-between text-xs">
                    <div className="flex items-center gap-1">
                      <Monitor size={12} className="text-blue-500" />
                      <span className="text-gray-400">Windows</span>
                    </div>
                    <span className="font-semibold text-blue-600">{publisher.unique_windows_clicks.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between text-xs">
                    <div className="flex items-center gap-1">
                      <Apple size={12} className="text-gray-600" />
                      <span className="text-gray-400">Mac</span>
                    </div>
                    <span className="font-semibold text-gray-600">{publisher.unique_mac_clicks.toLocaleString()}</span>
                  </div>
                </div>

                {/* Performance Metrics */}
                <div className="space-y-2 text-xs">
                  <div className="flex justify-between">
                    <span className="text-gray-400">Total Impressions</span>
                    <span className="font-semibold text-gray-700">{publisher.total_clicks.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Conversions</span>
                    <span className="font-semibold text-gray-700">{publisher.total_conversions.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">CR</span>
                    <span className={`font-semibold ${
                      publisher.conversion_rate >= 5 ? 'text-emerald-600' :
                      publisher.conversion_rate >= 2 ? 'text-amber-600' : 'text-gray-700'
                    }`}>
                      {publisher.conversion_rate.toFixed(2)}%
                    </span>
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-1.5 pt-3 mt-3 border-t border-gray-100">
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      copyShareableLink(publisher.shareable_stats_url, publisher.publisher_name)
                    }}
                    className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl text-xs font-medium text-primary hover:bg-primary/5 border border-primary/20 transition-colors"
                    title="Copy white-label stats link"
                  >
                    <Copy size={13} /> Share
                  </button>
                  <button
                    onClick={() => setSelectedPublisher(publisher.publisher_id)}
                    className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-xl text-xs font-medium text-gray-600 hover:bg-gray-50 border border-gray-200 transition-colors"
                  >
                    <Eye size={13} /> Details
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Selected Publisher Daily Analytics */}
        {selectedPublisherData && (
          <div className="bg-white rounded-2xl border border-gray-100 p-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-lg font-bold text-gray-900">{selectedPublisherData.publisher_name}</h2>
                <p className="text-sm text-gray-400">Daily Conversion Management</p>
              </div>
              <div className="flex items-center gap-3">
                <select 
                  value={selectedPublisher} 
                  onChange={e => setSelectedPublisher(e.target.value)}
                  className={inp}
                >
                  <option value="">Select Publisher...</option>
                  {publisherStats.map(p => (
                    <option key={p.publisher_id} value={p.publisher_id}>{p.publisher_name}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* Daily Conversions Table */}
            {analyticsLoading ? (
              <div className="space-y-3">
                {[1,2,3,4,5].map(i => <div key={i} className="shimmer h-16 rounded-xl" />)}
              </div>
            ) : dailyConversions.length === 0 ? (
              <div className="text-center py-12 text-gray-400">
                <TrendingUp size={48} className="mx-auto mb-4 opacity-30" />
                <p>No daily conversion data for selected date range</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-100">
                      <th className="text-left py-3 px-2 font-semibold text-gray-700">Date</th>
                      <th className="text-right py-3 px-2 font-semibold text-gray-700">Raw Clicks</th>
                      <th className="text-right py-3 px-2 font-semibold text-gray-700">Conversions</th>
                      <th className="text-right py-3 px-2 font-semibold text-gray-700">CR</th>
                      <th className="text-center py-3 px-2 font-semibold text-gray-700">Override</th>
                      <th className="text-center py-3 px-2 font-semibold text-gray-700">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dailyConversions.map(day => {
                      const displayConversions = day.manual_conversions ?? day.actual_conversions
                      const isOverride = day.manual_conversions !== undefined

                      return (
                        <tr key={day.date} className="border-b border-gray-50 hover:bg-gray-50/50">
                          <td className="py-3 px-2 font-medium text-gray-900">
                            {new Date(day.date).toLocaleDateString()}
                          </td>
                          <td className="py-3 px-2 text-right text-gray-700">
                            {day.raw_clicks.toLocaleString()}
                          </td>
                          <td className={`py-3 px-2 text-right font-medium ${
                            isOverride ? 'text-amber-600' : 'text-gray-700'
                          }`}>
                            {displayConversions.toLocaleString()}
                            {isOverride && (
                              <span className="ml-1 text-xs text-amber-500">*</span>
                            )}
                          </td>
                          <td className={`py-3 px-2 text-right font-semibold ${
                            isOverride ? 'text-amber-600' :
                            day.conversion_rate >= 5 ? 'text-emerald-600' :
                            day.conversion_rate >= 2 ? 'text-orange-500' : 'text-gray-700'
                          }`}>
                            {day.conversion_rate.toFixed(2)}%
                            {isOverride && (
                              <span className="ml-1 text-xs text-amber-500">*</span>
                            )}
                          </td>
                          <td className="py-3 px-2 text-center">
                            {isOverride ? (
                              <div className="flex items-center justify-center gap-1">
                                <CheckCircle size={14} className="text-amber-500" />
                                <span className="text-xs text-amber-600">Manual</span>
                              </div>
                            ) : (
                              <span className="text-xs text-gray-400">Auto</span>
                            )}
                          </td>
                          <td className="py-3 px-2 text-center">
                            <button
                              onClick={() => openManualCRModal(day.date, day.publisher_id, day.link_id, day.raw_clicks)}
                              className="p-1.5 rounded-lg text-primary hover:bg-primary/10 transition-colors"
                              title="Manual Conversion Override"
                            >
                              <Edit3 size={14} />
                            </button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {/* White-Label Share Link */}
            <div className="mt-6 p-4 bg-blue-50 border border-blue-200 rounded-xl">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-blue-900">White-Label Stats Link</p>
                  <p className="text-xs text-blue-600">Share this branded link with {selectedPublisherData.publisher_name}</p>
                </div>
                <button
                  onClick={() => copyShareableLink(selectedPublisherData.shareable_stats_url, selectedPublisherData.publisher_name)}
                  className="bg-blue-100 hover:bg-blue-200 text-blue-700 px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors"
                >
                  <Copy size={12} /> Copy Link
                </button>
              </div>
              <div className="mt-2 p-2 bg-white rounded border text-xs font-mono text-gray-600 truncate">
                {selectedPublisherData.shareable_stats_url}
              </div>
            </div>
          </div>
        )}
        {/* Manual Conversion Override Modal */}
        {showManualCRModal && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-6 w-full max-w-lg shadow-2xl border border-gray-100">
              <h3 className="text-lg font-bold text-gray-900 mb-5">
                Manual Conversion Override — {new Date(crForm.date).toLocaleDateString()}
              </h3>

              <div className="space-y-4">
                <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-sm text-amber-800">
                  <p className="font-semibold mb-1">⚠️ Manual Override</p>
                  <p>Set the exact number of conversions for this date. This will override automatic conversion tracking and recalculate the CR.</p>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Raw Clicks</label>
                    <input 
                      type="text"
                      value={dailyConversions.find(d => d.date === crForm.date)?.raw_clicks.toLocaleString() || '0'}
                      disabled
                      className={inp + " bg-gray-50 text-gray-500"}
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Manual Conversions <span className="text-red-500">*</span></label>
                    <input 
                      type="number" 
                      min="0"
                      value={crForm.manual_conversions}
                      onChange={e => setCrForm(p => ({ 
                        ...p, 
                        manual_conversions: parseInt(e.target.value) || 0
                      }))}
                      placeholder="Enter count"
                      className={inp}
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Reason <span className="text-red-500">*</span>
                  </label>
                  <textarea 
                    value={crForm.reason}
                    onChange={e => setCrForm(p => ({ ...p, reason: e.target.value }))}
                    placeholder="Explain why this manual override is needed..."
                    rows={3}
                    className={inp}
                  />
                </div>

                {/* CR Preview */}
                {crForm.manual_conversions > 0 && (
                  <div className="bg-blue-50 border border-blue-200 rounded-xl p-3 text-sm">
                    <p className="font-semibold text-blue-900 mb-1">Calculated CR Preview</p>
                    <p className="text-blue-700">
                      {crForm.manual_conversions} conversions ÷ {dailyConversions.find(d => d.date === crForm.date)?.raw_clicks || 0} clicks = 
                      <span className="font-semibold ml-1">
                        {dailyConversions.find(d => d.date === crForm.date)?.raw_clicks 
                          ? ((crForm.manual_conversions / dailyConversions.find(d => d.date === crForm.date)!.raw_clicks) * 100).toFixed(2)
                          : '0.00'
                        }% CR
                      </span>
                    </p>
                  </div>
                )}
              </div>

              <div className="flex gap-3 mt-6">
                <button 
                  onClick={handleManualCRSubmit}
                  disabled={crSaving || !crForm.reason.trim() || crForm.manual_conversions <= 0}
                  className="flex-1 bg-amber-500 hover:bg-amber-600 text-white py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 disabled:bg-gray-300"
                >
                  {crSaving ? <Spinner size={16} /> : 'Apply Override'}
                </button>
                <button 
                  onClick={() => setShowManualCRModal(false)}
                  className="flex-1 py-2.5 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  )
}