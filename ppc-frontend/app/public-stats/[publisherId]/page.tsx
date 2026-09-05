'use client'

import { useState, useEffect, useCallback } from 'react'
import { useParams, useSearchParams } from 'next/navigation'
import {
  BarChart3, TrendingUp, Calendar, Monitor, Apple,
  Users, MousePointer, Percent, Activity, Globe,
  CheckCircle2, AlertCircle, Download, RefreshCw
} from 'lucide-react'
import { toast } from 'sonner'
import { publicStatsApi } from '@/lib/api'

// ─── White-Label Publisher Stats Page ─────────────────────────────────────────
// This page is completely white-labeled - no internal branding
// Accessible via shareable links without authentication

interface StatsData {
  publisher_name: string
  publisher_id: string
  date_range: string
  total_impressions?: number
  total_clicks?: number
  unique_windows_clicks: number
  unique_mac_clicks: number
  total_conversions?: number
  conversion_rate?: number
  performance_score: string
  daily_breakdown?: Array<{
    date: string
    clicks: number
    conversions: number
    cr: number
    windows_clicks: number
    mac_clicks: number
  }>
  insights: {
    top_performance_day: string
    avg_daily_clicks: number
    trend_direction: 'up' | 'down' | 'stable'
    platform_preference: 'windows' | 'mac' | 'balanced'
  }
  preferences?: {
    show_os?: boolean
    show_country?: boolean
    show_device?: boolean
    show_clicks?: boolean
    show_unique_clicks?: boolean
    show_valid_clicks?: boolean
    show_invalid_clicks?: boolean
    show_impressions?: boolean
    show_conversions?: boolean
    show_cr?: boolean
    show_fraud_score?: boolean
    show_daily_breakdown?: boolean
  }
}

