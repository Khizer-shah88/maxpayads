Domain routing and publisher statistics
=====================================

Each public hostname has one role. Portal hosts come from PORTAL_HOSTNAMES;
Anchor, Inter and Prelander hosts come from active Redirection Domains; stats
hosts come from the global or publisher-specific stats-domain assignment.
Both FastAPI and Next.js enforce the same policy. Nginx checks it before
proxying requests, including static files, and closes denied connections
without serving a response (444). Pointing DNS at the server does not enroll
a domain. Bare and www hostnames are separate assignments.

Stats links require an explicitly configured stats hostname. A publisher's
custom hostname overrides the global stats host and is checked on the page
and API. Share, Copy and Preview use the canonical /public-stats/{share_id}
URL. Preview refreshes that URL before opening it. Saving a publisher's stats
domain updates their existing links; new links inherit the assignment.

The click pipeline retains the chain selected by its Anchor. Each Inter hop
gets a random ticket bound to the browser session, hostname and remaining
sequence. Redis GETDEL consumes each ticket atomically. Extra hops are visited
in order, then a separate one-use handoff creates the final Prelander session.
Bypass mode retains Anchor -> Inter -> campaign behavior. Tickets expire after
60 seconds; the configured chain cookie lifetime controls the underlying
session. Session validation is required, including on older chains whose
stored setting was disabled. Inactive/zero-weight prelanders are not used as
fallbacks when a chain's pool has no eligible destination.

Configuration requirements
--------------------------

- Set a dedicated global stats domain, or a custom domain per publisher.
  The homepage domain no longer serves public stats or click traffic.
- Use Inter domains for extra hops. Save changes to any older chain that used
  an Anchor or Prelander as a middle hop.
- Keep one active chain per Anchor; duplicate hosts in a chain are rejected.
- Deploy frontend, backend and nginx.prod.conf together. Production Compose
  passes PORTAL_HOSTNAMES to the backend as the authoritative portal list.

Publisher IDs display their public suffix (for example mJtCxLqp) consistently
across publisher tables, selections and public stats. The stored IDs, request
values and PUB_mJtCxLqp tracking parameters retain their existing format.
