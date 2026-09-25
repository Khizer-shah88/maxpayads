"""Atomic, host-bound tickets for the configured Inter sequence."""
import hmac
import json
import secrets
import time

from app.services import prelander_auth_service as auth
from app.services.domain_access_service import domain_role
from app.services.domain_service import normalize_domain


async def issue_hop(redis, session, hosts, bypass_url=''):
    if not hosts or not session or not session.is_usable():
        return None
    token = 'h_' + secrets.token_urlsafe(32)
    ttl = min(60, session.expires_at - int(time.time()))
    if ttl <= 0:
        return None
    await redis.setex('redirect_hop:' + token, ttl, json.dumps({
        'session': session.token, 'hosts': hosts, 'bypass_url': bypass_url,
    }))
    return f'https://{hosts[0]}/d/{token}'


async def advance_hop(redis, db, token, host, ip, user_agent):
    if redis is None or not token.startswith('h_'):
        return None
    # GETDEL makes simultaneous requests, copied URLs and retries single-use.
    raw = await redis.getdel('redirect_hop:' + token)
    if not raw:
        return None
    data = json.loads(raw)
    hosts = data.get('hosts') or []
    if not hosts or normalize_domain(host) != hosts[0]:
        return None
    if await domain_role(db, host) != 'inter':
        return None
    session = await auth.get_session(data.get('session', ''), redis)
    if not session or not session.is_usable():
        return None
    if not hmac.compare_digest(session.user_agent, (user_agent or '')[:500]):
        return None
    if auth._ip_mode() == 'strict' and session.fingerprint != auth._fingerprint(ip, user_agent):
        return None
    if len(hosts) > 1:
        if await domain_role(db, hosts[1]) != 'inter':
            return None
        return await issue_hop(redis, session, hosts[1:], data.get('bypass_url', ''))
    if data.get('bypass_url'):
        return data['bypass_url']
    if await domain_role(db, session.prelander_host) != 'prelander':
        return None
    handoff = await auth.mint_handoff(session, redis, target_host=session.prelander_host)
    return f'https://{session.prelander_host}/_auth/{handoff}' if handoff else None
