'use client'

import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'next/navigation'
import {
  Eye, Target, Percent, BarChart2, TrendingUp, Trophy,
  CalendarDays, Monitor, Smartphone, AlertCircle, ChevronDown,
} from 'lucide-react'
import { publicStatsApi } from '@/lib/api'

// ─── Types ────────────────────────────────────────────────────────────────────

interface DayRow {
  date: string
  clicks: number
  unique_wins: number
  conversions: number
  cr: number
  windows_clicks: number
  mac_clicks: number
  android_clicks: number
}

interface PlatformChip {
  key: 'windows' | 'mac' | 'android'
  label: string
  value: number
  color: string
}

interface StatsData {
  date_range: string
  total_impressions: number
  total_conversions: number
  conversion_rate: number
  avg_daily_impressions: number
  peak_day_value: number
  peak_day_date: string
  unique_wins: number
  days_tracked: number
  windows_clicks: number
  mac_clicks: number
  android_clicks: number
  trend_impressions_pct: number
  trend_conversions_pct: number
  trend_avg_pct: number
  trend_wins_pct: number
  daily_breakdown: DayRow[]
  preferences: Record<string, boolean>
}

// ─── Sparkline (SVG) ──────────────────────────────────────────────────────────
function Sparkline({ data, color }: { data: number[]; color: string }) {
  if (!data.length) return null
  const max = Math.max(...data, 1)
  const w = 100, h = 32, pts = data.length
  const xs = data.map((_, i) => (i / Math.max(pts - 1, 1)) * w)
  const ys = data.map(v => h - (v / max) * h * 0.9 - 2)
  const d = xs.map((x, i) => `${i === 0 ? 'M' : 'L'}${x},${ys[i]}`).join(' ')
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-8 mt-2" preserveAspectRatio="none">
      <path d={d} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

// ─── Trend badge ──────────────────────────────────────────────────────────────
function Trend({ pct }: { pct: number }) {
  if (!pct) return null
  const up = pct > 0
  return (
    <span className={`text-xs font-semibold flex items-center gap-0.5 ${up ? 'text-emerald-400' : 'text-red-400'}`}>
      <TrendingUp size={11} className={up ? '' : 'rotate-180'} />
      {up ? '+' : ''}{pct.toFixed(1)}%
    </span>
  )
}

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function PublisherStatsPage() {
  const params = useParams()
  const shareId = params.publisherId as string

  const [stats, setStats] = useState<StatsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [chartRange, setChartRange] = useState<'7' | '14' | '30'>('7')
  // Platform click filters — empty set = show all platforms
  const [platformFilters, setPlatformFilters] = useState<Set<'windows' | 'mac' | 'android'>>(new Set())

  const loadStats = useCallback(async () => {
    if (!shareId) { setError(true); setLoading(false); return }
    setLoading(true)
    try {
      const response = await publicStatsApi.getPublisherStats(shareId)
      const d = response.data.data

      const daily: DayRow[] = (d.daily_breakdown || []).map((r: any) => ({
        date: r.date,
        clicks: r.clicks || 0,
        unique_wins: r.unique_wins || r.windows_clicks || 0,
        conversions: r.conversions || 0,
        cr: r.cr || 0,
        windows_clicks: r.windows_clicks || 0,
        mac_clicks: r.mac_clicks || 0,
        android_clicks: r.android_clicks || 0,
      }))

      const totalImp = d.total_impressions || d.total_clicks || 0
      const totalConv = d.total_conversions || 0
      const cr = d.conversion_rate || (totalImp > 0 ? (totalConv / totalImp) * 100 : 0)
      const days = daily.length || 1

      // Find peak day
      const peakRow = daily.reduce(
        (a: DayRow, b: DayRow) => (b.clicks >= (a?.clicks || 0) ? b : a),
        daily[0] || { clicks: 0, date: '' } as DayRow,
      )

      // Unique wins = sum of unique wins across all days
      const uniqueWins = daily.reduce((s: number, r: DayRow) => s + r.unique_wins, 0)

      setStats({
        date_range: d.date_range || `Last ${days} Days`,
        total_impressions: totalImp,
        total_conversions: totalConv,
        conversion_rate: cr,
        avg_daily_impressions: d.insights?.avg_daily_clicks || Math.round(totalImp / days),
        peak_day_value: peakRow?.clicks || 0,
        peak_day_date: peakRow?.date || '',
        unique_wins: d.unique_wins || uniqueWins,
        days_tracked: days,
        windows_clicks: d.unique_windows_clicks || 0,
        mac_clicks: d.unique_mac_clicks || 0,
        android_clicks: d.unique_android_clicks || 0,
        trend_impressions_pct: d.trend_impressions_pct || 0,
        trend_conversions_pct: d.trend_conversions_pct || 0,
        trend_avg_pct: d.trend_avg_pct || 0,
        trend_wins_pct: d.trend_wins_pct || 0,
        daily_breakdown: daily,
        preferences: d.preferences || {},
      })
    } catch (err: any) {
      // Any failure (invalid token, revoked, wrong publisher, 404, network)
      // renders the same minimal expired message — never reveal why the link
      // failed or who it belonged to.
      console.error('Public stats error:', err?.response?.status)
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [shareId])

  useEffect(() => { loadStats() }, [loadStats])

  // ─── Platform filter toggle ───────────────────────────────────────────────
  const togglePlatform = (key: 'windows' | 'mac' | 'android') => {
    setPlatformFilters(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  // ─── Loading ───────────────────────────────────────────────────────────────
  if (loading) return (
    <div className="min-h-screen bg-[#0b0d15] flex items-center justify-center">
      <div className="text-center">
        <div className="w-10 h-10 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
        <p className="text-gray-500 text-sm">Stats</p>
      </div>
    </div>
  )

  // ─── Expired / error screen — deliberately minimal, reveals nothing ─────────
  if (error || !stats) return (
    <div className="min-h-screen bg-[#0b0d15] flex items-center justify-center">
      <div className="text-center max-w-sm px-6">
        <AlertCircle className="w-12 h-12 text-gray-600 mx-auto mb-4" />
        <h1 className="text-lg font-medium text-gray-300 mb-2">Stats</h1>
        <p className="text-sm text-gray-500">This statistics link has expired.</p>
      </div>
    </div>
  )

  const prefs = stats.preferences

  // ─── Platform filter helpers ──────────────────────────────────────────────
  // Respect the admin's per-OS toggles: an OS the admin hid is not shown at all.
  const platformChips: PlatformChip[] = [
    ...(prefs.show_windows_clicks !== false
      ? [{ key: 'windows' as const, label: 'Windows', value: stats.windows_clicks, color: 'text-sky-300' }]
      : []),
    ...(prefs.show_mac_clicks !== false
      ? [{ key: 'mac' as const, label: 'Mac', value: stats.mac_clicks, color: 'text-violet-300' }]
      : []),
    ...(prefs.show_android_clicks !== false
      ? [{ key: 'android' as const, label: 'Android', value: stats.android_clicks, color: 'text-emerald-300' }]
      : []),
  ]

  const hasAnyPlatformData = platformChips.some(c => c.value > 0)
  const showFilters = prefs.show_os !== false && hasAnyPlatformData
  const filterActive = platformFilters.size > 0

  // Filter daily rows by the selected platforms. With no selection every
  // platform is included, so the headline numbers are untouched.
  // (Plain computation — not a hook — so early returns above stay safe.)
  const filteredRows = filterActive
    ? stats.daily_breakdown.filter(row =>
        (platformFilters.has('windows') && row.windows_clicks > 0) ||
        (platformFilters.has('mac') && row.mac_clicks > 0) ||
        (platformFilters.has('android') && row.android_clicks > 0),
      )
    : stats.daily_breakdown

  const filteredClicks = filteredRows.reduce((s, r) => s + r.clicks, 0)
  const filteredConversions = filteredRows.reduce((s, r) => s + r.conversions, 0)
  const filteredCr = filteredClicks > 0 ? (filteredConversions / filteredClicks) * 100 : 0

  const chartDays = parseInt(chartRange)
  const chartData = filteredRows.slice(-chartDays)

  const fmtDate = (d: string) => {
    try {
      const dt = new Date(d + 'T00:00:00')
      return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
    } catch { return d }
  }

  const fmtShort = (d: string) => {
    try {
      const dt = new Date(d + 'T00:00:00')
      return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
    } catch { return d }
  }

  // Build SVG chart lines
  const chartH = 200
  const chartW = 600
  const padL = 48, padR = 24, padT = 16, padB = 40
  const plotW = chartW - padL - padR
  const plotH = chartH - padT - padB
  const impVals = chartData.map(r => r.clicks)
  const convVals = chartData.map(r => r.conversions)
  const maxImp = Math.max(...impVals, 1)
  const maxConv = Math.max(...convVals, 1)
  const xOf = (i: number) => padL + (i / Math.max(chartData.length - 1, 1)) * plotW
  const yImp = (v: number) => padT + plotH - (v / maxImp) * plotH
  const yConv = (v: number) => padT + plotH - (v / maxConv) * plotH

  const impPath = chartData.map((r, i) => `${i === 0 ? 'M' : 'L'}${xOf(i)},${yImp(r.clicks)}`).join(' ')
  const convPath = chartData.map((r, i) => `${i === 0 ? 'M' : 'L'}${xOf(i)},${yConv(r.conversions)}`).join(' ')

  // Y-axis labels
  const impTicks = [0, 0.25, 0.5, 0.75, 1].map(t => Math.round(maxImp * t))
  const convTicks = [0, 0.25, 0.5, 0.75, 1].map(t => Math.round(maxConv * t))

  // peak row
  const peakIdx = chartData.findIndex(r => r.date === stats.peak_day_date)

  return (
    <div className="min-h-screen bg-[#0b0d15] text-white font-sans">
      {/* ── Header — title only, fully white-labeled ─────────────────────── */}
      <div className="bg-[#10131f] border-b border-white/5 px-6 py-5">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <h1 className="text-lg font-semibold text-white">Stats</h1>
          <div className="text-xs text-gray-500">{stats.date_range}</div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-6">

        {/* ── Platform click filters ───────────────────────────────────── */}
        {showFilters && (
          <div className="bg-[#10131f] rounded-2xl p-4 border border-white/5 flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium text-gray-500 uppercase tracking-wide mr-1">Platform</span>
            {platformChips.map(chip => {
              const active = platformFilters.has(chip.key)
              return (
                <button
                  key={chip.key}
                  onClick={() => togglePlatform(chip.key)}
                  className={`flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-medium border transition-all ${
                    active
                      ? 'bg-indigo-500/20 border-indigo-400/50 text-indigo-200'
                      : 'bg-white/[0.03] border-white/10 text-gray-400 hover:border-white/25 hover:text-gray-300'
                  }`}
                >
                  <span className={`w-1.5 h-1.5 rounded-full ${active ? 'bg-indigo-400' : 'bg-gray-600'}`} />
                  {chip.label}
                  <span className={`font-mono ${chip.color}`}>{chip.value.toLocaleString()}</span>
                </button>
              )
            })}
            {filterActive && (
              <button
                onClick={() => setPlatformFilters(new Set())}
                className="ml-auto text-xs text-gray-500 hover:text-gray-300 transition-colors px-2 py-1"
              >
                Clear
              </button>
            )}
          </div>
        )}

        {/* ── Row 1: top 4 metric cards ─────────────────────────────────── */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">

          {/* Total Impressions */}
          {prefs.show_impressions !== false && (
            <div className="bg-[#10131f] rounded-2xl p-5 border border-white/5">
              <div className="flex items-center gap-2 text-indigo-300 mb-2">
                <Eye size={15} />
                <span className="text-xs font-semibold uppercase tracking-wide">Total Impressions</span>
              </div>
              <p className="text-3xl font-bold text-white">
                {(filterActive ? filteredClicks : stats.total_impressions).toLocaleString()}
              </p>
              <p className="text-xs text-gray-500 mt-0.5">{filterActive ? 'Filtered' : stats.date_range}</p>
              <Sparkline data={chartData.map(r => r.clicks)} color="#818cf8" />
            </div>
          )}

          {/* Total Conversions */}
          {prefs.show_conversions !== false && (
            <div className="bg-[#10131f] rounded-2xl p-5 border border-white/5">
              <div className="flex items-center gap-2 text-purple-300 mb-2">
                <Target size={15} />
                <span className="text-xs font-semibold uppercase tracking-wide">Conversions</span>
              </div>
              <p className="text-3xl font-bold text-white">
                {(filterActive ? filteredConversions : stats.total_conversions).toLocaleString()}
              </p>
              <p className="text-xs text-gray-500 mt-0.5">{filterActive ? 'Filtered' : stats.date_range}</p>
              <Sparkline data={chartData.map(r => r.conversions)} color="#a78bfa" />
            </div>
          )}

          {/* Conversion Rate */}
          {prefs.show_cr !== false && (
            <div className="bg-[#10131f] rounded-2xl p-5 border border-white/5">
              <div className="flex items-center gap-2 text-emerald-400 mb-2">
                <Percent size={15} />
                <span className="text-xs font-semibold uppercase tracking-wide">Conversion Rate</span>
              </div>
              <p className="text-3xl font-bold text-white">
                {(filterActive ? filteredCr : stats.conversion_rate).toFixed(2)}%
              </p>
              <p className="text-xs text-gray-500 mt-0.5">{filterActive ? 'Filtered' : stats.date_range}</p>
              <div className="mt-2"><Trend pct={stats.trend_conversions_pct} /></div>
            </div>
          )}

          {/* Avg Daily Impressions */}
          {prefs.show_impressions !== false && (
            <div className="bg-[#10131f] rounded-2xl p-5 border border-white/5">
              <div className="flex items-center gap-2 text-sky-400 mb-2">
                <BarChart2 size={15} />
                <span className="text-xs font-semibold uppercase tracking-wide">Avg Daily</span>
              </div>
              <p className="text-3xl font-bold text-white">{stats.avg_daily_impressions.toLocaleString()}</p>
              <p className="text-xs text-gray-500 mt-0.5">per day</p>
              <div className="mt-2"><Trend pct={stats.trend_avg_pct} /></div>
            </div>
          )}
        </div>

        {/* ── Row 2: lower 4 cards ───────────────────────────────────────── */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">

          {/* Peak Day */}
          <div className="bg-[#10131f] rounded-2xl p-5 border border-white/5">
            <div className="flex items-center gap-2 text-emerald-400 mb-2">
              <TrendingUp size={15} />
              <span className="text-xs font-semibold uppercase tracking-wide">Peak Day</span>
            </div>
            <p className="text-3xl font-bold text-white">{stats.peak_day_value.toLocaleString()}</p>
            <p className="text-xs text-gray-500 mt-0.5">{stats.peak_day_date ? fmtDate(stats.peak_day_date) : '—'}</p>
          </div>

          {/* Unique Wins */}
          {prefs.show_valid_clicks !== false && (
            <div className="bg-[#10131f] rounded-2xl p-5 border border-white/5">
              <div className="flex items-center gap-2 text-amber-400 mb-2">
                <Trophy size={15} />
                <span className="text-xs font-semibold uppercase tracking-wide">Unique Wins</span>
              </div>
              <p className="text-3xl font-bold text-white">{stats.unique_wins.toLocaleString()}</p>
              <p className="text-xs text-gray-500 mt-0.5">validated clicks</p>
              <div className="mt-2"><Trend pct={stats.trend_wins_pct} /></div>
            </div>
          )}

          {/* Days Tracked */}
          <div className="bg-[#10131f] rounded-2xl p-5 border border-white/5">
            <div className="flex items-center gap-2 text-indigo-300 mb-2">
              <CalendarDays size={15} />
              <span className="text-xs font-semibold uppercase tracking-wide">Days Tracked</span>
            </div>
            <p className="text-3xl font-bold text-white">{stats.days_tracked}</p>
            <p className="text-xs text-gray-500 mt-0.5">in this period</p>
          </div>

          {/* Platforms */}
          {prefs.show_device !== false && (
            <div className="bg-[#10131f] rounded-2xl p-5 border border-white/5">
              <div className="flex items-center gap-2 text-purple-300 mb-2">
                <Monitor size={15} />
                <span className="text-xs font-semibold uppercase tracking-wide">Platforms</span>
              </div>
              <div className="mt-1 space-y-2">
                {platformChips.map(c => (
                  <div key={c.key} className="flex items-center justify-between text-xs">
                    <span className="text-gray-400 flex items-center gap-1.5">
                      {c.key === 'windows' ? <Monitor size={11} /> : <Smartphone size={11} />}
                      {c.label}
                    </span>
                    <span className={`font-mono font-semibold ${c.color}`}>{c.value.toLocaleString()}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* ── Chart ───────────────────────────────────────────────────────── */}
        <div className="bg-[#10131f] rounded-2xl p-5 border border-white/5">
          <div className="flex items-center justify-between mb-4">
            <p className="text-sm font-semibold text-white">Impressions &amp; Conversions Over Time</p>
            <div className="relative">
              <select
                value={chartRange}
                onChange={e => setChartRange(e.target.value as any)}
                className="appearance-none bg-[#181c2c] text-gray-300 text-xs border border-white/10 rounded-lg pl-3 pr-7 py-1.5 cursor-pointer focus:outline-none"
              >
                <option value="7">Last 7 days</option>
                <option value="14">Last 14 days</option>
                <option value="30">Last 30 days</option>
              </select>
              <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
            </div>
          </div>

          {chartData.length === 0 ? (
            <div className="flex items-center justify-center h-40 text-gray-600 text-sm">
              {filterActive ? 'No data for the selected platforms' : 'No data available'}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <svg viewBox={`0 0 ${chartW} ${chartH}`} className="w-full" style={{ minWidth: '320px' }}>
                {/* Grid lines */}
                {[0, 0.25, 0.5, 0.75, 1].map((t, i) => (
                  <g key={i}>
                    <line
                      x1={padL} y1={padT + plotH - t * plotH}
                      x2={padL + plotW} y2={padT + plotH - t * plotH}
                      stroke="#ffffff08" strokeWidth="1"
                    />
                    <text x={padL - 6} y={padT + plotH - t * plotH + 4} textAnchor="end" fontSize="9" fill="#6b7280">
                      {impTicks[i] >= 1000 ? `${(impTicks[i] / 1000).toFixed(0)}K` : impTicks[i]}
                    </text>
                    <text x={padL + plotW + 6} y={padT + plotH - t * plotH + 4} textAnchor="start" fontSize="9" fill="#6b7280">
                      {convTicks[i]}
                    </text>
                  </g>
                ))}

                {/* Peak highlight */}
                {peakIdx >= 0 && (
                  <line
                    x1={xOf(peakIdx)} y1={padT}
                    x2={xOf(peakIdx)} y2={padT + plotH}
                    stroke="#818cf820" strokeWidth="2"
                  />
                )}

                {/* Impressions line */}
                <path d={impPath} fill="none" stroke="#818cf8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                {chartData.map((r, i) => (
                  <circle key={`imp-${i}`} cx={xOf(i)} cy={yImp(r.clicks)} r="3" fill="#818cf8" opacity="0.8" />
                ))}

                {/* Conversions line */}
                <path d={convPath} fill="none" stroke="#a78bfa" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                {chartData.map((r, i) => (
                  <circle key={`conv-${i}`} cx={xOf(i)} cy={yConv(r.conversions)} r="3" fill="#a78bfa" opacity="0.8" />
                ))}

                {/* X-axis labels */}
                {chartData.map((r, i) => {
                  if (chartData.length > 10 && i % 2 !== 0) return null
                  return (
                    <text key={`x-${i}`} x={xOf(i)} y={chartH - 6} textAnchor="middle" fontSize="9" fill="#6b7280">
                      {fmtShort(r.date)}
                    </text>
                  )
                })}
              </svg>

              {/* Legend */}
              <div className="flex items-center gap-5 mt-2 px-1">
                <span className="flex items-center gap-1.5 text-xs text-gray-400">
                  <span className="w-3 h-0.5 bg-indigo-400 inline-block rounded" /> Impressions
                </span>
                <span className="flex items-center gap-1.5 text-xs text-gray-400">
                  <span className="w-3 h-0.5 bg-purple-400 inline-block rounded" /> Conversions
                </span>
              </div>
            </div>
          )}
        </div>

        {/* ── Daily Breakdown Table ─────────────────────────────────────── */}
        {prefs.show_daily_breakdown !== false && filteredRows.length > 0 && (
          <div className="bg-[#10131f] rounded-2xl border border-white/5 overflow-hidden">
            <div className="px-5 py-4 border-b border-white/5">
              <p className="text-sm font-semibold text-white">Daily Breakdown</p>
              <p className="text-xs text-gray-500 mt-0.5">
                {filterActive ? 'Filtered by selected platforms' : 'Impressions and conversions per day'}
              </p>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-white/5">
                    <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Date</th>
                    {prefs.show_impressions !== false && (
                      <th className="px-4 py-3 text-left text-xs font-medium text-indigo-300 uppercase tracking-wide">Impressions</th>
                    )}
                    {prefs.show_valid_clicks !== false && (
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Unique Wins</th>
                    )}
                    {prefs.show_conversions !== false && (
                      <th className="px-4 py-3 text-left text-xs font-medium text-purple-300 uppercase tracking-wide">Conversions</th>
                    )}
                    {prefs.show_cr !== false && (
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Conv. Rate</th>
                    )}
                    {showFilters && (
                      <>
                        <th className="px-4 py-3 text-left text-xs font-medium text-sky-400/80 uppercase tracking-wide">Windows</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-violet-400/80 uppercase tracking-wide">Mac</th>
                        <th className="px-4 py-3 text-left text-xs font-medium text-emerald-400/80 uppercase tracking-wide">Android</th>
                      </>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {filteredRows.slice(0, 30).map(row => {
                    const isPeak = row.date === stats.peak_day_date
                    return (
                      <tr key={row.date} className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors">
                        <td className="px-5 py-3 text-sm font-medium text-gray-200 whitespace-nowrap">
                          {isPeak && <span className="mr-1.5 text-amber-400">★</span>}
                          {fmtDate(row.date)}
                        </td>
                        {prefs.show_impressions !== false && (
                          <td className="px-4 py-3 font-mono font-semibold text-indigo-300">{row.clicks.toLocaleString()}</td>
                        )}
                        {prefs.show_valid_clicks !== false && (
                          <td className="px-4 py-3 font-mono text-gray-300">{row.unique_wins.toLocaleString()}</td>
                        )}
                        {prefs.show_conversions !== false && (
                          <td className="px-4 py-3 font-mono font-semibold text-purple-300">{row.conversions.toLocaleString()}</td>
                        )}
                        {prefs.show_cr !== false && (
                          <td className="px-4 py-3 text-gray-300 font-mono">{row.cr.toFixed(2)}%</td>
                        )}
                        {showFilters && (
                          <>
                            <td className="px-4 py-3 text-gray-400 font-mono">{row.windows_clicks.toLocaleString()}</td>
                            <td className="px-4 py-3 text-gray-400 font-mono">{row.mac_clicks.toLocaleString()}</td>
                            <td className="px-4 py-3 text-gray-400 font-mono">{row.android_clicks.toLocaleString()}</td>
                          </>
                        )}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Footer — neutral, no identifying info */}
        <div className="text-center py-6 border-t border-white/5">
          <div className="flex items-center justify-center gap-4 text-xs text-gray-600">
            <span>All times in UTC</span>
          </div>
        </div>
      </div>
    </div>
  )
}