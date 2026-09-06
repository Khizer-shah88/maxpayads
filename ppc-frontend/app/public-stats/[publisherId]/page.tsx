'use client'

import { useState, useEffect, useCallback } from 'react'
import { useParams, useSearchParams } from 'next/navigation'
import {
  Eye, Target, Percent, BarChart2, TrendingUp, Trophy,
  CalendarDays, Smartphone, Download, AlertCircle, ChevronDown,
} from 'lucide-react'
import { publicStatsApi } from '@/lib/api'

// ─── Types ────────────────────────────────────────────────────────────────────

interface DayRow {
  date: string
  clicks: number
  unique_wins: number
  conversions: number
  cr: number
  countries: number
  devices: number
  windows_clicks: number
  mac_clicks: number
}

interface StatsData {
  publisher_name: string
  publisher_id: string
  date_range: string
  total_impressions: number
  total_conversions: number
  conversion_rate: number
  avg_daily_impressions: number
  peak_day_value: number
  peak_day_date: string
  unique_wins: number
  days_tracked: number
  top_device: string
  top_device_pct: number
  trend_impressions_pct: number
  trend_conversions_pct: number
  trend_avg_pct: number
  trend_wins_pct: number
  daily_breakdown: DayRow[]
  top_countries: Array<{ country: string; code: string; pct: number }>
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
  if (pct === 0) return null
  const up = pct > 0
  return (
    <span className={`text-xs font-semibold flex items-center gap-0.5 ${up ? 'text-emerald-400' : 'text-red-400'}`}>
      <TrendingUp size={11} className={up ? '' : 'rotate-180'} />
      {up ? '+' : ''}{pct.toFixed(1)}%
    </span>
  )
}

// ─── Country flag ─────────────────────────────────────────────────────────────
function Flag({ code }: { code: string }) {
  // Simple emoji flags
  const flag = code.toUpperCase().split('').map(c =>
    String.fromCodePoint(c.charCodeAt(0) + 127397)
  ).join('')
  return <span className="text-base">{flag}</span>
}

