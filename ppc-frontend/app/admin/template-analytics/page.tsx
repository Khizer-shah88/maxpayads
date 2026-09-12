'use client'

import { useEffect } from 'react'
import { BarChart2 } from 'lucide-react'
import Sidebar from '@/components/shared/Sidebar'
import { useAuth } from '@/lib/hooks/useAuth'

export default function TemplateAnalyticsPage() {
  const { initialize } = useAuth()
  useEffect(() => { initialize() }, [])

  return (
    <div className="flex min-h-screen bg-[#f8f9fb]">
      <Sidebar />
      <div className="flex-1 lg:ml-64 p-6 lg:p-8 min-w-0 overflow-x-hidden">
        <div className="mb-8 pt-12 lg:pt-0">
          <h1 className="text-2xl font-bold text-gray-900">Template Analytics</h1>
          <p className="text-gray-400 text-sm mt-0.5">Prelander template performance data</p>
        </div>
        <div className="bg-white rounded-2xl border border-gray-100 p-12 flex flex-col items-center justify-center text-center">
          <BarChart2 size={48} className="text-gray-200 mb-4" />
          <p className="text-gray-400 text-sm">No template analytics data yet.</p>
          <p className="text-gray-300 text-xs mt-1">Data will appear here once prelander templates receive traffic.</p>
        </div>
      </div>
    </div>
  )
}
