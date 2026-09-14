'use client'

import { useEffect, useState } from 'react'
import { Trash2, AlertTriangle, Loader2 } from 'lucide-react'

/**
 * ConfirmDialog — styled replacement for native window.confirm().
 *
 * Design matches the existing delete modals (Publishers / Redirection Domains):
 * red icon tile, centered text, optional "Type DELETE to confirm" gate.
 *
 * Usage:
 *   <ConfirmDialog
 *     open={!!deleteTarget}
 *     title="Delete Campaign"
 *     message={<>Delete <strong>{deleteTarget?.name}</strong>? This cannot be undone.</>}
 *     confirmLabel="Delete"
 *     loading={deleting}
 *     requireText="DELETE"   // omit for a simple Confirm/Cancel dialog
 *     onConfirm={handleDelete}
 *     onCancel={() => setDeleteTarget(null)}
 *   />
 */

interface ConfirmDialogProps {
  open: boolean
  title: string
  message: React.ReactNode
  confirmLabel?: string
  cancelLabel?: string
  /** Require typing this text (case-insensitive) before Confirm enables. */
  requireText?: string
  /** While true the confirm button shows a spinner and stays disabled. */
  loading?: boolean
  /** 'danger' = red (delete), 'warning' = amber (approve/regenerate), 'info' = neutral. */
  tone?: 'danger' | 'warning' | 'info'
  onConfirm: () => void
  onCancel: () => void
}

export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  requireText,
  loading = false,
  tone = 'danger',
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const [text, setText] = useState('')

  // Reset the typed confirmation whenever the dialog opens/closes
  useEffect(() => {
    if (open) setText('')
  }, [open])

  // Close on Escape
  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !loading) onCancel()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, loading, onCancel])

  if (!open) return null

  const toneStyles = {
    danger: { iconBg: 'bg-red-50', iconColor: 'text-red-600', btn: 'bg-red-600 hover:bg-red-700' },
    warning: { iconBg: 'bg-amber-50', iconColor: 'text-amber-600', btn: 'bg-amber-600 hover:bg-amber-700' },
    info: { iconBg: 'bg-blue-50', iconColor: 'text-blue-600', btn: 'bg-primary hover:bg-primary-dark' },
  }[tone]

  const Icon = tone === 'danger' ? Trash2 : AlertTriangle

  const inputOk = !requireText || text.toUpperCase() === requireText.toUpperCase()

  return (
    <div
      className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      onClick={() => !loading && onCancel()}
    >
      <div
        className="bg-white rounded-2xl p-6 w-full max-w-sm text-center shadow-2xl border border-gray-100"
        onClick={e => e.stopPropagation()}
      >
        <div className={`w-12 h-12 rounded-xl flex items-center justify-center mx-auto mb-4 ${toneStyles.iconBg}`}>
          <Icon className={toneStyles.iconColor} size={24} />
        </div>
        <h3 className="text-lg font-bold text-gray-900 mb-2">{title}</h3>
        <p className="text-gray-500 text-sm mb-4">{message}</p>

        {requireText && (
          <input
            value={text}
            onChange={e => setText(e.target.value)}
            placeholder={`Type ${requireText} to confirm`}
            autoFocus
            className="w-full px-4 py-2.5 border border-gray-200 rounded-xl text-sm text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-red-100 focus:border-red-300"
          />
        )}

        <div className="flex gap-3 mt-4">
          <button
            onClick={onConfirm}
            disabled={loading || !inputOk}
            className={`flex-1 ${toneStyles.btn} text-white py-2.5 rounded-xl text-sm font-semibold flex items-center justify-center gap-2 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors`}
          >
            {loading ? (
              <>
                <Loader2 size={16} className="animate-spin" /> Working…
              </>
            ) : (
              confirmLabel
            )}
          </button>
          <button
            onClick={onCancel}
            disabled={loading}
            className="flex-1 py-2.5 rounded-xl text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50 transition-colors"
          >
            {cancelLabel}
          </button>
        </div>
      </div>
    </div>
  )
}