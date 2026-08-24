'use client'

import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler,
} from 'chart.js'
import { Line } from 'react-chartjs-2'
import type { ClickTrend } from '@/types'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler)

interface ClicksChartProps {
  data: ClickTrend[]
  loading?: boolean
  filter?: 'unique' | 'valid'
}

export default function ClicksChart({ data, loading, filter = 'unique' }: ClicksChartProps) {
  if (loading) return <div className="h-64 shimmer rounded-lg" />

  const datasets = filter === 'valid'
    ? [
        {
          label: 'Valid Clicks',
          data: data.map(d => d.valid_clicks),
          borderColor: '#16A34A',
          backgroundColor: 'rgba(22, 163, 74, 0.08)',
          fill: true,
          tension: 0.4,
          borderWidth: 2,
          pointBackgroundColor: '#16A34A',
          pointRadius: 4,
          pointHoverRadius: 6,
        },
      ]
    : [
        {
          label: 'Unique Clicks',
          data: data.map(d => d.clicks),
          borderColor: '#DC2626',
          backgroundColor: 'rgba(220, 38, 38, 0.08)',
          fill: true,
          tension: 0.4,
          borderWidth: 2,
          pointBackgroundColor: '#DC2626',
          pointRadius: 4,
          pointHoverRadius: 6,
        },
      ]

  const chartData = {
    labels: data.map(d => d.date),
    datasets,
  }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { labels: { color: '#374151', font: { size: 12 }, boxWidth: 12 } },
      tooltip: {
        backgroundColor: '#fff',
        borderColor: '#E5E7EB',
        borderWidth: 1,
        titleColor: '#000',
        bodyColor: '#374151',
        padding: 12,
      },
    },
    scales: {
      x: { grid: { color: '#F3F4F6' }, ticks: { color: '#6B7280', font: { size: 11 } } },
      y: { grid: { color: '#F3F4F6' }, ticks: { color: '#6B7280', font: { size: 11 } } },
    },
  }

  return <div style={{ height: '260px' }}><Line data={chartData} options={options as any} /></div>
}
