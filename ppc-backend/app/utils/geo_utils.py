from typing import Optional, Tuple
import geoip2.database
import geoip2.errors
from app.config import settings
import logging

logger = logging.getLogger(__name__)

_reader = None


def get_geoip_reader():
    global _reader
    if _reader is None:
        try:
            _reader = geoip2.database.Reader(settings.GEOIP_DB_PATH)
        except Exception as e:
            logger.warning(f"GeoIP database not available: {e}")
    return _reader


def lookup_ip(ip: str) -> Tuple[Optional[str], Optional[str]]:
    """Return (country_code, country_name) for given IP."""
    reader = get_geoip_reader()
    if not reader:
        return None, None
    try:
        response = reader.country(ip)
        country_code = response.country.iso_code
        country_name = response.country.name
        return country_code, country_name
    except (geoip2.errors.AddressNotFoundError, Exception):
        return None, None
