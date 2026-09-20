import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Loading...',
  description: '',
}

// A nested layout must NOT render <html>/<body> -- only the root layout may.
// This one did, so /d/[slug] was served with two nested <html> elements. The
// parser drops the inner pair and merges its attributes, so rendering is
// unchanged by this fix; the markup is simply valid now.
//
// The source-deterrent script is not here either: the root layout embeds it for
// every app-router page, and a second copy would register the worker twice.
export default function PrelanderLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>
}
