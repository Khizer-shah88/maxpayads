import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Download Ready',
  description: 'Your file is ready to download.',
}

export default function PrelanderLayout({ children }: { children: React.ReactNode }) {
  return children
}
