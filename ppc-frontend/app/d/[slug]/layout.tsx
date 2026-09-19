import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Loading...',
  description: '',
}

export default function PrelanderLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <title>Loading...</title>
        <meta name="description" content="" />
      </head>
      <body>
        {children}
      </body>
    </html>
  )
}
