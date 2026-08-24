'use client'

import { useState, useEffect, useRef, useMemo } from 'react'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  ArcElement,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js'
import { Bar, Doughnut } from 'react-chartjs-2'
import flatpickr from 'flatpickr'
import 'flatpickr/dist/flatpickr.min.css'
import {
  BarChart3,
  MousePointer,
  Smartphone,
  Calendar,
  Download,
  Trash2,
  Globe,
  Monitor,
  Tablet,
  ChevronDown,
} from 'lucide-react'

ChartJS.register(
  CategoryScale, LinearScale, BarElement, ArcElement,
  PointElement, LineElement, Title, Tooltip, Legend, Filler
)

// Country flag helper
const countryFlags: Record<string, string> = {
  PK: '🇵🇰', US: '🇺🇸', IN: '🇮🇳', GB: '🇬🇧', DE: '🇩🇪',
  FR: '🇫🇷', CA: '🇨🇦', AU: '🇦🇺', BD: '🇧🇩', TR: '🇹🇷',
  BR: '🇧🇷', SA: '🇸🇦', AE: '🇦🇪', EG: '🇪🇬', ID: '🇮🇩',
  NG: '🇳🇬', JP: '🇯🇵', KR: '🇰🇷', RU: '🇷🇺', MX: '🇲🇽',
  IT: '🇮🇹', ES: '🇪🇸', NL: '🇳🇱', SE: '🇸🇪', PH: '🇵🇭',
}

// Tier classification
const tier1 = ['US', 'GB', 'CA', 'AU', 'DE', 'FR', 'NL', 'SE', 'JP', 'KR']
const tier2 = ['BR', 'MX', 'TR', 'SA', 'AE', 'IT', 'ES', 'RU', 'PH']

function classifyTier(code: string) {
  if (tier1.includes(code)) return 'Tier 1'
  if (tier2.includes(code)) return 'Tier 2'
  return 'Tier 3'
}

// Fake data generators
function generateDailyClicks() {
  const data = []
  const now = new Date()
  for (let i = 60; i >= 0; i--) {
    const d = new Date(now)
    d.setDate(d.getDate() - i)
    data.push({
      date: d.toISOString().split('T')[0],
      clicks: Math.floor(Math.random() * 350) + 50,
    })
  }
  return data
}

function generateCountryData() {
  return [
    { code: 'PK', name: 'Pakistan', clicks: 342 },
    { code: 'US', name: 'United States', clicks: 289 },
    { code: 'IN', name: 'India', clicks: 245 },
    { code: 'GB', name: 'United Kingdom', clicks: 198 },
    { code: 'DE', name: 'Germany', clicks: 167 },
    { code: 'BD', name: 'Bangladesh', clicks: 143 },
    { code: 'TR', name: 'Turkey', clicks: 121 },
    { code: 'SA', name: 'Saudi Arabia', clicks: 98 },
    { code: 'FR', name: 'France', clicks: 87 },
    { code: 'CA', name: 'Canada', clicks: 76 },
  ]
}

const osData = [
  { name: 'Windows', value: 42, color: '#3B82F6' },
  { name: 'Android', value: 28, color: '#22C55E' },
  { name: 'iOS', value: 18, color: '#F97316' },
  { name: 'macOS', value: 8, color: '#8B5CF6' },
  { name: 'Linux', value: 4, color: '#EF4444' },
]

const deviceData = [
  { name: 'Desktop', value: 52, color: '#1E293B' },
  { name: 'Mobile', value: 39, color: '#22C55E' },
  { name: 'Tablet', value: 9, color: '#F97316' },
]

const fakeLogs = [
  { time: '14:32:05', ip: '182.180.XX.XX', country: 'PK', countryName: 'Pakistan', city: 'Lahore', device: 'Desktop', os: 'Windows 11', browser: 'Chrome 121', deviceId: 'dv_8a2f', canvas: '0x9e2c1f', ua: 'Mozilla/5.0 (Windows NT 10.0; Win64)' },
  { time: '14:31:58', ip: '39.40.XX.XX', country: 'PK', countryName: 'Pakistan', city: 'Karachi', device: 'Mobile', os: 'Android 14', browser: 'Chrome Mobile', deviceId: 'dv_3c7e', canvas: '0x4b8a2d', ua: 'Mozilla/5.0 (Linux; Android 14)' },
  { time: '14:31:42', ip: '72.134.XX.XX', country: 'US', countryName: 'United States', city: 'New York', device: 'Desktop', os: 'macOS 14', browser: 'Safari 17', deviceId: 'dv_1f9b', canvas: '0x7d3e5a', ua: 'Mozilla/5.0 (Macintosh; Intel)' },
  { time: '14:31:30', ip: '49.37.XX.XX', country: 'IN', countryName: 'India', city: 'Mumbai', device: 'Mobile', os: 'iOS 17', browser: 'Safari Mobile', deviceId: 'dv_5d2a', canvas: '0x1c4f8b', ua: 'Mozilla/5.0 (iPhone; CPU iPhone OS)' },
  { time: '14:31:15', ip: '85.214.XX.XX', country: 'DE', countryName: 'Germany', city: 'Berlin', device: 'Desktop', os: 'Windows 10', browser: 'Firefox 122', deviceId: 'dv_9e4c', canvas: '0x6a2d7f', ua: 'Mozilla/5.0 (Windows NT 10.0; rv:122)' },
]

