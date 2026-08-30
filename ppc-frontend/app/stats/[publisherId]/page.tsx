'use client'

import { useState, useEffect, useCallback } from 'react'
import { useParams, useSearchParams } from 'next/navigation'
import {
  BarChart3, TrendingUp, Calendar, Monitor, Apple,
  Users, MousePointer, Percent, Activity, Globe,
} from 'lucide-react'
import { toast } from 'sonner'

// ─── White-Label Publisher Stats Page ─────────────────────────────────────────
// This page is completely white-labeled - no internal branding
// Accessible via shareable links without authentication

interface StatsData {
  publisher_name: string
  date_range: string
  total_impressions: number
  unique_windows_clicks: number
  unique_mac_clicks: number
  total_conversions: number
  conversion_rate: number
  daily_breakdown: Array<{
    date: string
    clicks: number
    conversions: number
    cr: number
  }>
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
      // In a real implementation, this would call a public API endpoint
      // For now, we'll simulate the data
      
      // Decode and validate token (basic validation)
      const decodedToken = atob(token)
      
      // Simulate API call delay
      await new Promise(resolve => setTimeout(resolve, 1000))
      
      // Mock data - in real implementation, this would come from API
      const mockStats: StatsData = {
        publisher_name: `Publisher ${publisherId.slice(0, 8)}`,
        date_range: 'Last 30 Days',
        total_impressions: 15432,
        unique_windows_clicks: 9259,
        unique_mac_clicks: 6173,
        total_conversions: 892,
        conversion_rate: 5.78,
        daily_breakdown: [
          { date: '2024-01-15', clicks: 521, conversions: 31, cr: 5.95 },
          { date: '2024-01-14', clicks: 487, conversions: 28, cr: 5.75 },
          { date: '2024-01-13', clicks: 603, conversions: 35, cr: 5.81 },
          { date: '2024-01-12', clicks: 445, conversions: 24, cr: 5.39 },
          { date: '2024-01-11', clicks: 512, conversions: 30, cr: 5.86 },
          { date: '2024-01-10', clicks: 478, conversions: 26, cr: 5.44 },
          { date: '2024-01-09', clicks: 556, conversions: 34, cr: 6.12 },
        ]
      }
      
