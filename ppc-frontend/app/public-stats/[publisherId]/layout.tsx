import type { Metadata } from 'next'

// White-label metadata — no brand names, no taglines
export const metadata: Metadata = {
  title: 'Stats',
  description: '',
}

export default function PublicStatsLayout({ children }: { children: React.ReactNode }) {
  return children
}