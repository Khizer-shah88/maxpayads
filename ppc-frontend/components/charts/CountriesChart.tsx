'use client'

import { Chart as ChartJS, ArcElement, Tooltip, Legend } from 'chart.js'
import { Doughnut } from 'react-chartjs-2'
import type { TopCountry } from '@/types'

ChartJS.register(ArcElement, Tooltip, Legend)

const COLORS = ['#DC2626', '#EF4444', '#F87171', '#1F2937', '#374151', '#6B7280', '#16A34A', '#F59E0B', '#3B82F6', '#8B5CF6']

interface CountriesChartProps {
  data: TopCountry[]
  loading?: boolean
}

export default function CountriesChart({ data, loading }: CountriesChartProps) {
  if (loading) return <div className="h-48 shimmer rounded-lg" />
  if (!data.length) return <div className="h-48 flex items-center justify-center text-gray-400 text-sm">No data</div>

  const top10 = data.slice(0, 10)
  const chartData = {
    labels: top10.map(c => `${c.country_code} - ${c.country_name}`),
    datasets: [{
      data: top10.map(c => c.clicks),
      backgroundColor: COLORS.slice(0, top10.length),
      borderColor: '#fff',
      borderWidth: 2,
    }],
  }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { position: 'right' as const, labels: { color: '#374151', font: { size: 11 }, padding: 8 } },
      tooltip: {
        backgroundColor: '#fff',
        borderColor: '#E5E7EB',
        borderWidth: 1,
        titleColor: '#000',
        bodyColor: '#374151',
      },
    },
  }

  return <div style={{ height: '220px' }}><Doughnut data={chartData} options={options as any} /></div>
}
