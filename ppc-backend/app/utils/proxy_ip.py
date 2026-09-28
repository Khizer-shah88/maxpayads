"""Trust forwarded identity only across the configured internal proxy boundary."""
from functools import lru_cache
from ipaddress import ip_address, ip_network

from app.config import settings


@lru_cache(maxsize=8)
def trusted_networks(value):
    return tuple(ip_network(item.strip()) for item in value.split(',') if item.strip())


def client_ip(request):
    peer = request.client.host if request.client else 'unknown'
    try:
        address = ip_address(peer)
        if any(address in network for network in trusted_networks(settings.TRUSTED_PROXY_CIDRS)):
            forwarded = request.headers.get('x-real-ip')
            if forwarded:
                return str(ip_address(forwarded))
    except ValueError:
        pass
    return peer
