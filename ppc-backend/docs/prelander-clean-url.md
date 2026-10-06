# Prelander clean URL behavior

The final handoff now uses this flow:

```
/_auth/{one-time-token}
  -> create the existing HttpOnly session cookie
  -> 302 /d/session
  -> validate the session and serve the prelander shell
  -> claim the arrival and resolve the selected template/offer
  -> history.replaceState({}, '', '/')
```

The visible `/` on a registered prelander domain always returns an empty,
non-cacheable HTTP 204, including when a valid session cookie is present.
It does not redirect or serve the portal. Authorization checks still protect
the entry route and the content APIs. Portal and anchor roots keep their
existing behavior.

In Chrome, a same-tab navigation to `view-source:https://prelander-domain/`
receives 204 without replacing the displayed prelander. A fresh tab remains
blank. Reload also requests `/` and receives 204; Chrome retains the displayed
document in the browser test. This intentionally changes the former behavior
where a root reload re-fetched prelander content. Browser UI behavior can vary;
the server guarantee is the empty 204 response.

The URL is cleaned only after data resolves. A temporary failure on the entry
route can therefore be retried through `/d/session`. Existing template scripts,
buttons, campaign selection, and attribution remain in their original flow.
The arrival shell no longer registers the source-deterrent service worker or
sets its `x-sd` marker. Already-installed workers pass through the unmarked
response instead of replaying the arrival document. Other uses of that worker
are unchanged. The empty response includes `Content-Type: text/html`:
Chrome otherwise treats a worker-forwarded 204 with `nosniff` and no MIME
type as a download. The browser test checks that no download starts.

This implements the clean-URL/source-view behavior, not the competitor's
keyboard suppression, DevTools erasure, or replacement of button actions.
Delivered HTML and authorized API responses remain inspectable.

## Verification

Backend tests (from `ppc-backend`, with the project Python environment):

```
python -m pytest tests/test_prelander_auth.py tests/test_one_use_redirect_hops.py tests/test_middleware_cookie_regression.py -q
```

Frontend checks (from `ppc-frontend`):

```
npm ci
node --test tests/prelander-session.test.cjs tests/source-deterrent.test.cjs tests/admin-auth.test.cjs
npm run build
npm run test:prelander:browser
```

The browser test uses installed Chrome by default. `PLAYWRIGHT_CHANNEL` may
select another installed Chromium browser such as `msedge`. `PYTHON` can point
to an alternative Python executable; otherwise the test uses the backend's
`.venv`. That environment needs the project's test dependencies and uvicorn.

The runner starts a production Next build, a loopback-only FastAPI fixture,
and a local HTTP proxy mirroring nginx's Host-preserving `/api/` and `/_auth/`
routes on available ports. It exercises the real prelander routes, authorization
service, template renderer, middleware, and browser. Redis/database contents
and host-role lookup use in-memory fixtures; the offer navigation is intercepted.
It does not use production credentials or contact a live campaign. Screenshots,
HTTP navigation statuses, and server logs are saved to the printed temporary
artifact directory. All test servers are stopped afterward.

Deploy the frontend and backend changes together. The backend handoff and its
Next fallback must both send arrivals to `/d/session` before the root becomes
204. Local checks do not verify production DNS, TLS, nginx, or CDN rules. No
nginx path changes are needed: existing `/_auth/` and `/` proxy locations cover
the new flow. Explicit CDN rules must not cache the entry or 204 responses.
