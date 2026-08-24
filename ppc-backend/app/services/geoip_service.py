from app.utils.geo_utils import lookup_ip
from typing import Tuple, Optional


async def get_location(ip: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (country_code, country_name) for an IP address."""
    return lookup_ip(ip)
