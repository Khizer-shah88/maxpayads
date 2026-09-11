interface BadgeProps {
  status: string
  className?: string
}

const statusConfig: Record<string, string> = {
  active: 'badge-active',
  valid: 'badge-valid',
  paid: 'badge-paid',
  approved: 'badge-active',
  pending: 'badge-pending',
  suspended: 'badge-suspended',
  invalid: 'badge-invalid',
  rejected: 'badge-suspended',
  paused: 'badge-pending',
  deleted: 'badge-suspended',
  // Banned/removed publishers: links keep redirecting, stats still record,
  // Direct Link Stats unavailable.
  banned: 'badge-invalid',
  removed: 'badge-suspended',
  desktop: 'bg-gray-100 text-gray-700 border border-gray-200',
  mobile: 'bg-blue-50 text-blue-700 border border-blue-200',
  tablet: 'bg-yellow-50 text-yellow-700 border border-yellow-200',
}

export function StatusBadge({ status, className }: BadgeProps) {
  const safeStatus = status || 'active'
  const badgeClass = statusConfig[safeStatus.toLowerCase()] || 'badge-pending'
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${badgeClass} ${className || ''}`}>
      {safeStatus.charAt(0).toUpperCase() + safeStatus.slice(1)}
    </span>
  )
}
