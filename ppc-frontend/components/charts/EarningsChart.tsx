'use client'

import { Chart as ChartJS, CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend } from 'chart.js'
import { Bar } from 'react-chartjs-2'
import type { ClickTrend } from '@/types'

ChartJS.register(CategoryScale, LinearScale, BarElement, Title, Tooltip, Legend)

interface EarningsChartProps {
  data: ClickTrend[]
  loading?: boolean
}

export default function EarningsChart({ data, loading }: EarningsChartProps) {
  if (loading) return <div className="h-48 shimmer rounded-lg" />

  const chartData = {
    labels: data.map(d => d.date),
    datasets: [{
      label: 'Earnings ($)',
      data: data.map(d => d.earnings),
      backgroundColor: 'rgba(220, 38, 38, 0.7)',
      borderColor: '#DC2626',
      borderWidth: 1,
      borderRadius: 4,
    }],
  }

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: '#fff',
        borderColor: '#E5E7EB',
        borderWidth: 1,
        titleColor: '#000',
        bodyColor: '#374151',
        callbacks: { label: (ctx: any) => `$${ctx.raw.toFixed(4)}` },
      },
    },
    scales: {
      x: { grid: { color: '#F3F4F6' }, ticks: { color: '#6B7280', font: { size: 11 } } },
      y: { grid: { color: '#F3F4F6' }, ticks: { color: '#6B7280', font: { size: 11 }, callback: (v: any) => `$${v}` } },
    },
  }

  return <div style={{ height: '200px' }}><Bar data={chartData} options={options as any} /></div>
}
