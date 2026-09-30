"""One hostname, one role. Shared by the API and the Next.js entry gate."""
import re
from functools import lru_cache

from app.config import settings
from app.core.glossary import normalize_domain_type
from app.services.domain_service import normalize_domain


def portal_hosts():
    return _portal_hosts(settings.PORTAL_HOSTNAMES)


@lru_cache(maxsize=8)
def _portal_hosts(value):
    return frozenset(normalize_domain(h) for h in value.split(',') if h.strip())


def stored_host_spellings(host):
    return [host, f'https://{host}', f'http://{host}', f'https://{host}/', f'http://{host}/']


async def stats_host(db, link=None, redis=None):
    """No request-origin fallback: a stats hostname must be explicitly assigned."""
    from app.cache.kv_cache import cached_json, STATS_HOST_KEY
    from app.config import settings

    custom = normalize_domain((link or {}).get('stats_domain', ''))
    if custom:
        return custom

    async def _load():
        setting = await db.system_settings.find_one({'key': 'stats_domain'})
        return normalize_domain((setting or {}).get('value', ''))

    return await cached_json(redis, STATS_HOST_KEY, settings.KV_TTL_STATS_HOST, _load)


async def domain_role(db, host, redis=None):
    """Resolve a hostname's role, briefly cached (KV_TTL_DOMAIN_ROLE).

    This lookup runs for every page view (nginx auth_request → /domain-access)
    and several times per click (hop validation, prelander handoff). The DB
    path here used to be 2-3 queries per hit; the cache keeps admin domain
    edits visible within the TTL. Pass redis=None to always hit the DB.
    """
    from app.cache.kv_cache import cached_json
    from app.config import settings

    host = normalize_domain(host)
    if not host:
        return None
    if host in portal_hosts():
        return 'portal'

    async def _load():
        doc = await db.redirection_domains.find_one({'domain': host})
        if doc:
            role = (normalize_domain_type(doc.get('domain_type'))
                    if doc.get('status') == 'active' else None)
            if role:
                return role
        if host == await stats_host(db, redis=redis):
            return 'stats'
        link = await db.direct_links.find_one({'stats_domain': {'$in': stored_host_spellings(host)}})
        return 'stats' if link else None

    return await cached_json(
        redis, f'kv:drole:{host}', settings.KV_TTL_DOMAIN_ROLE, _load,
    )


async def validate_stats_domain(db, value):
    host = normalize_domain(value)
    if not host:
        return ''
    if not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}', host):
        raise ValueError('Enter a valid stats hostname')
    if host in portal_hosts() or await db.redirection_domains.find_one({'domain': host}):
        raise ValueError('This hostname already has a portal or redirection role')
    return host


async def allow_path(db, host, path, redis=None):
    """Return the role when the route is allowed, otherwise None (empty 404)."""
    role = await domain_role(db, host, redis=redis)
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
        return role if not link or normalize_domain(host) == await stats_host(db, link, redis=redis) else None
    if path in ('/click', '/go', '/ad.js') or path.startswith('/go/'):
        return role if role == 'anchor' else None
    if path.startswith('/d/'):
        return role if role in ('inter', 'prelander') else None
    if path == '/prelander-fallback':
        return role if role in ('portal', 'inter', 'prelander') else None
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
