"""One hostname, one role. Shared by the API and the Next.js entry gate."""
import re

from app.config import settings
from app.core.glossary import normalize_domain_type
from app.services.domain_service import normalize_domain


def portal_hosts():
    return {normalize_domain(h) for h in settings.PORTAL_HOSTNAMES.split(',') if h.strip()}


def stored_host_spellings(host):
    return [host, f'https://{host}', f'http://{host}', f'https://{host}/', f'http://{host}/']


async def stats_host(db, link=None):
    """No request-origin fallback: a stats hostname must be explicitly assigned."""
    custom = normalize_domain((link or {}).get('stats_domain', ''))
    if custom:
        return custom
    setting = await db.system_settings.find_one({'key': 'stats_domain'})
    return normalize_domain((setting or {}).get('value', ''))


async def domain_role(db, host):
    host = normalize_domain(host)
    if not host:
        return None
    if host in portal_hosts():
        return 'portal'
    doc = await db.redirection_domains.find_one({'domain': host})
    if doc:
        return normalize_domain_type(doc.get('domain_type')) if doc.get('status') == 'active' else None
    if host == await stats_host(db):
        return 'stats'
    link = await db.direct_links.find_one({'stats_domain': {'$in': stored_host_spellings(host)}})
    return 'stats' if link else None


async def validate_stats_domain(db, value):
    host = normalize_domain(value)
    if not host:
        return ''
    if not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}', host):
        raise ValueError('Enter a valid stats hostname')
    if host in portal_hosts() or await db.redirection_domains.find_one({'domain': host}):
        raise ValueError('This hostname already has a portal or redirection role')
    return host


async def allow_path(db, host, path):
    """Return the role when the route is allowed, otherwise None (empty 404)."""
    role = await domain_role(db, host)
    if not role:
        return None
    path = '/' + path.lstrip('/')
    if path.startswith('/api/'):
        path = path[4:]
    if path.startswith('/public-stats/'):
        if role != 'stats':
            return None
        share_id = path[len('/public-stats/'):].rstrip('/')
        link = await db.direct_links.find_one({'stats_share_id': share_id})
        # Unknown shares may render the ordinary expired-link message, but a
        # valid share can only be opened on its exact configured hostname.
        return role if not link or normalize_domain(host) == await stats_host(db, link) else None
    if path in ('/click', '/go', '/ad.js') or path.startswith('/go/'):
        return role if role == 'anchor' else None
    if path.startswith('/d/'):
        return role if role in ('inter', 'prelander') else None
    if path.startswith('/_auth/'):
        return role if role == 'prelander' else None
    if path.startswith('/prelander/'):
        action = path[len('/prelander/'):]
        if action == 'preview':
            return role if role == 'portal' else None
        if action.startswith('hop/'):
            return role if role == 'inter' else None
        if action.startswith(('_auth/', 'resolve/', 'session-check', 'claim', 'render', 'data')):
            return role if role == 'prelander' else None
        return role if role in ('inter', 'prelander') else None
    # Assets remain available on registered hosts, including worker updates.
    if path.startswith(('/_next/', '/uploads/')) or re.search(r'\.(?:js|css|mp4|webm|png|jpg|jpeg|gif|ico|svg|woff2?|webmanifest)$', path):
        return role
    if path in ('/', '/clean-shell'):
        return role if role in ('portal', 'prelander') or (path == '/' and role == 'anchor') else None
    return role if role == 'portal' else None