export default function AnalyticsDashboard() {
  const dateRef = useRef<HTMLInputElement>(null)
  const fpRef = useRef<flatpickr.Instance | null>(null)
  const [dateRange, setDateRange] = useState('')
  const [mode, setMode] = useState('unique_device')
  const [showBots, setShowBots] = useState(false)
  const [uniqueOnly, setUniqueOnly] = useState(true)

  const dailyClicks = useMemo(() => generateDailyClicks(), [])
  const countryData = useMemo(() => generateCountryData(), [])
  const totalLogs = useMemo(() => dailyClicks.reduce((s, d) => s + d.clicks, 0), [dailyClicks])

  useEffect(() => {
    if (!dateRef.current) return
    const today = new Date()
    const thirtyAgo = new Date()
    thirtyAgo.setDate(thirtyAgo.getDate() - 30)

    fpRef.current = flatpickr(dateRef.current, {
      mode: 'range',
      dateFormat: 'Y-m-d',
      defaultDate: [thirtyAgo, today],
      onChange: (dates) => {
        if (dates.length === 2) {
          setDateRange(`${dates[0].toISOString().split('T')[0]} to ${dates[1].toISOString().split('T')[0]}`)
        }
      },
    })
    setDateRange(`${thirtyAgo.toISOString().split('T')[0]} to ${today.toISOString().split('T')[0]}`)

    return () => { fpRef.current?.destroy() }
  }, [])

  // Bar chart data
  const barChartData = {
    labels: dailyClicks.map(d => d.date.slice(5)),
    datasets: [{
      label: 'Daily Clicks',
      data: dailyClicks.map(d => d.clicks),
      backgroundColor: '#3B82F6',
      borderRadius: 3,
      barPercentage: 0.7,
    }],
  }

  const barOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: '#fff', borderColor: '#E5E7EB', borderWidth: 1,
        titleColor: '#000', bodyColor: '#374151', padding: 10,
      },
    },
    scales: {
      x: { grid: { display: false }, ticks: { color: '#9CA3AF', font: { size: 10 }, maxTicksLimit: 15 } },
      y: { grid: { color: '#F3F4F6' }, ticks: { color: '#9CA3AF', font: { size: 11 } } },
    },
  }

  // Doughnut data
  const osDoughnut = {
    labels: osData.map(d => d.name),
    datasets: [{
      data: osData.map(d => d.value),
      backgroundColor: osData.map(d => d.color),
      borderWidth: 0,
      cutout: '65%',
    }],
  }

  const deviceDoughnut = {
    labels: deviceData.map(d => d.name),
    datasets: [{
      data: deviceData.map(d => d.value),
      backgroundColor: deviceData.map(d => d.color),
      borderWidth: 0,
      cutout: '65%',
    }],
  }

  const doughnutOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'bottom' as const,
        labels: { color: '#374151', font: { size: 11 }, boxWidth: 12, padding: 12 },
      },
    },
  }

  // Country bar chart
  const countryBarData = {
    labels: countryData.map(c => `${countryFlags[c.code] || '🏳️'} ${c.name}`),
    datasets: [{
      data: countryData.map(c => c.clicks),
      backgroundColor: '#DC2626',
      borderRadius: 4,
      barPercentage: 0.6,
    }],
  }

  const countryBarOptions = {
    indexAxis: 'y' as const,
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: '#fff', borderColor: '#E5E7EB', borderWidth: 1,
        titleColor: '#000', bodyColor: '#374151', padding: 10,
      },
    },
    scales: {
      x: { grid: { color: '#F3F4F6' }, ticks: { color: '#9CA3AF' } },
      y: { grid: { display: false }, ticks: { color: '#374151', font: { size: 12 } } },
    },
  }

  // Tier stats
  const totalCountryClicks = countryData.reduce((s, c) => s + c.clicks, 0)
  const tierStats = [
    { tier: 'Tier 1', count: countryData.filter(c => classifyTier(c.code) === 'Tier 1').reduce((s, c) => s + c.clicks, 0) },
    { tier: 'Tier 2', count: countryData.filter(c => classifyTier(c.code) === 'Tier 2').reduce((s, c) => s + c.clicks, 0) },
    { tier: 'Tier 3', count: countryData.filter(c => classifyTier(c.code) === 'Tier 3').reduce((s, c) => s + c.clicks, 0) },
  ]

  const handleExport = () => {
    const rows = [['Date', 'Clicks'], ...dailyClicks.map(d => [d.date, String(d.clicks)])]
    const csv = rows.map(r => r.join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = 'analytics_export.csv'; a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div>
            <h2 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <BarChart3 className="text-red-600" size={28} />
              Download Analytics
            </h2>
            <p className="text-gray-500 text-sm mt-1">Detailed traffic analysis, device breakdown, and geographic distribution</p>
          </div>
          <div className="text-sm text-gray-500">
            Logs: <span className="font-semibold text-gray-900">{totalLogs.toLocaleString()}</span>
          </div>
        </div>
      </div>

      {/* Controls */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
          {/* Date Range */}
          <div className="relative">
            <label className="block text-xs font-medium text-gray-500 mb-1.5">Date Range</label>
            <div className="relative">
              <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={16} />
              <input
                ref={dateRef}
                type="text"
                placeholder="Select date range"
                className="w-full pl-10 pr-4 py-2.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-red-500 focus:border-red-500 bg-white"
                readOnly
              />
            </div>
          </div>

          {/* Mode */}
          <div className="relative">
            <label className="block text-xs font-medium text-gray-500 mb-1.5">Mode</label>
            <div className="relative">
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value)}
                className="w-full px-4 py-2.5 border border-gray-300 rounded-lg text-sm appearance-none focus:ring-2 focus:ring-red-500 focus:border-red-500 bg-white pr-10"
              >
                <option value="unique_device">Unique per device/day</option>
                <option value="unique_ip">Unique per IP/day</option>
                <option value="all">All clicks</option>
              </select>
              <ChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" size={16} />
            </div>
          </div>

          {/* Buttons */}
          <div className="flex items-end gap-2">
            <button
              onClick={handleExport}
              className="flex items-center gap-2 px-5 py-2.5 bg-blue-900 text-white rounded-lg text-sm font-medium hover:bg-blue-800 transition-colors"
            >
              <Download size={16} /> Export CSV
            </button>
            <button
              onClick={() => fpRef.current?.clear()}
              className="flex items-center gap-2 px-5 py-2.5 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700 transition-colors"
            >
              <Trash2 size={16} /> Clear
            </button>
          </div>
        </div>

        {/* Quick filters */}
        <div className="flex flex-wrap gap-4 pt-2 border-t border-gray-100">
          <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
            <input type="checkbox" checked={uniqueOnly} onChange={(e) => setUniqueOnly(e.target.checked)}
              className="w-4 h-4 rounded border-gray-300 text-red-600 focus:ring-red-500" />
            Unique clicks only
          </label>
          <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
            <input type="checkbox" checked={showBots} onChange={(e) => setShowBots(e.target.checked)}
              className="w-4 h-4 rounded border-gray-300 text-red-600 focus:ring-red-500" />
            Include bots
          </label>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: 'Total Clicks', value: totalLogs.toLocaleString(), icon: <MousePointer size={20} />, color: 'bg-blue-50 text-blue-600' },
          { label: 'Unique Devices', value: Math.floor(totalLogs * 0.72).toLocaleString(), icon: <Smartphone size={20} />, color: 'bg-green-50 text-green-600' },
          { label: "Today's Clicks", value: (dailyClicks[dailyClicks.length - 1]?.clicks ?? 0).toLocaleString(), icon: <BarChart3 size={20} />, color: 'bg-orange-50 text-orange-600' },
          { label: 'This Month', value: dailyClicks.slice(-30).reduce((s, d) => s + d.clicks, 0).toLocaleString(), icon: <Calendar size={20} />, color: 'bg-purple-50 text-purple-600' },
        ].map((kpi, i) => (
          <div key={i} className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm hover:shadow-md transition-shadow">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">{kpi.label}</span>
              <div className={`p-2 rounded-lg ${kpi.color}`}>{kpi.icon}</div>
            </div>
            <p className="text-2xl font-bold text-gray-900">{kpi.value}</p>
          </div>
        ))}
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Bar Chart */}
        <div className="lg:col-span-2 bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Daily Clicks</h3>
          <div style={{ height: '320px' }}>
            <Bar data={barChartData} options={barOptions as any} />
          </div>
        </div>

        {/* Doughnut Charts */}
        <div className="flex flex-col gap-6">
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm flex-1">
            <h3 className="text-sm font-semibold text-gray-900 mb-2">OS Distribution</h3>
            <div style={{ height: '180px' }}>
              <Doughnut data={osDoughnut} options={doughnutOptions} />
            </div>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm flex-1">
            <h3 className="text-sm font-semibold text-gray-900 mb-2">Device Type</h3>
            <div style={{ height: '180px' }}>
              <Doughnut data={deviceDoughnut} options={doughnutOptions} />
            </div>
          </div>
        </div>
      </div>

      {/* Country Breakdown */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
        <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
          <Globe className="text-red-600" size={20} /> Country Breakdown
        </h3>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Horizontal bar chart */}
          <div style={{ height: '360px' }}>
            <Bar data={countryBarData} options={countryBarOptions as any} />
          </div>

          {/* Tier stats + country list */}
          <div>
            {/* Tier Summary */}
            <div className="grid grid-cols-3 gap-3 mb-5">
              {tierStats.map((t, i) => (
                <div key={i} className={`rounded-lg p-3 text-center ${
                  i === 0 ? 'bg-green-50 border border-green-200' :
                  i === 1 ? 'bg-yellow-50 border border-yellow-200' :
                  'bg-red-50 border border-red-200'
                }`}>
                  <p className="text-xs font-medium text-gray-500">{t.tier}</p>
                  <p className="text-lg font-bold text-gray-900">{((t.count / totalCountryClicks) * 100).toFixed(1)}%</p>
                  <p className="text-xs text-gray-400">{t.count} clicks</p>
                </div>
              ))}
            </div>

            {/* Country List */}
            <div className="space-y-2">
              {countryData.map((c, i) => (
                <div key={i} className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-gray-50 transition-colors">
                  <div className="flex items-center gap-2">
                    <span className="text-lg">{countryFlags[c.code] || '🏳️'}</span>
                    <span className="text-sm font-medium text-gray-700">{c.name}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-sm font-semibold text-gray-900">{c.clicks}</span>
                    <span className="text-xs text-gray-400">{((c.clicks / totalCountryClicks) * 100).toFixed(1)}%</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Detailed Logs Table */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
        <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
          <Monitor className="text-red-600" size={20} /> Detailed Logs
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200">
                {['Time', 'IP', 'Country', 'City', 'Device', 'OS', 'Browser', 'Device ID', 'Canvas', 'UA'].map(h => (
                  <th key={h} className="text-left py-3 px-3 text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {fakeLogs.map((log, i) => (
                <tr key={i} className={`border-b border-gray-100 hover:bg-red-50/30 transition-colors ${i % 2 === 0 ? 'bg-gray-50/50' : ''}`}>
                  <td className="py-2.5 px-3 font-mono text-xs text-gray-600">{log.time}</td>
                  <td className="py-2.5 px-3 font-mono text-xs text-gray-600">{log.ip}</td>
                  <td className="py-2.5 px-3 whitespace-nowrap">
                    <span className="text-base mr-1">{countryFlags[log.country] || '🏳️'}</span>
                    <span className="text-xs text-gray-700">{log.countryName}</span>
                  </td>
                  <td className="py-2.5 px-3 text-xs text-gray-600">{log.city}</td>
                  <td className="py-2.5 px-3">
                    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
                      log.device === 'Desktop' ? 'bg-gray-100 text-gray-700' :
                      log.device === 'Mobile' ? 'bg-green-100 text-green-700' :
                      'bg-orange-100 text-orange-700'
                    }`}>
                      {log.device === 'Desktop' ? <Monitor size={11} /> : log.device === 'Mobile' ? <Smartphone size={11} /> : <Tablet size={11} />}
                      {log.device}
                    </span>
                  </td>
                  <td className="py-2.5 px-3 text-xs text-gray-600">{log.os}</td>
                  <td className="py-2.5 px-3 text-xs text-gray-600">{log.browser}</td>
                  <td className="py-2.5 px-3 font-mono text-xs text-gray-400">{log.deviceId}</td>
                  <td className="py-2.5 px-3 font-mono text-xs text-gray-400">{log.canvas}</td>
                  <td className="py-2.5 px-3 font-mono text-xs text-gray-400 max-w-[200px] truncate">{log.ua}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
