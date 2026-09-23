'use client'

import { useState, useEffect, useCallback, useRef, type ReactNode, type MouseEvent as ReactMouseEvent } from 'react'
import { useParams } from 'next/navigation'
import { AlertCircle, RefreshCw, Eye, Download, BarChart3, TrendingUp, CalendarDays } from 'lucide-react'
import { publicStatsApi } from '@/lib/api'

// â”€â”€â”€ Types â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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

interface CountryRow {
  country_code: string
  country: string
  clicks: number
  share_pct: number
}

interface StatsData {
  date_range: string
  identity?: { link_number: number; pub_id: string }
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
  country_breakdown?: CountryRow[]
  preferences: Record<string, boolean>
}

// â”€â”€â”€ Corner sparkline (KPI card decoration, example style) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function CornerSpark({ data, color }: { data: number[]; color: string }) {
  if (data.length < 2) return null
  const w = 96, h = 34
  const max = Math.max(...data), min = Math.min(...data)
  const range = (max - min) || 1
  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w
    const y = h - 4 - ((v - min) / range) * (h - 12)
    return `${x.toFixed(1)} ${y.toFixed(1)}`
  })
  const line = 'M' + pts.join(' L')
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none"
      className="absolute right-0 bottom-0 w-24 h-[34px] opacity-85 pointer-events-none">
      <path d={`${line} L${w} ${h} L0 ${h} Z`} fill={color} opacity="0.10" />
      <path d={line} fill="none" stroke={color} strokeWidth="1.6" opacity="0.8" />
    </svg>
  )
}

// â”€â”€â”€ Trend delta chip â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function Delta({ pct }: { pct: number }) {
  const cls = pct > 0
    ? 'text-emerald-400 bg-emerald-400/10'
    : pct < 0
      ? 'text-[#F0563E] bg-[#F0563E]/10'
      : 'text-[#5C6B7E] bg-white/[0.04]'
  return (
    <span className={`text-[11.5px] font-medium px-1.5 py-0.5 rounded-md whitespace-nowrap tabular-nums ${cls}`}>
      {pct > 0 ? '+' : ''}{pct.toFixed(0)}%
    </span>
  )
}

// ─── KPI card — example style: label + icon tile, big value, sub row ─────
function Kpi({ label, value, sub, subValue, icon, iconBg, spark }: {
  label: string
  value: string
  sub: string
  subValue?: string
  icon: ReactNode
  iconBg: string
  spark?: ReactNode
}) {
  return (
    <div className="relative overflow-hidden bg-[#111721] border border-[#1D2634] rounded-[10px] px-4 pt-3.5 pb-3">
      {spark}
      <div className="relative flex items-start justify-between gap-2">
        <span className="text-[11px] uppercase tracking-[0.08em] text-[#8695A8] font-medium pt-0.5">{label}</span>
        <span className={`w-9 h-9 rounded-[9px] grid place-items-center flex-none ${iconBg}`}>{icon}</span>
      </div>
      <p className="text-[28px] font-bold leading-[1.1] tracking-[-0.02em] text-[#E8EEF6] mt-1.5 tabular-nums">{value}</p>
      <div className="relative flex items-center justify-between gap-2 mt-2.5 pt-2 border-t border-[#1D2634]">
        <span className="text-[11.5px] text-[#5C6B7E]">{sub}</span>
        {subValue && <b className="text-[12px] text-[#C7D2E0] tabular-nums">{subValue}</b>}
      </div>
    </div>
  )
}

