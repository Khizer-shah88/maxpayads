'use client'

import { TrendingUp, TrendingDown } from 'lucide-react'

interface StatCardProps {
  title: string
  value: string | number
  change?: number
  icon: React.ReactNode
  color?: 'primary' | 'secondary' | 'success' | 'warning' | 'danger'
  loading?: boolean
  prefix?: string
  suffix?: string
  delay?: number
}

const colorMap = {
  primary: { bg: 'bg-red-500/10', iconColor: 'text-red-500', accent: 'border-l-red-500' },
  secondary: { bg: 'bg-gray-500/10', iconColor: 'text-gray-500', accent: 'border-l-gray-500' },
  success: { bg: 'bg-emerald-500/10', iconColor: 'text-emerald-500', accent: 'border-l-emerald-500' },
  warning: { bg: 'bg-amber-500/10', iconColor: 'text-amber-500', accent: 'border-l-amber-500' },
  danger: { bg: 'bg-red-500/10', iconColor: 'text-red-500', accent: 'border-l-red-500' },
}

export default function StatCard({
  title, value, change, icon, color = 'primary', loading = false, prefix = '', suffix = '',
}: StatCardProps) {
  const colors = colorMap[color]

  if (loading) {
    return (
      <div className="bg-white rounded-xl border border-gray-100 p-5">
        <div className="shimmer h-4 w-24 rounded-lg mb-4" />
        <div className="shimmer h-8 w-32 rounded-lg mb-2" />
        <div className="shimmer h-3 w-20 rounded-lg" />
      </div>
    )
  }

  return (
    <div className={`bg-white rounded-xl border border-gray-100 p-5 hover:shadow-md transition-all duration-200 border-l-4 ${colors.accent}`}>
      <div className="flex items-start justify-between mb-3">
        <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${colors.bg}`}>
          <div className={colors.iconColor}>{icon}</div>
        </div>
        {change !== undefined && (
          <div className={`flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-full ${
            change >= 0 ? 'text-emerald-700 bg-emerald-50' : 'text-red-700 bg-red-50'
          }`}>
            {change >= 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
            {Math.abs(change).toFixed(1)}%
          </div>
        )}
      </div>
      <p className="text-gray-400 text-xs font-medium uppercase tracking-wider mb-1">{title}</p>
      <p className="text-2xl font-bold text-gray-900">
        {prefix}{typeof value === 'number' ? value.toLocaleString() : value}{suffix}
      </p>
    </div>
  )
}
