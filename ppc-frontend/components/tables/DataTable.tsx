'use client'

import { useRef } from 'react'
import { SkeletonRow } from '@/components/ui/loading'
import { ChevronLeft, ChevronRight } from 'lucide-react'

interface Column<T> {
  key: string
  label: string
  render?: (row: T) => React.ReactNode
}

interface PaginationProps {
  page: number
  total: number
  limit: number
  onPageChange: (page: number) => void
}

interface DataTableProps<T> {
  columns: Column<T>[]
  data: T[]
  loading?: boolean
  pagination?: PaginationProps
  emptyMessage?: string
  keyField?: string
  compact?: boolean
}

export default function DataTable<T extends Record<string, any>>({
  columns, data, loading = false, pagination, emptyMessage = 'No data found', keyField = 'id', compact = false
}: DataTableProps<T>) {
  const pages = pagination ? Math.ceil(pagination.total / pagination.limit) : 1
  const scrollRef = useRef<HTMLDivElement>(null)

  const scroll = (dir: 'left' | 'right') => {
    if (!scrollRef.current) return
    scrollRef.current.scrollBy({ left: dir === 'left' ? -300 : 300, behavior: 'smooth' })
  }

  const thClass = compact
    ? 'px-2 py-1.5 text-left whitespace-nowrap text-[10px] font-semibold text-gray-500 uppercase tracking-wider'
    : 'px-4 py-3 text-left whitespace-nowrap'
  const tdClass = compact
    ? 'px-2 py-1 text-[11px] whitespace-nowrap leading-tight'
    : 'px-4 py-3 text-sm whitespace-nowrap'

  return (
    <div>
      {/* Scroll buttons */}
      <div className="flex items-center gap-1.5 mb-1.5 justify-end">
        <button onClick={() => scroll('left')}
          className="p-1 rounded border border-gray-200 text-gray-400 hover:text-gray-700 hover:bg-gray-50 transition-colors">
          <ChevronLeft size={12} />
        </button>
        <span className="text-[10px] text-gray-300">Scroll</span>
        <button onClick={() => scroll('right')}
          className="p-1 rounded border border-gray-200 text-gray-400 hover:text-gray-700 hover:bg-gray-50 transition-colors">
          <ChevronRight size={12} />
        </button>
      </div>

      <div ref={scrollRef} className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full min-w-[900px]">
          <thead>
            <tr className={compact ? 'bg-gray-50' : ''}>
              {columns.map(col => (
                <th key={col.key} className={thClass}>{col.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} cols={columns.length} />)
            ) : data.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className={`px-4 ${compact ? 'py-6' : 'py-12'} text-center text-gray-400 text-xs`}>
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              data.map((row, i) => (
                <tr key={row[keyField] || i} className={compact ? 'hover:bg-gray-50/50' : ''}>
                  {columns.map(col => (
                    <td key={col.key} className={tdClass}>
                      {col.render ? col.render(row) : row[col.key]}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {pagination && pages > 1 && (
        <div className="flex items-center justify-between mt-2">
          <p className={`${compact ? 'text-[10px]' : 'text-sm'} text-gray-400`}>
            {((pagination.page - 1) * pagination.limit) + 1}–{Math.min(pagination.page * pagination.limit, pagination.total)} of {pagination.total}
          </p>
          <div className="flex items-center gap-0.5">
            <button
              onClick={() => pagination.onPageChange(pagination.page - 1)}
              disabled={pagination.page <= 1}
              className={`${compact ? 'p-1' : 'p-2'} rounded text-gray-500 hover:text-black hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed transition-colors`}
            >
              <ChevronLeft size={compact ? 12 : 16} />
            </button>
            {Array.from({ length: Math.min(pages, 7) }).map((_, i) => {
              const page = i + 1
              return (
                <button key={page} onClick={() => pagination.onPageChange(page)}
                  className={`${compact ? 'w-6 h-6 text-[10px]' : 'w-8 h-8 text-sm'} rounded font-medium transition-colors ${
                    page === pagination.page
                      ? 'bg-primary text-white'
                      : 'text-gray-600 hover:bg-gray-100'
                  }`}>
                  {page}
                </button>
              )
            })}
            <button
              onClick={() => pagination.onPageChange(pagination.page + 1)}
              disabled={pagination.page >= pages}
              className={`${compact ? 'p-1' : 'p-2'} rounded text-gray-500 hover:text-black hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed transition-colors`}
            >
              <ChevronRight size={compact ? 12 : 16} />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
