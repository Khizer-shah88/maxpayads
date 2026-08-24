from user_agents import parse
from app.core.constants import DEVICE_DESKTOP, DEVICE_MOBILE, DEVICE_TABLET


def parse_user_agent(ua_string: str) -> dict:
    """Parse user agent string and return device info."""
    try:
        ua = parse(ua_string)
        if ua.is_tablet:
            device_type = DEVICE_TABLET
        elif ua.is_mobile:
            device_type = DEVICE_MOBILE
        else:
            device_type = DEVICE_DESKTOP

        os_family = ua.os.family if ua.os.family != "Other" else None
        browser_family = ua.browser.family if ua.browser.family != "Other" else None

        return {
            "device_type": device_type,
            "os": os_family,
            "browser": browser_family,
            "is_bot": ua.is_bot,
        }
    except Exception:
        return {
            "device_type": DEVICE_DESKTOP,
            "os": None,
            "browser": None,
            "is_bot": False,
        }


def is_bot_user_agent(ua_string: str) -> bool:
    """Check if user agent belongs to a bot/crawler."""
    from app.core.constants import BOT_UA_KEYWORDS
    ua_lower = ua_string.lower()
    if any(keyword in ua_lower for keyword in BOT_UA_KEYWORDS):
        return True
    try:
        ua = parse(ua_string)
        return ua.is_bot
    except Exception:
        return False
