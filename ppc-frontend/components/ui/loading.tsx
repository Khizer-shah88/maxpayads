export function Spinner({ size = 20 }: { size?: number }) {
  return (
    <div
      className="rounded-full border-2 animate-spin"
      style={{ width: size, height: size, borderColor: '#E5E7EB', borderTopColor: '#DC2626' }}
    />
  )
}

export function PageLoader() {
  return (
    <div className="fixed inset-0 bg-white/80 backdrop-blur-sm z-50 flex items-center justify-center">
      <div className="flex flex-col items-center gap-4">
        <Spinner size={48} />
        <p className="text-gray-500 text-sm">Loading...</p>
      </div>
    </div>
  )
}

export function SkeletonRow({ cols = 5 }: { cols?: number }) {
  return (
    <tr>
      {Array.from({ length: cols }).map((_, i) => (
        <td key={i} className="px-4 py-3">
          <div className="shimmer h-4 rounded w-full" />
        </td>
      ))}
    </tr>
  )
}
