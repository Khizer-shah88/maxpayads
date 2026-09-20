import type { Metadata } from 'next'
import { sourceDeterrentScript } from '@/lib/source-deterrent-script'
import { Toaster } from 'sonner'
import './globals.css'

export const metadata: Metadata = {
  title: 'vertexmonetize - Premium Pay-Per-Click Advertising Platform',
  description: 'Monetize your website traffic with the leading vertexmonetize advertising network. High CPC rates, real-time analytics, and fast payouts.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  // Inline, never bundled: if this shipped in a bundle and the bundle failed to
  // load, the page would fall silent and the worker would navigate it -- firing
  // on exactly the users it should leave alone. '' when the feature is off.
  // Covers every app-router page, so every document that can receive the `x-sd`
  // marker also carries the heartbeat. Keep those two together.
  const deterrent = sourceDeterrentScript()

  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet" />
      </head>
      <body className="bg-white text-black antialiased">
        {deterrent ? <script dangerouslySetInnerHTML={{ __html: deterrent }} /> : null}
        {children}
        <Toaster
          theme="light"
          position="top-right"
          toastOptions={{
            style: {
              background: '#FFFFFF',
              border: '1px solid #E5E7EB',
              color: '#000000',
            },
          }}
        />
      </body>
    </html>
  )
}