// â”€â”€â”€ Main Page â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export default function PublisherStatsPage() {
  const params = useParams()
  const shareId = params.publisherId as string

  const [stats, setStats] = useState<StatsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [chartRange, setChartRange] = useState<'7' | '14' | '30'>('7')
  // Platform click filters — empty set = show all platforms
  const [platformFilters, setPlatformFilters] = useState<Set<'windows' | 'mac' | 'android'>>(new Set())
  // Chart series visibility + hover crosshair + refresh timestamp
  const [series, setSeries] = useState({ imp: true, uni: true, conv: true })
  const [hoverIdx, setHoverIdx] = useState<number | null>(null)
  const [lastUpdated, setLastUpdated] = useState('')

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
        identity: d.identity || null,
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
        country_breakdown: d.country_breakdown || [],
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
      setLastUpdated(new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }))
    }
  }, [shareId])

  useEffect(() => { loadStats() }, [loadStats])

  // ── Auto refresh every 20s (spec) — pauses while a manual refresh runs ──
  const AUTO_REFRESH_MS = 20_000
  const refreshTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  useEffect(() => {
    refreshTimer.current = setInterval(() => {
      loadStats()
    }, AUTO_REFRESH_MS)
    return () => { if (refreshTimer.current) clearInterval(refreshTimer.current) }
  }, [loadStats])

  // â”€â”€â”€ Platform filter toggle â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const togglePlatform = (key: 'windows' | 'mac' | 'android') => {
    setPlatformFilters(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  // â”€â”€â”€ Loading â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  if (loading) return (
    <div className="min-h-screen bg-[#0A0E14] flex items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <div className="w-8 h-8 border-2 border-[#1D2634] border-t-[#3B82F6] rounded-full animate-spin" />
        <p className="text-[#8695A8] text-sm">Loading stats…</p>
      </div>
    </div>
  )

  // â”€â”€â”€ Expired / error screen — deliberately minimal, reveals nothing â”€â”€â”€â”€â”€â”€â”€â”€â”€
  if (error || !stats) return (
    <div className="min-h-screen bg-[#0A0E14] flex items-center justify-center">
      <div className="text-center max-w-sm px-6">
        <AlertCircle className="w-12 h-12 text-[#3D4A5E] mx-auto mb-4" />
        <h1 className="text-lg font-medium text-[#E8EEF6] mb-2">Stats</h1>
        <p className="text-sm text-[#5C6B7E]">This statistics link has expired.</p>
      </div>
    </div>
  )

  const prefs = stats.preferences

  // â”€â”€â”€ Platform filter helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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

  // â”€â”€â”€ Chart geometry (example style: area fill + right axis for series 2) â”€â”€
  const chartH = 280
  const chartW = 900
  const padL = 52, padR = 52, padT = 16, padB = 30
  const plotW = chartW - padL - padR
  const plotH = chartH - padT - padB
  const ceilTo = (v: number, s: number) => Math.max(s, Math.ceil(v / s) * s)
  const maxImp = ceilTo(Math.max(...chartData.map(r => r.clicks), 1), 50)
  const maxUni = ceilTo(Math.max(
    ...chartData.map(r => Math.max(r.unique_wins, r.conversions)), 1,
  ), 10)
  const xOf = (i: number) => padL + (i / Math.max(chartData.length - 1, 1)) * plotW
  const yImp = (v: number) => padT + plotH - (v / maxImp) * plotH
  const yUni = (v: number) => padT + plotH - (v / maxUni) * plotH

  const impPath = chartData.map((r, i) => `${i === 0 ? 'M' : 'L'}${xOf(i).toFixed(1)} ${yImp(r.clicks).toFixed(1)}`).join(' ')
  const uniPath = chartData.map((r, i) => `${i === 0 ? 'M' : 'L'}${xOf(i).toFixed(1)} ${yUni(r.unique_wins).toFixed(1)}`).join(' ')
  const convPath = chartData.map((r, i) => `${i === 0 ? 'M' : 'L'}${xOf(i).toFixed(1)} ${yUni(r.conversions).toFixed(1)}`).join(' ')
  const areaPath = chartData.length > 1
    ? `${impPath} L${xOf(chartData.length - 1).toFixed(1)} ${yImp(0)} L${padL} ${yImp(0)} Z`
    : ''

  const onChartMove = (e: ReactMouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const px = ((e.clientX - rect.left) / rect.width) * chartW
    const idx = Math.round((px - padL) / (plotW / Math.max(chartData.length - 1, 1)))
    setHoverIdx(Math.max(0, Math.min(chartData.length - 1, idx)))
  }

  // KPI values (example layout: 5 cards with corner sparks + delta chips)
  const uniTotal = filteredRows.reduce((s, r) => s + r.unique_wins, 0)
  const avgDaily = chartData.length ? Math.round(filteredClicks / chartData.length) : 0
  const peak = chartData.reduce((a, r) => (r.clicks >= (a?.clicks || 0) ? r : a), chartData[0])
  const peakCvr = peak && peak.clicks ? ((peak.conversions / peak.clicks) * 100).toFixed(2) : '0.00'
  const impSpark = chartData.map(r => r.clicks)
  const uniSpark = chartData.map(r => r.unique_wins)
  const convSpark = chartData.map(r => r.conversions)

  const toggleSeries = (k: 'imp' | 'uni' | 'conv') =>
    setSeries(prev => ({ ...prev, [k]: !prev[k] }))

  // Number of columns visible in the daily breakdown table (for colSpan).
  const visibleColCount = 1
    + (prefs.show_impressions !== false ? 1 : 0)
    + (prefs.show_windows_clicks !== false ? 1 : 0)
    + (prefs.show_mac_clicks !== false ? 1 : 0)
    + (prefs.show_android_clicks !== false ? 1 : 0)
    + (prefs.show_conversions !== false ? 1 : 0)

  const hovered = hoverIdx !== null ? chartData[hoverIdx] : null

  return (
    <div className="min-h-screen bg-[#0A0E14] text-[#E8EEF6] font-sans">
      {/* â”€â”€ Top bar — brand, platform chips, range segment, refresh â”€â”€â”€â”€â”€â”€â”€â”€ */}
      <header className="sticky top-0 z-20 bg-[#0D131C] border-b border-[#1D2634]">
        <div className="max-w-[1280px] mx-auto px-5 py-3 flex items-center justify-between gap-3.5 flex-wrap">
          <div className="flex items-center gap-2.5 min-w-0">
            <svg viewBox="0 0 140 80" className="w-[34px] h-5 text-[#3B82F6] flex-none" aria-hidden="true">
              <path fill="currentColor" d="M12 44C12 30 30 20 54 20c22 0 38 6 50 16l20-14c-4 12-4 24 0 36l-20-12c-12 8-30 12-50 12C30 58 12 52 12 44Z" />
              <path fill="currentColor" d="M56 52c2 9 10 15 20 14-6-3-11-8-14-15Z" />
              <circle cx="28" cy="38" r="3" fill="#0D131C" />
            </svg>
            <div className="min-w-0">
              <b className="block text-[15px] font-semibold tracking-[-0.01em] leading-tight">Stats</b>
              <span className="block text-[11px] text-[#5C6B7E]">Performance tracking</span>
            </div>
          </div>

          {/* ── Identity mark — which publisher/link this page tracks ── */}
          {stats.identity && (
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-[#111721] border border-[#1D2634] min-w-0">
              <span className="text-xs text-[#3B82F6] font-semibold tabular-nums whitespace-nowrap">
                #{stats.identity.link_number ? `L${stats.identity.link_number}` : 'L1'}
              </span>
              {stats.identity.pub_id && (
                <>
                  <span className="text-[10px] text-[#3D4A5E]">·</span>
                  <span className="text-xs text-[#8695A8] truncate" title={stats.identity.pub_id}>
                    Pub id {stats.identity.pub_id}
                  </span>
                </>
              )}
            </div>
          )}

          <div className="flex items-center gap-2 flex-wrap">
            {showFilters && platformChips.map(chip => {
              const active = platformFilters.has(chip.key)
              return (
                <button
                  key={chip.key}
                  onClick={() => togglePlatform(chip.key)}
                  className={`inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-md border transition-colors ${
                    active
                      ? 'bg-[#3B82F6]/15 border-[#3B82F6]/40 text-[#E8EEF6]'
                      : 'bg-[#111721] border-[#1D2634] text-[#8695A8] hover:border-[#26313F] hover:text-[#E8EEF6]'
                  }`}
                >
                  {chip.label}
                  <b className="font-medium text-[#E8EEF6] tabular-nums">{chip.value.toLocaleString()}</b>
                </button>
              )
            })}
          </div>

          <div className="flex items-center gap-2">
            <div className="flex bg-[#111721] border border-[#1D2634] rounded-lg p-0.5">
              {(['7', '14', '30'] as const).map(d => (
                <button
                  key={d}
                  onClick={() => setChartRange(d)}
                  className={`px-2.5 py-1 rounded-md text-[12.5px] transition-colors ${
                    chartRange === d ? 'bg-[#3B82F6] text-white font-medium' : 'text-[#8695A8] hover:text-[#E8EEF6]'
                  }`}
                >
                  {d}d
                </button>
              ))}
            </div>
            <button
              onClick={loadStats}
              className="inline-flex items-center gap-1.5 bg-[#111721] border border-[#1D2634] rounded-lg px-2.5 py-1.5 text-xs text-[#8695A8] hover:text-[#E8EEF6] hover:border-[#26313F] transition-colors"
            >
              <RefreshCw size={13} />
              <span className="tabular-nums">{lastUpdated || '—'}</span>
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-[1280px] mx-auto px-5 py-5 flex flex-col gap-4">
        {/* KPI grid — example layout: 5 cards w/ icon tiles + sub rows */}
        <section className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-3">
          {prefs.show_impressions !== false && (
            <Kpi
              label="Total Impressions"
              value={(filterActive ? filteredClicks : stats.total_impressions).toLocaleString()}
              sub={filterActive ? 'Filtered view' : 'Lifetime views'}
              subValue={(filterActive ? filteredClicks : stats.total_impressions).toLocaleString()}
              icon={<Eye size={17} className="text-emerald-400" />}
              iconBg="bg-emerald-400/10"
              spark={<CornerSpark data={impSpark} color="#3B82F6" />}
            />
          )}
          {prefs.show_conversions !== false && (
            <Kpi
              label="Total Conversions"
              value={(filterActive ? filteredConversions : stats.total_conversions).toLocaleString()}
              sub="Lifetime conversions"
              subValue={(filterActive ? filteredConversions : stats.total_conversions).toLocaleString()}
              icon={<Download size={17} className="text-violet-400" />}
              iconBg="bg-violet-400/10"
              spark={<CornerSpark data={convSpark} color="#F59E0B" />}
            />
          )}
          <Kpi
            label="Daily Average"
            value={avgDaily.toLocaleString()}
            sub="Mean impressions per day"
            icon={<BarChart3 size={17} className="text-sky-400" />}
            iconBg="bg-sky-400/10"
            spark={<CornerSpark data={impSpark} color="#22C55E" />}
          />
          <Kpi
            label="Peak Day"
            value={(peak?.clicks || 0).toLocaleString()}
            sub="Best day"
            subValue={peak?.date ? fmtShort(peak.date) : '\u2014'}
            icon={<TrendingUp size={17} className="text-emerald-400" />}
            iconBg="bg-emerald-400/10"
            spark={<CornerSpark data={impSpark} color="#F59E0B" />}
          />
          <Kpi
            label="Days Tracked"
            value={String(stats.days_tracked)}
            sub="Days with recorded data"
            icon={<CalendarDays size={17} className="text-amber-400" />}
            iconBg="bg-amber-400/10"
          />
        </section>

        {/* â”€â”€ Chart panel — area + lines, legend toggles, hover tooltip â”€â”€â”€â”€â”€ */}
        <section className="bg-[#111721] border border-[#1D2634] rounded-[10px]">
          <div className="flex items-center justify-between gap-3.5 flex-wrap px-4 py-3.5 border-b border-[#1D2634]">
            <div>
              <h2 className="text-sm font-semibold text-[#E8EEF6]">Traffic over time</h2>
              <p className="text-xs text-[#8695A8] mt-0.5">Impressions, unique wins and conversions per day</p>
            </div>
            <div className="flex gap-1.5 flex-wrap">
              {([
                { k: 'imp' as const, label: 'Impressions', color: '#3B82F6' },
                { k: 'uni' as const, label: 'Unique wins', color: '#8B5CF6' },
                { k: 'conv' as const, label: 'Conversions', color: '#F59E0B' },
              ]).map(item => (
                <button
                  key={item.k}
                  onClick={() => toggleSeries(item.k)}
                  className={`inline-flex items-center gap-1.5 bg-[#0D131C] border border-[#1D2634] rounded-md px-2.5 py-1.5 text-xs text-[#8695A8] transition-opacity ${series[item.k] ? '' : 'opacity-40'}`}
                >
                  <i className="w-2 h-2 rounded-[2px] flex-none" style={{ background: item.color }} />
                  {item.label}
                </button>
              ))}
            </div>
          </div>
          <div className="px-2.5 pt-3.5 pb-1.5">
            {chartData.length === 0 ? (
              <div className="flex items-center justify-center h-40 text-[#5C6B7E] text-sm">
                {filterActive ? 'No data for the selected platforms' : 'No data available'}
              </div>
            ) : (
              <div className="relative">
                <svg
                  viewBox={`0 0 ${chartW} ${chartH}`}
                  className="block w-full h-auto"
                  onMouseMove={onChartMove}
                  onMouseLeave={() => setHoverIdx(null)}
                >
                  <defs>
                    <linearGradient id="impArea" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0" stopColor="#3B82F6" stopOpacity="0.28" />
                      <stop offset="1" stopColor="#3B82F6" stopOpacity="0" />
                    </linearGradient>
                  </defs>

                  {/* grid + dual axes */}
                  {[0, 0.25, 0.5, 0.75, 1].map((t, i) => {
                    const y = padT + plotH - t * plotH
                    return (
                      <g key={i}>
                        <line x1={padL} y1={y} x2={chartW - padR} y2={y} stroke="rgba(232,238,246,.07)" />
                        <text x={padL - 10} y={y + 4} textAnchor="end" fontSize="11" fill="#5C6B7E">
                          {Math.round(maxImp * t) >= 1000 ? `${(Math.round(maxImp * t) / 1000).toFixed(0)}K` : Math.round(maxImp * t)}
                        </text>
                        <text x={chartW - padR + 10} y={y + 4} fontSize="11" fill="#5C6B7E">
                          {Math.round(maxUni * t)}
                        </text>
                      </g>
                    )
                  })}

                  {/* impressions area + line */}
                  {series.imp && (
                    <>
                      <path d={areaPath} fill="url(#impArea)" />
                      <path d={impPath} fill="none" stroke="#3B82F6" strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round" />
                      <circle cx={xOf(chartData.length - 1)} cy={yImp(chartData[chartData.length - 1].clicks)} r="4" fill="#3B82F6" />
                    </>
                  )}
                  {series.uni && (
                    <path d={uniPath} fill="none" stroke="#8B5CF6" strokeWidth="1.8" strokeLinejoin="round" />
                  )}
                  {series.conv && (
                    <path d={convPath} fill="none" stroke="#F59E0B" strokeWidth="1.8" strokeDasharray="4 4" />
                  )}

                  {/* x labels */}
                  {chartData.map((r, i) => {
                    const every = chartData.length > 20 ? 5 : chartData.length > 9 ? 2 : 1
                    if (i % every && i !== chartData.length - 1) return null
                    return (
                      <text key={`x-${i}`} x={xOf(i)} y={chartH - 8} textAnchor="middle" fontSize="11" fill="#5C6B7E">
                        {fmtShort(r.date)}
                      </text>
                    )
                  })}

                  {/* hover crosshair + marker */}
                  {hovered !== null && (
                    <g>
                      <line x1={xOf(hoverIdx!)} y1={padT} x2={xOf(hoverIdx!)} y2={padT + plotH} stroke="#8695A8" strokeOpacity="0.35" />
                      <circle cx={xOf(hoverIdx!)} cy={yImp(chartData[hoverIdx!].clicks)} r="4.5" fill="#111721" stroke="#3B82F6" strokeWidth="2" />
                    </g>
                  )}
                </svg>

                {/* tooltip */}
                {hovered && (
                  <div
                    className="absolute pointer-events-none -translate-x-1/2 z-10 bg-[#0D131C] border border-[#26313F] rounded-lg px-2.5 py-2 text-xs whitespace-nowrap shadow-[0_8px_24px_rgba(0,0,0,0.35)]"
                    style={{
                      left: `${(xOf(hoverIdx!) / chartW) * 100}%`,
                      top: `${(yImp(hovered.clicks) / chartH) * 100}%`,
                      transform: 'translate(-50%, -110%)',
                    }}
                  >
                    <div className="text-[#8695A8] text-[11.5px] mb-1.5">{fmtDate(hovered.date)}</div>
                    {series.imp && (
                      <div className="flex items-center justify-between gap-4">
                        <span className="inline-flex items-center gap-1.5 text-[#8695A8]"><i className="w-[7px] h-[7px] rounded-[2px]" style={{ background: '#3B82F6' }} />Impressions</span>
                        <b className="font-semibold tabular-nums">{hovered.clicks.toLocaleString()}</b>
                      </div>
                    )}
                    {series.uni && (
                      <div className="flex items-center justify-between gap-4">
                        <span className="text-[#8695A8] inline-flex items-center gap-1.5"><i className="w-[7px] h-[7px] rounded-[2px]" style={{ background: '#8B5CF6' }} />Unique</span>
                        <b className="font-semibold tabular-nums">{hovered.unique_wins.toLocaleString()}</b>
                      </div>
                    )}
                    {series.conv && (
                      <div className="flex items-center justify-between gap-4">
                        <span className="text-[#8695A8] inline-flex items-center gap-1.5"><i className="w-[7px] h-[7px] rounded-[2px]" style={{ background: '#F59E0B' }} />Conversions</span>
                        <b className="font-semibold tabular-nums">{hovered.conversions.toLocaleString()}</b>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </section>

        {/* Platforms share + Country share (two-column row) */}
        <section className="grid md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-4">
          {/* Platform share bars */}
          <div className="bg-[#111721] border border-[#1D2634] rounded-[10px]">
            <div className="px-4 py-3.5 border-b border-[#1D2634]">
              <h2 className="text-sm font-semibold text-[#E8EEF6]">Top platforms</h2>
              <p className="text-xs text-[#8695A8] mt-0.5">Share of total clicks</p>
            </div>
            <div className="px-4 pt-1.5 pb-3.5">
              {platformChips.length === 0 ? (
                <p className="text-sm text-[#5C6B7E] py-6 text-center">No platform data</p>
              ) : (
                (() => {
                  const top = Math.max(...platformChips.map(c => c.value), 1)
                  return platformChips.map(c => (
                    <button
                      key={c.key}
                      onClick={() => togglePlatform(c.key)}
                      className="w-full text-left grid grid-cols-[1fr_64px] gap-3 items-center py-2 border-b border-[#1D2634] last:border-b-0 group"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2.5 text-[13px]">
                          <span className="w-5 h-3.5 rounded-[3px] bg-white/[0.04] border border-[#1D2634] grid place-items-center text-[9px] font-semibold text-[#5C6B7E] uppercase">
                            {c.key.slice(0, 2)}
                          </span>
                          <span className={filterActive && platformFilters.has(c.key) ? 'text-[#E8EEF6]' : 'text-[#C7D2E0]'}>{c.label}</span>
                        </div>
                        <div className="relative h-[5px] rounded-[3px] bg-white/[0.04] mt-1.5 overflow-hidden">
                          <span
                            className="absolute inset-y-0 left-0 rounded-[3px] bg-[#3B82F6] transition-all"
                            style={{ width: `${(c.value / top) * 100}%` }}
                          />
                        </div>
                      </div>
                      <span className="text-right text-[12.5px] text-[#8695A8] tabular-nums">
                        {((c.value / Math.max(stats.total_impressions, 1)) * 100).toFixed(1)}%
                      </span>
                    </button>
                  ))
                })()
              )}
              {filterActive && (
                <button
                  onClick={() => setPlatformFilters(new Set())}
                  className="mt-2 text-xs text-[#3B82F6] hover:underline"
                >
                  Clear platform filter
                </button>
              )}
            </div>
          </div>

          {/* Country share bars — country-based stats (example style) */}
          {prefs.show_country !== false && (
            <div className="bg-[#111721] border border-[#1D2634] rounded-[10px]">
              <div className="px-4 py-3.5 border-b border-[#1D2634]">
                <h2 className="text-sm font-semibold text-[#E8EEF6]">Top countries</h2>
                <p className="text-xs text-[#8695A8] mt-0.5">Clicks by country</p>
              </div>
              <div className="px-4 pt-1.5 pb-3.5">
                {(stats.country_breakdown?.length ?? 0) === 0 ? (
                  <p className="text-sm text-[#5C6B7E] py-6 text-center">No country data</p>
                ) : (
                  (() => {
                    const countries = stats.country_breakdown || []
                    const top = Math.max(...countries.map(c => c.clicks), 1)
                    return countries.map(c => (
                      <div
                        key={c.country_code}
                        className="grid grid-cols-[1fr_110px] gap-3 items-center py-2 border-b border-[#1D2634] last:border-b-0"
                      >
                        <div className="min-w-0">
                          <div className="flex items-center gap-2.5 text-[13px]">
                            <span className="w-6 h-3.5 rounded-[3px] bg-white/[0.04] border border-[#1D2634] grid place-items-center text-[9px] font-semibold text-[#5C6B7E] uppercase">
                              {c.country_code === 'UNKNOWN' ? '??' : c.country_code.slice(0, 2)}
                            </span>
                            <span className="text-[#C7D2E0] truncate">{c.country}</span>
                          </div>
                          <div className="relative h-[5px] rounded-[3px] bg-white/[0.04] mt-1.5 overflow-hidden">
                            <span
                              className="absolute inset-y-0 left-0 rounded-[3px] bg-[#8B5CF6] transition-all"
                              style={{ width: `${(c.clicks / top) * 100}%` }}
                            />
                          </div>
                        </div>
                        <div className="text-right text-[12.5px] text-[#8695A8] tabular-nums flex items-baseline justify-end gap-2">
                          <b className="text-[#E8EEF6] font-medium">{c.clicks.toLocaleString()}</b>
                          <span className="text-[11px] text-[#5C6B7E]">{c.share_pct?.toFixed(1)}%</span>
                        </div>
                      </div>
                    ))
                  })()
                )}
              </div>
            </div>
          )}
        </section>

        {/* Daily breakdown — FULL width so every column fits with no dead space */}
        <section className="bg-[#111721] border border-[#1D2634] rounded-[10px] overflow-hidden">
          <div className="px-4 py-3.5 border-b border-[#1D2634]">
            <h2 className="text-sm font-semibold text-[#E8EEF6]">Daily breakdown</h2>
            <p className="text-xs text-[#8695A8] mt-0.5">
              {filterActive ? 'Filtered by selected platforms' : 'Valid clicks per OS and conversions per day'}
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse table-fixed">
                <thead>
                  <tr>
                    <th className="w-[42%] px-3 py-2.5 text-left text-[11.5px] font-medium text-[#8695A8] bg-[#0D131C] border-b border-[#1D2634]">Date</th>
                    {prefs.show_impressions !== false && (
                      <th className="px-3 py-2.5 text-right text-[11.5px] font-medium text-[#8695A8] bg-[#0D131C] border-b border-[#1D2634]">Impressions</th>
                    )}
                    {prefs.show_windows_clicks !== false && (
                      <th className="px-3 py-2.5 text-right text-[11.5px] font-medium text-[#8695A8] bg-[#0D131C] border-b border-[#1D2634]">Valid Windows</th>
                    )}
                    {prefs.show_mac_clicks !== false && (
                      <th className="px-3 py-2.5 text-right text-[11.5px] font-medium text-[#8695A8] bg-[#0D131C] border-b border-[#1D2634]">Valid Mac</th>
                    )}
                    {prefs.show_android_clicks !== false && (
                      <th className="px-3 py-2.5 text-right text-[11.5px] font-medium text-[#8695A8] bg-[#0D131C] border-b border-[#1D2634]">Valid Android</th>
                    )}
                    {prefs.show_conversions !== false && (
                      <th className="px-3 py-2.5 text-right text-[11.5px] font-medium text-[#8695A8] bg-[#0D131C] border-b border-[#1D2634]">Conv.</th>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {filteredRows.slice(0, 10).map((row, i) => {
                    const maxImpRow = Math.max(...filteredRows.map(r => r.clicks), 1)
                    return (
                      <tr key={row.date} className="hover:bg-white/[0.03] transition-colors">
                        <td className="px-3 py-2.5 text-[13px] text-[#8695A8] whitespace-nowrap">
                          {fmtDate(row.date)}
                          {i === 0 && <span className="ml-2 text-[10.5px] text-[#3B82F6] bg-[#3B82F6]/15 px-1.5 py-0.5 rounded">latest</span>}
                          {row.date === stats.peak_day_date && <span className="ml-2 text-[10.5px] text-[#F59E0B] bg-[#F59E0B]/10 px-1.5 py-0.5 rounded">peak</span>}
                        </td>
                        {prefs.show_impressions !== false && (
                          <td className="px-3 py-2.5 text-right text-[13px] tabular-nums text-[#E8EEF6]">
                            {row.clicks.toLocaleString()}
                            <span
                              className="inline-block h-1 rounded-[2px] bg-[#3B82F6] opacity-35 ml-2 align-middle"
                              style={{ width: Math.round((row.clicks / maxImpRow) * 40) }}
                            />
                          </td>
                        )}
                        {/* OS valid-click columns — admin picks which OSes to expose */}
                        {prefs.show_windows_clicks !== false && (
                          <td className="px-3 py-2.5 text-right text-[13px] tabular-nums text-[#E8EEF6]">{row.windows_clicks.toLocaleString()}</td>
                        )}
                        {prefs.show_mac_clicks !== false && (
                          <td className="px-3 py-2.5 text-right text-[13px] tabular-nums text-[#E8EEF6]">{row.mac_clicks.toLocaleString()}</td>
                        )}
                        {prefs.show_android_clicks !== false && (
                          <td className="px-3 py-2.5 text-right text-[13px] tabular-nums text-[#E8EEF6]">{row.android_clicks.toLocaleString()}</td>
                        )}
                        {prefs.show_conversions !== false && (
                          <td className={`px-3 py-2.5 text-right text-[13px] tabular-nums ${row.conversions ? 'text-[#E8EEF6]' : 'text-[#5C6B7E]'}`}>
                            {row.conversions.toLocaleString()}
                          </td>
                        )}
                      </tr>
                    )
                  })}
                  {filteredRows.length === 0 && (
                    <tr><td colSpan={visibleColCount} className="px-4 py-8 text-center text-sm text-[#5C6B7E]">No data in this range</td></tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="px-4 py-2.5 text-xs text-[#5C6B7E] flex justify-between gap-2.5 flex-wrap border-t border-[#1D2634]">
              <span>Showing {Math.min(10, filteredRows.length)} of {filteredRows.length} days</span>
              <span>{stats.date_range}</span>
            </div>
        </section>
      </main>

      <footer className="border-t border-[#1D2634]">
        <div className="max-w-[1280px] mx-auto px-5 py-5 flex items-center justify-center text-xs text-[#5C6B7E]">
          <span>All times in UTC</span>
        </div>
      </footer>
    </div>
  )
}