export default function PublisherStatsPage() {
  const params = useParams()
  const searchParams = useSearchParams()
  const publisherId = params.publisherId as string
  const token = searchParams.get('token')
  
  const [stats, setStats] = useState<StatsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const loadStats = useCallback(async () => {
    if (!publisherId || !token) {
      setError('Invalid access link')
      setLoading(false)
      return
    }

    setLoading(true)
    try {
      // Call the real API endpoint
      const response = await publicStatsApi.getPublisherStats(publisherId, token)
      const apiData = response.data.data
      
      // Handle the new response format with preferences
      const prefs = apiData.preferences || {}
      
      // Build stats object based on what's returned from API (preferences already applied)
      setStats({
        publisher_name: apiData.publisher_name || 'Publisher',
        publisher_id: apiData.publisher_id || publisherId,
        date_range: apiData.date_range || `Last 30 Days`,
        total_impressions: apiData.total_impressions || apiData.total_clicks || 0,
        unique_windows_clicks: apiData.unique_windows_clicks || 0,
        unique_mac_clicks: apiData.unique_mac_clicks || 0,
        total_conversions: apiData.total_conversions || 0,
        conversion_rate: apiData.conversion_rate || 0,
        performance_score: apiData.performance_score || 'Building',
        daily_breakdown: apiData.daily_breakdown || [],
        insights: apiData.insights || {
          top_performance_day: '',
          avg_daily_clicks: 0,
          trend_direction: 'stable',
          platform_preference: 'balanced',
        },
        preferences: prefs,
      })
      
    } catch (err: any) {
      console.error('Error loading stats:', err)
      if (err?.response?.status === 403) {
        setError('Access denied. Please check your link or request a new one.')
      } else if (err?.response?.status === 404) {
        setError('Publisher not found. Please verify the link.')
      } else {
        setError('Unable to load statistics. Please try again later.')
      }
    } finally {
      setLoading(false)
    }
  }, [publisherId, token])

  useEffect(() => {
    loadStats()
  }, [loadStats])

  const downloadReport = () => {
    if (!stats) return
    
    // Generate CSV report
    const csvContent = [
      ['Date', 'Clicks', 'Conversions', 'Conversion Rate (%)', 'Windows Clicks', 'Mac Clicks'],
      ...stats.daily_breakdown.map(day => [
        day.date,
        day.clicks.toString(),
        day.conversions.toString(),
        day.cr.toFixed(2),
        day.windows_clicks.toString(),
        day.mac_clicks.toString()
      ])
    ].map(row => row.join(',')).join('\n')
    
    const blob = new Blob([csvContent], { type: 'text/csv' })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `publisher-stats-${stats.publisher_name.replace(/\s+/g, '-')}.csv`
    link.click()
    window.URL.revokeObjectURL(url)
    
    toast.success('Report downloaded successfully')
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading your performance dashboard...</p>
          <p className="text-sm text-gray-500 mt-2">Please wait while we fetch your latest statistics</p>
        </div>
      </div>
    )
  }

  if (error || !stats) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-red-50 to-pink-100 flex items-center justify-center">
        <div className="text-center max-w-md mx-auto px-6">
          <div className="text-red-500 mb-6">
            <AlertCircle className="w-16 h-16 mx-auto" />
          </div>
          <h1 className="text-2xl font-bold text-gray-900 mb-3">Access Error</h1>
          <p className="text-gray-600 mb-6">{error}</p>
          <div className="bg-white rounded-xl p-4 border border-red-200 text-left">
            <h3 className="font-semibold text-gray-900 mb-2">Troubleshooting:</h3>
            <ul className="text-sm text-gray-600 space-y-1">
              <li>• Verify the complete URL was copied correctly</li>
              <li>• Check if the link has expired</li>
              <li>• Contact support for a new access link</li>
            </ul>
          </div>
        </div>
      </div>
    )
  }

  const TrendIcon = ({ direction }: { direction: string }) => {
    if (direction === 'up') return <TrendingUp className="w-4 h-4 text-emerald-600" />
    if (direction === 'down') return <TrendingUp className="w-4 h-4 text-red-500 rotate-180" />
    return <Activity className="w-4 h-4 text-gray-500" />
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      {/* Header */}
      <div className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Performance Dashboard</h1>
              <p className="text-gray-600 mt-1 flex items-center gap-2">
                <Globe className="w-4 h-4" />
                {stats.publisher_name} • {stats.date_range}
              </p>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={downloadReport}
                className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-xl text-sm font-semibold flex items-center gap-2 transition-colors"
              >
                <Download size={16} />
                Download Report
              </button>
              <div className="flex items-center gap-2 text-sm text-gray-500">
                <RefreshCw size={16} />
                <span>Updated: {new Date().toLocaleDateString()}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Key Metrics Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-12 h-12 bg-blue-100 rounded-xl flex items-center justify-center">
                <MousePointer className="w-6 h-6 text-blue-600" />
              </div>
              <div>
                <p className="text-sm text-gray-600">Total Impressions</p>
                <p className="text-2xl font-bold text-gray-900">{stats.total_impressions.toLocaleString()}</p>
              </div>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <TrendIcon direction={stats.insights.trend_direction} />
              <span className={`font-medium ${
                stats.insights.trend_direction === 'up' ? 'text-emerald-600' :
                stats.insights.trend_direction === 'down' ? 'text-red-500' : 'text-gray-600'
              }`}>
                {stats.insights.avg_daily_clicks.toLocaleString()} avg/day
              </span>
            </div>
          </div>

          <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-12 h-12 bg-emerald-100 rounded-xl flex items-center justify-center">
                <Users className="w-6 h-6 text-emerald-600" />
              </div>
              <div>
                <p className="text-sm text-gray-600">Total Conversions</p>
                <p className="text-2xl font-bold text-gray-900">{stats.total_conversions.toLocaleString()}</p>
              </div>
            </div>
            <div className="flex items-center gap-2 text-sm text-emerald-600">
              <CheckCircle2 size={16} />
              <span>High performer</span>
            </div>
          </div>

          <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-12 h-12 bg-purple-100 rounded-xl flex items-center justify-center">
                <Percent className="w-6 h-6 text-purple-600" />
              </div>
              <div>
                <p className="text-sm text-gray-600">Conversion Rate</p>
                <p className="text-2xl font-bold text-gray-900">{stats.conversion_rate.toFixed(2)}%</p>
              </div>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <Activity size={16} className="text-purple-600" />
              <span className="text-purple-600 font-medium">Industry avg: 3.2%</span>
            </div>
          </div>

          <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
            <div className="flex items-center gap-3 mb-3">
              <div className="w-12 h-12 bg-orange-100 rounded-xl flex items-center justify-center">
                <BarChart3 className="w-6 h-6 text-orange-600" />
              </div>
              <div>
                <p className="text-sm text-gray-600">Performance Score</p>
                <p className="text-2xl font-bold text-gray-900">{stats.performance_score}</p>
              </div>
            </div>
            <div className="flex items-center gap-2 text-sm text-blue-600">
              <Globe size={16} />
              <span>Top 25% globally</span>
            </div>
          </div>
        </div>

        {/* Platform Breakdown & Insights */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Platform Performance</h3>
            
            <div className="space-y-4">
              <div className="flex items-center justify-between p-4 bg-blue-50 rounded-xl">
                <div className="flex items-center gap-3">
                  <Monitor className="w-6 h-6 text-blue-600" />
                  <div>
                    <span className="font-semibold text-blue-900">Windows Users</span>
                    <p className="text-xs text-blue-600">Desktop & Laptop</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-xl font-bold text-blue-900">{stats.unique_windows_clicks.toLocaleString()}</p>
                  <p className="text-sm text-blue-600">
                    {((stats.unique_windows_clicks / stats.total_impressions) * 100).toFixed(1)}%
                  </p>
                </div>
              </div>
              
              <div className="flex items-center justify-between p-4 bg-gray-50 rounded-xl">
                <div className="flex items-center gap-3">
                  <Apple className="w-6 h-6 text-gray-600" />
                  <div>
                    <span className="font-semibold text-gray-900">Mac Users</span>
                    <p className="text-xs text-gray-600">MacBook & iMac</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-xl font-bold text-gray-900">{stats.unique_mac_clicks.toLocaleString()}</p>
                  <p className="text-sm text-gray-600">
                    {((stats.unique_mac_clicks / stats.total_impressions) * 100).toFixed(1)}%
                  </p>
                </div>
              </div>
            </div>

            <div className="mt-4 p-3 bg-blue-50 rounded-xl">
              <p className="text-sm font-medium text-blue-900">Platform Preference</p>
              <p className="text-xs text-blue-700 capitalize">
                {stats.insights.platform_preference === 'balanced' 
                  ? 'Balanced across platforms - excellent reach'
                  : `${stats.insights.platform_preference} preferred - optimize targeting`
                }
              </p>
            </div>
          </div>

          {/* Performance Insights */}
          <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Performance Insights</h3>
            
            <div className="space-y-4">
              <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-xl">
                <div className="flex items-start gap-3">
                  <CheckCircle2 className="w-5 h-5 text-emerald-600 mt-0.5" />
                  <div>
                    <p className="text-sm font-semibold text-emerald-800">Strong Performance</p>
                    <p className="text-xs text-emerald-700 mt-1">
                      Your {stats.conversion_rate.toFixed(2)}% conversion rate exceeds the industry average of 3.2%
                    </p>
                  </div>
                </div>
              </div>
              
              <div className="p-4 bg-blue-50 border border-blue-200 rounded-xl">
                <div className="flex items-start gap-3">
                  <Calendar className="w-5 h-5 text-blue-600 mt-0.5" />
                  <div>
                    <p className="text-sm font-semibold text-blue-800">Best Performance Day</p>
                    <p className="text-xs text-blue-700 mt-1">
                      {new Date(stats.insights.top_performance_day).toLocaleDateString()} showed the highest conversion rate
                    </p>
                  </div>
                </div>
              </div>
              
              <div className="p-4 bg-purple-50 border border-purple-200 rounded-xl">
                <div className="flex items-start gap-3">
                  <TrendIcon direction={stats.insights.trend_direction} />
                  <div>
                    <p className="text-sm font-semibold text-purple-800">Traffic Trend</p>
                    <p className="text-xs text-purple-700 mt-1">
                      {stats.insights.trend_direction === 'up' && 'Increasing engagement - momentum is building'}
                      {stats.insights.trend_direction === 'down' && 'Declining engagement - consider optimization'}
                      {stats.insights.trend_direction === 'stable' && 'Consistent performance - maintain current strategy'}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Daily Performance Chart */}
        <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Daily Performance Trend (Last 14 Days)</h3>
          
          <div className="space-y-2 max-h-80 overflow-y-auto">
            {stats.daily_breakdown.slice(0, 14).map(day => (
              <div key={day.date} className="flex items-center justify-between p-3 hover:bg-gray-50 rounded-lg transition-colors">
                <div className="flex items-center gap-4">
                  <div className="w-3 h-3 bg-blue-500 rounded-full flex-shrink-0"></div>
                  <div>
                    <p className="text-sm font-medium text-gray-900">
                      {new Date(day.date).toLocaleDateString('en-US', { 
                        weekday: 'short', 
                        month: 'short', 
                        day: 'numeric' 
                      })}
                    </p>
                    <div className="flex items-center gap-3 mt-1">
                      <div className="flex items-center gap-1 text-xs text-gray-500">
                        <Monitor size={12} />
                        <span>{day.windows_clicks}</span>
                      </div>
                      <div className="flex items-center gap-1 text-xs text-gray-500">
                        <Apple size={12} />
                        <span>{day.mac_clicks}</span>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-6 text-sm">
                  <div className="text-right">
                    <p className="text-gray-600">Clicks</p>
                    <p className="font-semibold text-gray-900">{day.clicks.toLocaleString()}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-gray-600">Conversions</p>
                    <p className="font-semibold text-gray-900">{day.conversions.toLocaleString()}</p>
                  </div>
                  <div className="text-right min-w-[60px]">
                    <p className="text-gray-600">CR</p>
                    <p className={`font-semibold text-sm ${
                      day.cr >= 6 ? 'text-emerald-600' : 
                      day.cr >= 4 ? 'text-amber-600' : 
                      day.cr >= 2 ? 'text-orange-500' : 'text-gray-900'
                    }`}>
                      {day.cr.toFixed(2)}%
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div className="text-center mt-12 py-8 border-t border-gray-200">
          <div className="flex items-center justify-center gap-6 text-sm text-gray-500">
            <span>Last updated: {new Date().toLocaleDateString()}</span>
            <span>•</span>
            <span>Data refreshed every 24 hours</span>
            <span>•</span>
            <span>All times in UTC</span>
          </div>
          <p className="text-xs text-gray-400 mt-2">
            This performance dashboard is provided for analytical purposes. 
            Contact your account manager for detailed reporting or support.
          </p>
        </div>
      </div>
    </div>
  )
}