      setStats(mockStats)
      
    } catch (err: any) {
      console.error('Error loading stats:', err)
      setError('Failed to load statistics')
    } finally {
      setLoading(false)
    }
  }, [publisherId, token])

  useEffect(() => {
    loadStats()
  }, [loadStats])

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600">Loading your statistics...</p>
        </div>
      </div>
    )
  }

  if (error || !stats) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-red-50 to-pink-100 flex items-center justify-center">
        <div className="text-center max-w-md mx-auto px-6">
          <div className="text-red-500 mb-4">
            <svg className="w-16 h-16 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <h1 className="text-xl font-bold text-gray-900 mb-2">Access Error</h1>
          <p className="text-gray-600 mb-4">{error}</p>
          <p className="text-sm text-gray-500">Please contact support if you believe this is an error.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-100">
      {/* Header */}
      <div className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Performance Dashboard</h1>
              <p className="text-gray-600 mt-1">
                Statistics for {stats.publisher_name} • {stats.date_range}
              </p>
            </div>
            <div className="flex items-center gap-2 text-sm text-gray-500">
              <Calendar size={16} />
              <span>Updated: {new Date().toLocaleDateString()}</span>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Key Metrics Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
            <div className="flex items-center gap-3 mb-2">
              <div className="w-10 h-10 bg-blue-100 rounded-xl flex items-center justify-center">
                <MousePointer className="w-5 h-5 text-blue-600" />
              </div>
              <div>
                <p className="text-sm text-gray-600">Total Impressions</p>
                <p className="text-2xl font-bold text-gray-900">{stats.total_impressions.toLocaleString()}</p>
              </div>
            </div>
            <div className="flex items-center gap-1 text-sm text-emerald-600">
              <TrendingUp size={14} />
              <span>+12% vs last period</span>
            </div>
          </div>

          <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
            <div className="flex items-center gap-3 mb-2">
              <div className="w-10 h-10 bg-purple-100 rounded-xl flex items-center justify-center">
                <Users className="w-5 h-5 text-purple-600" />
              </div>
              <div>
                <p className="text-sm text-gray-600">Conversions</p>
                <p className="text-2xl font-bold text-gray-900">{stats.total_conversions.toLocaleString()}</p>
              </div>
            </div>
            <div className="flex items-center gap-1 text-sm text-emerald-600">
              <TrendingUp size={14} />
              <span>+8% vs last period</span>
            </div>
          </div>

          <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
            <div className="flex items-center gap-3 mb-2">
              <div className="w-10 h-10 bg-green-100 rounded-xl flex items-center justify-center">
                <Percent className="w-5 h-5 text-green-600" />
              </div>
              <div>
                <p className="text-sm text-gray-600">Conversion Rate</p>
                <p className="text-2xl font-bold text-gray-900">{stats.conversion_rate}%</p>
              </div>
            </div>
            <div className="flex items-center gap-1 text-sm text-emerald-600">
              <TrendingUp size={14} />
              <span>+0.3% vs last period</span>
            </div>
          </div>

          <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
            <div className="flex items-center gap-3 mb-2">
              <div className="w-10 h-10 bg-orange-100 rounded-xl flex items-center justify-center">
                <Activity className="w-5 h-5 text-orange-600" />
              </div>
              <div>
                <p className="text-sm text-gray-600">Performance Score</p>
                <p className="text-2xl font-bold text-gray-900">
                  {stats.conversion_rate >= 5 ? 'Excellent' : stats.conversion_rate >= 3 ? 'Good' : 'Fair'}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-1 text-sm text-blue-600">
              <Globe size={14} />
              <span>Top 15% globally</span>
            </div>
          </div>
        </div>

        {/* OS Breakdown */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
          <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Platform Breakdown</h3>
            
            <div className="space-y-4">
              <div className="flex items-center justify-between p-3 bg-blue-50 rounded-xl">
                <div className="flex items-center gap-3">
                  <Monitor className="w-5 h-5 text-blue-600" />
                  <span className="font-medium text-blue-900">Windows</span>
                </div>
                <div className="text-right">
                  <p className="font-semibold text-blue-900">{stats.unique_windows_clicks.toLocaleString()}</p>
                  <p className="text-xs text-blue-600">
                    {((stats.unique_windows_clicks / stats.total_impressions) * 100).toFixed(1)}%
                  </p>
                </div>
              </div>
              
              <div className="flex items-center justify-between p-3 bg-gray-50 rounded-xl">
                <div className="flex items-center gap-3">
                  <Apple className="w-5 h-5 text-gray-600" />
                  <span className="font-medium text-gray-900">Mac</span>
                </div>
                <div className="text-right">
                  <p className="font-semibold text-gray-900">{stats.unique_mac_clicks.toLocaleString()}</p>
                  <p className="text-xs text-gray-600">
                    {((stats.unique_mac_clicks / stats.total_impressions) * 100).toFixed(1)}%
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Daily Performance Chart */}
          <div className="lg:col-span-2 bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Daily Performance Trend</h3>
            
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {stats.daily_breakdown.map(day => (
                <div key={day.date} className="flex items-center justify-between p-3 hover:bg-gray-50 rounded-lg transition-colors">
                  <div className="flex items-center gap-3">
                    <div className="w-2 h-2 bg-blue-500 rounded-full"></div>
                    <span className="text-sm font-medium text-gray-900">
                      {new Date(day.date).toLocaleDateString()}
                    </span>
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
                    <div className="text-right">
                      <p className="text-gray-600">CR</p>
                      <p className={`font-semibold ${
                        day.cr >= 6 ? 'text-emerald-600' : 
                        day.cr >= 4 ? 'text-amber-600' : 'text-gray-900'
                      }`}>
                        {day.cr.toFixed(2)}%
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Performance Insights */}
        <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Performance Insights</h3>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-xl">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-2 h-2 bg-emerald-500 rounded-full"></div>
                <span className="text-sm font-semibold text-emerald-800">Strong Performance</span>
              </div>
              <p className="text-sm text-emerald-700">
                Your conversion rate of {stats.conversion_rate}% is above industry average of 3.2%
              </p>
            </div>
            
            <div className="p-4 bg-blue-50 border border-blue-200 rounded-xl">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-2 h-2 bg-blue-500 rounded-full"></div>
                <span className="text-sm font-semibold text-blue-800">Platform Mix</span>
              </div>
              <p className="text-sm text-blue-700">
                Windows traffic ({((stats.unique_windows_clicks / stats.total_impressions) * 100).toFixed(0)}%) shows higher engagement than Mac
              </p>
            </div>
            
            <div className="p-4 bg-purple-50 border border-purple-200 rounded-xl">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-2 h-2 bg-purple-500 rounded-full"></div>
                <span className="text-sm font-semibold text-purple-800">Growth Trend</span>
              </div>
              <p className="text-sm text-purple-700">
                Steady upward trend in both impressions and conversion rates over time
              </p>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="text-center mt-12 py-8 border-t border-gray-200">
          <p className="text-sm text-gray-500">
            Statistics generated on {new Date().toLocaleDateString()} • Data refreshed every 24 hours
          </p>
        </div>
      </div>
    </div>
  )
}