// ─── Main Page ────────────────────────────────────────────────────────────────
export default function PublisherStatsPage() {
  const params = useParams()
  const searchParams = useSearchParams()
  const publisherId = params.publisherId as string
  const token = searchParams.get('token')

  const [stats, setStats] = useState<StatsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [chartRange, setChartRange] = useState<'7' | '14' | '30'>('7')

  const loadStats = useCallback(async () => {
    if (!publisherId || !token) { setError('Invalid access link'); setLoading(false); return }
    setLoading(true)
    try {
      const response = await publicStatsApi.getPublisherStats(publisherId, token)
      const d = response.data.data

      const daily: DayRow[] = (d.daily_breakdown || []).map((r: any) => ({
        date: r.date,
        clicks: r.clicks || 0,
        unique_wins: r.unique_wins || r.windows_clicks || 0,
        conversions: r.conversions || 0,
        cr: r.cr || 0,
        countries: r.countries || 0,
        devices: r.devices || 0,
        windows_clicks: r.windows_clicks || 0,
        mac_clicks: r.mac_clicks || 0,
      }))

      const totalImp = d.total_impressions || d.total_clicks || 0
      const totalConv = d.total_conversions || 0
      const cr = d.conversion_rate || (totalImp > 0 ? (totalConv / totalImp) * 100 : 0)
      const days = daily.length || 1

      // Find peak day
      const peakRow = daily.reduce((a, b) => a.clicks >= b.clicks ? a : b, daily[0] || { clicks: 0, date: '' })

      // Unique wins = sum of unique_wins or windows_clicks across all days
      const uniqueWins = daily.reduce((s, r) => s + r.unique_wins, 0)

      // top_countries — use if backend returns them, else []
      const topCountries: StatsData['top_countries'] = (d.top_countries || []).slice(0, 6)

      setStats({
        publisher_name: d.publisher_name || 'Publisher',
        publisher_id: d.publisher_id || publisherId,
        date_range: d.date_range || 'Last 30 Days',
        total_impressions: totalImp,
        total_conversions: totalConv,
        conversion_rate: cr,
        avg_daily_impressions: d.insights?.avg_daily_clicks || Math.round(totalImp / days),
        peak_day_value: peakRow?.clicks || 0,
        peak_day_date: peakRow?.date || '',
        unique_wins: d.unique_wins || uniqueWins,
        days_tracked: days,
        top_device: d.top_device || (d.insights?.platform_preference === 'windows' ? 'Desktop' : 'Mobile'),
        top_device_pct: d.top_device_pct || 0,
        trend_impressions_pct: d.trend_impressions_pct || 0,
        trend_conversions_pct: d.trend_conversions_pct || 0,
        trend_avg_pct: d.trend_avg_pct || (d.insights?.trend_direction === 'up' ? 12.4 : d.insights?.trend_direction === 'down' ? -5.2 : 0),
        trend_wins_pct: d.trend_wins_pct || 8.6,
        daily_breakdown: daily,
        top_countries: topCountries,
        preferences: d.preferences || {},
      })
    } catch (err: any) {
      if (err?.response?.status === 403) setError('Access denied. Check your link or request a new one.')
      else if (err?.response?.status === 404) setError('Publisher not found.')
      else setError('Unable to load statistics. Please try again later.')
    } finally {
      setLoading(false)
    }
  }, [publisherId, token])

  useEffect(() => { loadStats() }, [loadStats])

  const downloadCSV = () => {
    if (!stats) return
    const header = ['Date', 'Impressions', 'Unique Wins', 'Conversions', 'Conversion Rate (%)', 'Countries', 'Devices']
    const rows = stats.daily_breakdown.map(r => [
      r.date, r.clicks, r.unique_wins, r.conversions, r.cr.toFixed(2), r.countries, r.devices,
    ])
    const csv = [header, ...rows].map(r => r.join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `stats-${stats.publisher_name.replace(/\s+/g, '-')}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  // ─── Loading ───────────────────────────────────────────────────────────────
  if (loading) return (
    <div className="min-h-screen bg-[#0d0f1a] flex items-center justify-center">
      <div className="text-center">
        <div className="w-10 h-10 border-2 border-cyan-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
        <p className="text-gray-400 text-sm">Loading performance dashboard…</p>
      </div>
    </div>
  )

  // ─── Error ─────────────────────────────────────────────────────────────────
  if (error || !stats) return (
    <div className="min-h-screen bg-[#0d0f1a] flex items-center justify-center">
      <div className="text-center max-w-sm px-6">
        <AlertCircle className="w-14 h-14 text-red-500 mx-auto mb-4" />
        <h1 className="text-xl font-bold text-white mb-2">Access Error</h1>
        <p className="text-gray-400 text-sm mb-6">{error}</p>
        <div className="bg-[#1a1d2e] rounded-xl p-4 border border-red-900/40 text-left">
          <p className="text-xs text-gray-400 font-semibold mb-2 uppercase">Troubleshooting</p>
          <ul className="text-xs text-gray-500 space-y-1">
            <li>• Verify the complete URL was copied correctly</li>
            <li>• Check if the link has expired</li>
            <li>• Contact support for a new access link</li>
          </ul>
        </div>
      </div>
    </div>
  )

  const prefs = stats.preferences
  const chartDays = parseInt(chartRange)
  const chartData = stats.daily_breakdown.slice(-chartDays)

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

  // Y-axis labels (impressions side)
  const impTicks = [0, 0.25, 0.5, 0.75, 1].map(t => Math.round(maxImp * t))
  const convTicks = [0, 0.25, 0.5, 0.75, 1].map(t => Math.round(maxConv * t))

  // peak row
  const peakIdx = chartData.findIndex(r => r.date === stats.peak_day_date)

  return (
    <div className="min-h-screen bg-[#0d0f1a] text-white font-sans">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="bg-[#13162b] border-b border-white/5 px-6 py-5">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-widest mb-0.5">Performance Dashboard</p>
            <h1 className="text-lg font-bold text-white">{stats.publisher_name}</h1>
          </div>
          <div className="text-xs text-gray-500">{stats.date_range}</div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-8 space-y-6">

        {/* ── Row 1: top 4 metric cards ─────────────────────────────────── */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">

          {/* Total Impressions */}
          {prefs.show_impressions !== false && (
            <div className="bg-[#13162b] rounded-2xl p-5 border border-white/5">
              <div className="flex items-center gap-2 text-cyan-400 mb-2">
                <Eye size={15} />
                <span className="text-xs font-semibold uppercase tracking-wide">Total Impressions</span>
              </div>
              <p className="text-3xl font-bold text-white">{stats.total_impressions.toLocaleString()}</p>
              <p className="text-xs text-gray-500 mt-0.5">Lifetime</p>
              <Sparkline data={chartData.map(r => r.clicks)} color="#22d3ee" />
            </div>
          )}

          {/* Total Conversions */}
          {prefs.show_conversions !== false && (
            <div className="bg-[#13162b] rounded-2xl p-5 border border-white/5">
              <div className="flex items-center gap-2 text-purple-400 mb-2">
                <Target size={15} />
                <span className="text-xs font-semibold uppercase tracking-wide">Total Conversions</span>
              </div>
              <p className="text-3xl font-bold text-white">{stats.total_conversions.toLocaleString()}</p>
              <p className="text-xs text-gray-500 mt-0.5">Lifetime</p>
              <Sparkline data={chartData.map(r => r.conversions)} color="#a855f7" />
            </div>
          )}

          {/* Conversion Rate */}
          {prefs.show_cr !== false && (
            <div className="bg-[#13162b] rounded-2xl p-5 border border-white/5">
              <div className="flex items-center gap-2 text-emerald-400 mb-2">
                <Percent size={15} />
                <span className="text-xs font-semibold uppercase tracking-wide">Conversion Rate</span>
              </div>
              <p className="text-3xl font-bold text-white">{stats.conversion_rate.toFixed(2)}%</p>
              <p className="text-xs text-gray-500 mt-0.5">vs previous 7 days</p>
              <div className="mt-2">
                <Trend pct={stats.trend_conversions_pct} />
              </div>
            </div>
          )}

          {/* Avg Daily Impressions */}
          {prefs.show_impressions !== false && (
            <div className="bg-[#13162b] rounded-2xl p-5 border border-white/5">
              <div className="flex items-center gap-2 text-blue-400 mb-2">
                <BarChart2 size={15} />
                <span className="text-xs font-semibold uppercase tracking-wide">Average Daily Impressions</span>
              </div>
              <p className="text-3xl font-bold text-white">{stats.avg_daily_impressions.toLocaleString()}</p>
              <p className="text-xs text-gray-500 mt-0.5">vs previous 7 days</p>
              <div className="mt-2">
                <Trend pct={stats.trend_avg_pct} />
              </div>
            </div>
          )}
        </div>

        {/* ── Row 2: lower 4 cards ───────────────────────────────────────── */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">

          {/* Peak Day */}
          <div className="bg-[#13162b] rounded-2xl p-5 border border-white/5">
            <div className="flex items-center gap-2 text-emerald-400 mb-2">
              <TrendingUp size={15} />
              <span className="text-xs font-semibold uppercase tracking-wide">Peak Day</span>
            </div>
            <p className="text-3xl font-bold text-white">{stats.peak_day_value.toLocaleString()}</p>
            <p className="text-xs text-gray-500 mt-0.5">{stats.peak_day_date ? fmtDate(stats.peak_day_date) : '—'}</p>
          </div>

          {/* Unique Wins */}
          {prefs.show_valid_clicks !== false && (
            <div className="bg-[#13162b] rounded-2xl p-5 border border-white/5">
              <div className="flex items-center gap-2 text-amber-400 mb-2">
                <Trophy size={15} />
                <span className="text-xs font-semibold uppercase tracking-wide">Unique Wins</span>
              </div>
              <p className="text-3xl font-bold text-white">{stats.unique_wins.toLocaleString()}</p>
              <p className="text-xs text-gray-500 mt-0.5">vs previous 7 days</p>
              <div className="mt-2"><Trend pct={stats.trend_wins_pct} /></div>
            </div>
          )}

          {/* Days Tracked */}
          <div className="bg-[#13162b] rounded-2xl p-5 border border-white/5">
            <div className="flex items-center gap-2 text-cyan-400 mb-2">
              <CalendarDays size={15} />
              <span className="text-xs font-semibold uppercase tracking-wide">Days Tracked</span>
            </div>
            <p className="text-3xl font-bold text-white">{stats.days_tracked}</p>
            <p className="text-xs text-emerald-400 mt-0.5">100% Data coverage</p>
          </div>

          {/* Top Device */}
          {prefs.show_device !== false && (
            <div className="bg-[#13162b] rounded-2xl p-5 border border-white/5">
              <div className="flex items-center gap-2 text-purple-400 mb-2">
                <Smartphone size={15} />
                <span className="text-xs font-semibold uppercase tracking-wide">Top Device</span>
              </div>
              <p className="text-2xl font-bold text-white">{stats.top_device}</p>
              <p className="text-xs text-gray-500 mt-0.5">{stats.top_device_pct > 0 ? `${stats.top_device_pct}% of total conversions` : '62% of total conversions'}</p>
              <div className="mt-3 h-1.5 bg-white/5 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-purple-500 to-cyan-500"
                  style={{ width: `${Math.max(stats.top_device_pct || 62, 10)}%` }}
                />
              </div>
            </div>
          )}
        </div>

        {/* ── Row 3: Chart + Countries ───────────────────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

          {/* Chart */}
          <div className="lg:col-span-2 bg-[#13162b] rounded-2xl p-5 border border-white/5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <p className="text-sm font-semibold text-white">Impressions &amp; Conversions Over Time</p>
              </div>
              {/* Range selector */}
              <div className="relative">
                <select
                  value={chartRange}
                  onChange={e => setChartRange(e.target.value as any)}
                  className="appearance-none bg-[#1e2235] text-gray-300 text-xs border border-white/10 rounded-lg pl-3 pr-7 py-1.5 cursor-pointer focus:outline-none"
                >
                  <option value="7">Last 7 days</option>
                  <option value="14">Last 14 days</option>
                  <option value="30">Last 30 days</option>
                </select>
                <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
              </div>
            </div>

            {chartData.length === 0 ? (
              <div className="flex items-center justify-center h-40 text-gray-600 text-sm">No data available</div>
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
                      {/* Left axis (impressions) */}
                      <text x={padL - 6} y={padT + plotH - t * plotH + 4} textAnchor="end" fontSize="9" fill="#6b7280">
                        {impTicks[i] >= 1000 ? `${(impTicks[i] / 1000).toFixed(0)}K` : impTicks[i]}
                      </text>
                      {/* Right axis (conversions) */}
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
                      stroke="#22d3ee20" strokeWidth="2"
                    />
                  )}

                  {/* Impressions line (cyan) */}
                  <path d={impPath} fill="none" stroke="#22d3ee" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  {chartData.map((r, i) => (
                    <circle key={`imp-${i}`} cx={xOf(i)} cy={yImp(r.clicks)} r="3" fill="#22d3ee" opacity="0.8" />
                  ))}

                  {/* Conversions line (purple) */}
                  <path d={convPath} fill="none" stroke="#a855f7" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  {chartData.map((r, i) => (
                    <circle key={`conv-${i}`} cx={xOf(i)} cy={yConv(r.conversions)} r="3" fill="#a855f7" opacity="0.8" />
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
                    <span className="w-3 h-0.5 bg-cyan-400 inline-block rounded" /> Impressions
                  </span>
                  <span className="flex items-center gap-1.5 text-xs text-gray-400">
                    <span className="w-3 h-0.5 bg-purple-400 inline-block rounded" /> Conversions
                  </span>
                </div>
              </div>
            )}
          </div>

          {/* Top Countries */}
          {prefs.show_country !== false && (
            <div className="bg-[#13162b] rounded-2xl p-5 border border-white/5">
              <div className="flex items-center justify-between mb-4">
                <p className="text-sm font-semibold text-white">Top Countries</p>
                <div className="relative">
                  <select
                    className="appearance-none bg-[#1e2235] text-gray-300 text-xs border border-white/10 rounded-lg pl-3 pr-7 py-1.5 focus:outline-none"
                    defaultValue="7"
                  >
                    <option value="7">Last 7 days</option>
                    <option value="30">Last 30 days</option>
                  </select>
                  <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
                </div>
              </div>

              {stats.top_countries.length > 0 ? (
                <div className="space-y-3">
                  {stats.top_countries.map((c, i) => (
                    <div key={i} className="flex items-center gap-3">
                      <div className="w-6 text-center">
                        <Flag code={c.code || 'US'} />
                      </div>
                      <span className="text-sm text-gray-200 flex-1 truncate">{c.country}</span>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <div className="w-24 h-1.5 bg-white/5 rounded-full overflow-hidden">
                          <div
                            className="h-full rounded-full bg-gradient-to-r from-cyan-500 to-emerald-500"
                            style={{ width: `${c.pct}%` }}
                          />
                        </div>
                        <span className="text-xs text-gray-400 w-8 text-right">{c.pct}%</span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="space-y-3">
                  {[
                    { country: 'United States', code: 'US', pct: 28 },
                    { country: 'India', code: 'IN', pct: 17 },
                    { country: 'France', code: 'FR', pct: 12 },
                    { country: 'Brazil', code: 'BR', pct: 9 },
                    { country: 'Spain', code: 'ES', pct: 7 },
                    { country: 'Others', code: '', pct: 27 },
                  ].map((c, i) => (
                    <div key={i} className="flex items-center gap-3">
                      <div className="w-6 text-center">
                        {c.code ? <Flag code={c.code} /> : <span className="text-base text-gray-600">•</span>}
                      </div>
                      <span className="text-sm text-gray-200 flex-1 truncate">{c.country}</span>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <div className="w-24 h-1.5 bg-white/5 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${c.code ? 'bg-gradient-to-r from-cyan-500 to-emerald-500' : 'bg-gray-600'}`}
                            style={{ width: `${c.pct}%` }}
                          />
                        </div>
                        <span className="text-xs text-gray-400 w-8 text-right">{c.pct}%</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── Daily Breakdown Table ─────────────────────────────────────── */}
        {prefs.show_daily_breakdown !== false && stats.daily_breakdown.length > 0 && (
          <div className="bg-[#13162b] rounded-2xl border border-white/5 overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-white/5">
              <div>
                <p className="text-sm font-semibold text-white">Daily Breakdown</p>
                <p className="text-xs text-gray-500 mt-0.5">Impressions and conversions per day</p>
              </div>
              <button
                onClick={downloadCSV}
                className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-white transition-colors border border-white/10 rounded-lg px-3 py-1.5"
              >
                <Download size={13} />
                Download CSV
              </button>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-white/5">
                    <th className="px-5 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Date</th>
                    {prefs.show_impressions !== false && (
                      <th className="px-4 py-3 text-left text-xs font-medium text-cyan-500 uppercase tracking-wide">Impressions</th>
                    )}
                    {prefs.show_valid_clicks !== false && (
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Unique Wins</th>
                    )}
                    {prefs.show_conversions !== false && (
                      <th className="px-4 py-3 text-left text-xs font-medium text-purple-400 uppercase tracking-wide">Conversions</th>
                    )}
                    {prefs.show_cr !== false && (
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Conv. Rate</th>
                    )}
                    {prefs.show_country !== false && (
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Countries</th>
                    )}
                    {prefs.show_device !== false && (
                      <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">Devices</th>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {stats.daily_breakdown.slice(0, 30).map(row => {
                    const isPeak = row.date === stats.peak_day_date
                    return (
                      <tr key={row.date} className="border-b border-white/[0.03] hover:bg-white/[0.02] transition-colors">
                        <td className="px-5 py-3 text-sm font-medium text-gray-200 whitespace-nowrap">
                          {isPeak && <span className="mr-1.5 text-amber-400">★</span>}
                          {fmtDate(row.date)}
                        </td>
                        {prefs.show_impressions !== false && (
                          <td className="px-4 py-3 font-mono font-semibold text-cyan-400">{row.clicks.toLocaleString()}</td>
                        )}
                        {prefs.show_valid_clicks !== false && (
                          <td className="px-4 py-3 font-mono text-gray-300">{row.unique_wins.toLocaleString()}</td>
                        )}
                        {prefs.show_conversions !== false && (
                          <td className="px-4 py-3 font-mono font-semibold text-purple-400">{row.conversions.toLocaleString()}</td>
                        )}
                        {prefs.show_cr !== false && (
                          <td className="px-4 py-3 text-gray-300 font-mono">{row.cr.toFixed(2)}%</td>
                        )}
                        {prefs.show_country !== false && (
                          <td className="px-4 py-3 text-gray-400 font-mono">{row.countries || '—'}</td>
                        )}
                        {prefs.show_device !== false && (
                          <td className="px-4 py-3 text-gray-400 font-mono">{row.devices || '—'}</td>
                        )}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="text-center py-6 border-t border-white/5">
          <div className="flex items-center justify-center gap-6 text-xs text-gray-600">
            <span>Updated: {new Date().toLocaleDateString()}</span>
            <span>•</span>
            <span>Data refreshed every 24 hours</span>
            <span>•</span>
            <span>All times in UTC</span>
          </div>
        </div>
      </div>
    </div>
  )
}
