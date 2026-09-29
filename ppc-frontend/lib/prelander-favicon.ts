/**
 * Template favicon on prelander surfaces.
 *
 * The browser tab's favicon comes from <link rel="icon"> in the document
 * HEAD. The admin sets it two ways per template:
 *   1. Their own <link rel=icon> inside a full-HTML template — document.write
 *      renders it verbatim, nothing to do here.
 *   2. A `favicon_url` field (or as the fallback when option 1 is missing) —
 *      built-in layouts + clean-shell inject it client-side: favicons are
 *      re-scanned whenever a link node is added to <head>, so a dynamic
 *      injection works even after hydration.
 *
 * Accepted input shapes (normalized server-side, re-guarded client-side):
 *   https://example.com/a.png · example.com/a.png · https://example[.]com/a.png
 *   (the anti-scam bracket spelling is cleaned to a fetchable URL)
 */

function extractFromSnippet(value: string): string {
  if (/<link/i.test(value)) {
    const link = value.match(/<link\b[^>]*>/i)?.[0] || ''
    const href = link.match(/href\s*=\s*["']([^"']+)["']/i)?.[1] || ''
    return href.trim()
  }
  return value.trim()
}

function normalizeFaviconUrl(value: unknown): string {
  if (typeof value !== 'string') return ''
  let raw = extractFromSnippet(value)
  if (!raw) return ''
  // Anti-scam bracket spelling → real hostname.
  raw = raw.replace(/\[\.\]/g, '.')
  if (!/^https?:\/\//i.test(raw)) raw = `https://${raw.replace(/^\/+/, '')}`
  if (!/^https:\/\//i.test(raw)) return '' // https only on prelander domains
  return raw
}

/** Idempotent: replaces our previous injection before writing a new one. */
export function applyFavicon(value: unknown): void {
  if (typeof document === 'undefined') return
  const url = normalizeFaviconUrl(value)
  if (!url) return
  const mark = 'data-pl-favicon'
  document.getElementById(mark)?.remove()
  if (!document.head) return
  const link = document.createElement('link')
  link.setAttribute(mark, '1')
  link.rel = 'icon'
  link.type = 'image/png'
  link.href = url
  document.head.appendChild(link)
}