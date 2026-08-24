import ipaddress
from typing import Optional
from app.core.constants import DATACENTER_CIDRS


def is_valid_ip(ip: str) -> bool:
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False


def is_private_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return addr.is_private or addr.is_loopback or addr.is_link_local
    except ValueError:
        return False


def is_datacenter_ip(ip: str) -> bool:
    """Check if IP belongs to known datacenter ranges."""
    try:
        addr = ipaddress.ip_address(ip)
        for cidr in DATACENTER_CIDRS:
            network = ipaddress.ip_network(cidr, strict=False)
            if addr in network:
                return True
        return False
    except ValueError:
        return False


def get_client_ip(request_headers: dict, remote_addr: str) -> str:
    """Extract real client IP from request headers."""
    # Check CF-Connecting-IP first (Cloudflare)
    cf_ip = request_headers.get("cf-connecting-ip", "")
    if cf_ip and is_valid_ip(cf_ip):
        return cf_ip

    # Check X-Forwarded-For (from reverse proxy)
    x_forwarded = request_headers.get("x-forwarded-for", "")
    if x_forwarded:
        ip = x_forwarded.split(",")[0].strip()
        if is_valid_ip(ip):
            return ip

    # Check X-Real-IP
    x_real_ip = request_headers.get("x-real-ip", "")
    if x_real_ip and is_valid_ip(x_real_ip):
        return x_real_ip

    return remote_addr
