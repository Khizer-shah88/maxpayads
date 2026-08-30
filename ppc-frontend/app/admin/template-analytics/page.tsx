'use client'

import { useState, useEffect, useCallback } from 'react'
import {
  BarChart3, TrendingUp, TrendingDown, Calendar, Edit3,
  Target, MousePointer, Users, Percent, CheckCircle, XCircle,
} from 'lucide-react'
import { toast } from 'sonner'
import Sidebar from '@/components/shared/Sidebar'
import { StatusBadge } from '@/components/ui/badge'
import { Spinner } from '@/components/ui/loading'
import { templateAnalyticsApi, prlanderTemplateApi } from '@/lib/api'
import { useAuth } from '@/lib/hooks/useAuth'

// ─── Types ────────────────────────────────────────────────────────────────────

interface TemplateOverview {
  template_id: string
  template_name: string
  template_status: string
  os_type: string
  total_clicks_30d: number
  total_conversions_30d: number
  conversion_rate_30d: number
}

interface DailyAnalytics {
  id: string
  template_id: string
  date: string
  total_clicks: number
  unique_clicks: number
  valid_clicks: number
  invalid_clicks: number
  fraud_clicks: number
  total_conversions: number
  conversion_rate: number
  manual_cr_override?: number
  manual_conversions_override?: number
  override_reason?: string
  override_updated_at?: string
  override_updated_by?: string
  geo_stats: Record<string, number>
  device_stats: Record<string, number>
  created_at: string
  updated_at: string
}

