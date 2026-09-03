// Lightweight runtime-safe formatting and base64 helpers
export const fmtNum = (n: any): string => {
  if (typeof n === 'number' && Number.isFinite(n)) return n.toLocaleString()
  const parsed = Number(n)
  if (!Number.isFinite(parsed)) return '0'
  return parsed.toLocaleString()
}

export const fmtFixed = (n: any, digits = 2): string => {
  const num = Number(n)
  if (!Number.isFinite(num)) return (digits > 0 ? `0.${'0'.repeat(digits)}` : '0')
  return num.toFixed(digits)
}

export const fmtPercent = (n: any, digits = 2): string => {
  const num = Number(n)
  if (!Number.isFinite(num)) return (digits === 0 ? '0' : `0.${'0'.repeat(digits)}`)
  return num.toFixed(digits)
}

export const safeBtoa = (s: any): string => {
  try {
    if (typeof window !== 'undefined' && typeof window.btoa === 'function') return window.btoa(String(s))
    // Node.js / server fallback
    if (typeof Buffer !== 'undefined') return Buffer.from(String(s)).toString('base64')
  } catch {}
  try {
    return encodeURIComponent(String(s))
  } catch {
    return ''
  }
}

export const safeAtob = (s: any): string => {
  try {
    if (typeof window !== 'undefined' && typeof window.atob === 'function') return window.atob(String(s))
    if (typeof Buffer !== 'undefined') return Buffer.from(String(s), 'base64').toString('utf-8')
  } catch {}
  try {
    return decodeURIComponent(String(s))
  } catch {
    return ''
  }
}

// intentionally no default export