interface ManualCRForm {
  template_id: string
  date: string
  manual_conversions?: number
  manual_cr?: number
  reason: string
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function TemplateAnalyticsPage() {
  const { initialize } = useAuth()
  const [templates, setTemplates] = useState<TemplateOverview[]>([])
  const [selectedTemplate, setSelectedTemplate] = useState<string>('')
  const [dailyData, setDailyData] = useState<DailyAnalytics[]>([])
  const [loading, setLoading] = useState(true)
  const [analyticsLoading, setAnalyticsLoading] = useState(false)
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [showManualCRModal, setShowManualCRModal] = useState(false)
  const [crForm, setCrForm] = useState<ManualCRForm>({
    template_id: '',
    date: '',
    manual_conversions: undefined,
    manual_cr: undefined,
    reason: '',
  })
  const [crSaving, setCrSaving] = useState(false)

  useEffect(() => { initialize() }, [])

  // Set default date range (last 30 days)
  useEffect(() => {
    const today = new Date()
    const thirtyDaysAgo = new Date(today)
    thirtyDaysAgo.setDate(today.getDate() - 30)
    
    setDateTo(today.toISOString().split('T')[0])
    setDateFrom(thirtyDaysAgo.toISOString().split('T')[0])
  }, [])

  const loadTemplatesOverview = useCallback(async () => {
    setLoading(true)
    try {
      const res = await templateAnalyticsApi.getOverview()
      setTemplates(res.data?.templates ?? [])
      
      // Auto-select first template if none selected
      if (!selectedTemplate && res.data?.templates?.length > 0) {
        setSelectedTemplate(res.data.templates[0].template_id)
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to load templates overview')
    } finally {
      setLoading(false)
    }
  }, [selectedTemplate])

  const loadDailyAnalytics = useCallback(async () => {
    if (!selectedTemplate) return
    
    setAnalyticsLoading(true)
    try {
      const params: any = {}
      if (dateFrom) params.date_from = dateFrom
      if (dateTo) params.date_to = dateTo
      
      const res = await templateAnalyticsApi.getDailyAnalytics(selectedTemplate, params)
      setDailyData(res.data ?? [])
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to load analytics')
    } finally {
      setAnalyticsLoading(false)
    }
  }, [selectedTemplate, dateFrom, dateTo])

  useEffect(() => {
    loadTemplatesOverview()
  }, [loadTemplatesOverview])

  useEffect(() => {
    loadDailyAnalytics()
  }, [loadDailyAnalytics])

  const openManualCRModal = (date: string) => {
    const template = templates.find(t => t.template_id === selectedTemplate)
    setCrForm({
      template_id: selectedTemplate,
      date,
      manual_conversions: undefined,
      manual_cr: undefined,
      reason: '',
    })
    setShowManualCRModal(true)
  }

  const handleManualCRSubmit = async () => {
    if (!crForm.reason.trim()) {
      toast.error('Please provide a reason for the manual override')
      return
    }
    
    if (!crForm.manual_conversions && !crForm.manual_cr) {
      toast.error('Please set either manual conversions or manual CR')
      return
    }

    setCrSaving(true)
    try {
      await templateAnalyticsApi.updateManualCR(crForm.template_id, crForm)
      toast.success('Manual CR override applied successfully')
      setShowManualCRModal(false)
      loadDailyAnalytics() // Refresh data
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to update manual CR')
    } finally {
      setCrSaving(false)
    }
  }

  const handleRemoveOverride = async (date: string) => {
    if (!selectedTemplate) return
    
    try {
      await templateAnalyticsApi.removeManualCROverride(selectedTemplate, date)
      toast.success('Manual CR override removed')
      loadDailyAnalytics() // Refresh data
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to remove override')
    }
  }

  const selectedTemplateData = templates.find(t => t.template_id === selectedTemplate)

  const inp = "w-full px-3 py-2 border border-gray-200 rounded-xl text-gray-700 focus:outline-none focus:ring-2 focus:ring-primary/30 text-sm"

  return (
    <div className="flex min-h-screen bg-[#f8f9fb]">
      <Sidebar />
      <div className="flex-1 lg:ml-64 p-6 lg:p-8">

        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6 pt-12 lg:pt-0">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Template Analytics</h1>
            <p className="text-gray-400 text-sm mt-0.5">
              Track performance metrics and manually adjust conversion rates for prelander templates
            </p>
          </div>
        </div>

        {/* Template Overview Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4 mb-6">
          {loading ? (
            [1,2,3,4].map(i => <div key={i} className="shimmer h-32 rounded-2xl" />)
          ) : templates.length === 0 ? (
            <div className="col-span-full text-center py-12 text-gray-400">
              <BarChart3 size={48} className="mx-auto mb-4 opacity-30" />
              <p>No template analytics available yet</p>
            </div>
          ) : (
            templates.slice(0, 4).map(template => (
              <div 
                key={template.template_id}
                onClick={() => setSelectedTemplate(template.template_id)}
                className={`bg-white rounded-2xl border p-5 cursor-pointer transition-all hover:shadow-md ${
                  selectedTemplate === template.template_id ? 'border-primary shadow-md ring-2 ring-primary/20' : 'border-gray-100'
                }`}
              >
                <div className="flex items-start justify-between mb-3">
                  <h3 className="font-semibold text-gray-900 text-sm truncate flex-1">
                    {template.template_name}
                  </h3>
                  <StatusBadge status={template.template_status} />
                </div>
                
                <div className="space-y-2 text-xs">
                  <div className="flex justify-between">
                    <span className="text-gray-400">Clicks (30d)</span>
                    <span className="font-semibold text-gray-700">{template.total_clicks_30d.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">Conversions</span>
                    <span className="font-semibold text-gray-700">{template.total_conversions_30d.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-400">CR</span>
                    <span className={`font-semibold ${
                      template.conversion_rate_30d >= 5 ? 'text-emerald-600' :
                      template.conversion_rate_30d >= 2 ? 'text-amber-600' : 'text-gray-700'
                    }`}>
                      {template.conversion_rate_30d.toFixed(2)}%
                    </span>
                  </div>
                </div>
                
                <div className="mt-3 pt-2 border-t border-gray-100 text-xs text-gray-400">
                  OS: {template.os_type}
                </div>
              </div>
            ))
          )}
        </div>

        {/* Selected Template Details */}
        {selectedTemplateData && (
          <div className="bg-white rounded-2xl border border-gray-100 p-6 mb-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-lg font-bold text-gray-900">{selectedTemplateData.template_name}</h2>
                <p className="text-sm text-gray-400">Template Performance Analytics</p>
              </div>
              <div className="flex items-center gap-3">
                <select 
                  value={selectedTemplate} 
                  onChange={e => setSelectedTemplate(e.target.value)}
                  className={inp}
                >
                  {templates.map(t => (
                    <option key={t.template_id} value={t.template_id}>{t.template_name}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* Date Range Filters */}
            <div className="flex gap-3 items-center mb-4">
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
                {dailyData.length} day{dailyData.length !== 1 ? 's' : ''}
              </span>
            </div>

            {/* Daily Analytics Table */}
            {analyticsLoading ? (
              <div className="space-y-3">
                {[1,2,3,4,5].map(i => <div key={i} className="shimmer h-16 rounded-xl" />)}
              </div>
            ) : dailyData.length === 0 ? (
              <div className="text-center py-12 text-gray-400">
                <Target size={48} className="mx-auto mb-4 opacity-30" />
                <p>No analytics data for selected date range</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-100">
                      <th className="text-left py-3 px-2 font-semibold text-gray-700">Date</th>
                      <th className="text-right py-3 px-2 font-semibold text-gray-700">Clicks</th>
                      <th className="text-right py-3 px-2 font-semibold text-gray-700">Valid</th>
                      <th className="text-right py-3 px-2 font-semibold text-gray-700">Invalid</th>
                      <th className="text-right py-3 px-2 font-semibold text-gray-700">Conversions</th>
                      <th className="text-right py-3 px-2 font-semibold text-gray-700">CR</th>
                      <th className="text-center py-3 px-2 font-semibold text-gray-700">Override</th>
                      <th className="text-center py-3 px-2 font-semibold text-gray-700">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dailyData.map(day => {
                      const hasOverride = day.manual_cr_override !== null || day.manual_conversions_override !== null
                      const displayCR = hasOverride 
                        ? (day.manual_cr_override ?? day.conversion_rate)
                        : day.conversion_rate
                      const displayConversions = hasOverride 
                        ? (day.manual_conversions_override ?? day.total_conversions)
                        : day.total_conversions

                      return (
                        <tr key={day.id} className="border-b border-gray-50 hover:bg-gray-50/50">
                          <td className="py-3 px-2 font-medium text-gray-900">
                            {new Date(day.date).toLocaleDateString()}
                          </td>
                          <td className="py-3 px-2 text-right text-gray-700">
                            {day.total_clicks.toLocaleString()}
                          </td>
                          <td className="py-3 px-2 text-right text-emerald-600">
                            {day.valid_clicks.toLocaleString()}
                          </td>
                          <td className="py-3 px-2 text-right text-red-500">
                            {day.invalid_clicks.toLocaleString()}
                          </td>
                          <td className={`py-3 px-2 text-right font-medium ${
                            hasOverride ? 'text-amber-600' : 'text-gray-700'
                          }`}>
                            {displayConversions.toLocaleString()}
                            {hasOverride && (
                              <span className="ml-1 text-xs text-amber-500">*</span>
                            )}
                          </td>
                          <td className={`py-3 px-2 text-right font-semibold ${
                            hasOverride ? 'text-amber-600' :
                            displayCR >= 5 ? 'text-emerald-600' :
                            displayCR >= 2 ? 'text-orange-500' : 'text-gray-700'
                          }`}>
                            {displayCR.toFixed(2)}%
                            {hasOverride && (
                              <span className="ml-1 text-xs text-amber-500">*</span>
                            )}
                          </td>
                          <td className="py-3 px-2 text-center">
                            {hasOverride ? (
                              <div className="flex items-center justify-center gap-1">
                                <CheckCircle size={14} className="text-amber-500" />
                                <span className="text-xs text-amber-600">Manual</span>
                              </div>
                            ) : (
                              <span className="text-xs text-gray-400">Auto</span>
                            )}
                          </td>
                          <td className="py-3 px-2 text-center">
                            <div className="flex items-center justify-center gap-1">
                              <button
                                onClick={() => openManualCRModal(day.date)}
                                className="p-1.5 rounded-lg text-primary hover:bg-primary/10 transition-colors"
                                title="Manual CR Override"
                              >
                                <Edit3 size={14} />
                              </button>
                              {hasOverride && (
                                <button
                                  onClick={() => handleRemoveOverride(day.date)}
                                  className="p-1.5 rounded-lg text-red-500 hover:bg-red-50 transition-colors"
                                  title="Remove Override"
                                >
                                  <XCircle size={14} />
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* Manual CR Override Modal */}
        {showManualCRModal && (
          <div className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-6 w-full max-w-lg shadow-2xl border border-gray-100">
              <h3 className="text-lg font-bold text-gray-900 mb-5">
                Manual CR Override — {new Date(crForm.date).toLocaleDateString()}
              </h3>

              <div className="space-y-4">
                <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-sm text-amber-800">
                  <p className="font-semibold mb-1">⚠️ Manual Override</p>
                  <p>This will override the automatic conversion calculation for this specific date. Use carefully and document the reason.</p>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Manual Conversions</label>
                    <input 
                      type="number" 
                      min="0"
                      value={crForm.manual_conversions ?? ''}
                      onChange={e => setCrForm(p => ({ 
                        ...p, 
                        manual_conversions: e.target.value ? parseInt(e.target.value) : undefined 
                      }))}
                      placeholder="Enter count"
                      className={inp}
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Manual CR %</label>
                    <input 
                      type="number" 
                      step="0.01"
                      min="0"
                      max="100"
                      value={crForm.manual_cr ?? ''}
                      onChange={e => setCrForm(p => ({ 
                        ...p, 
                        manual_cr: e.target.value ? parseFloat(e.target.value) : undefined 
                      }))}
                      placeholder="Enter %"
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

                <p className="text-xs text-gray-400">
                  Note: You can set either manual conversions OR manual CR percentage. If both are set, conversions takes priority.
                </p>
              </div>

              <div className="flex gap-3 mt-6">
                <button 
                  onClick={handleManualCRSubmit}
                  disabled={crSaving || !crForm.reason.trim()}
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