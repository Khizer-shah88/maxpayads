"""
Shared date-range helpers for click/analytics filters.

Historically each router built its own timestamp filter with
``{"$lte": datetime.fromisoformat(date_to)}``. Because a bare ``YYYY-MM-DD``
parses to that day at 00:00:00, ``$lte`` excluded the whole "to" day, so a
single-day range (from == to) matched nothing. These helpers make the "to"
bound inclusive of the entire day when no time component is supplied.
"""
from datetime import datetime, timedelta
from typing import Optional


def parse_date(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO date/datetime string. Returns None on empty/invalid input."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            return None


def _is_midnight(dt: datetime) -> bool:
    return dt.hour == 0 and dt.minute == 0 and dt.second == 0 and dt.microsecond == 0


def timestamp_range_query(date_from: Optional[str], date_to: Optional[str]) -> dict:
    """
    Build a Mongo timestamp filter fragment from optional from/to strings.

    - ``date_from`` → ``$gte`` at the parsed instant.
    - ``date_to`` with no time-of-day → ``$lt`` next-day midnight (whole day
      inclusive). With an explicit time → ``$lte`` at that instant.
    - Returns ``{}`` when neither bound is valid, so callers can skip applying it.
    """
    q: dict = {}
    start = parse_date(date_from)
    if start:
        q["$gte"] = start
    end = parse_date(date_to)
    if end:
        if _is_midnight(end):
            q["$lt"] = end + timedelta(days=1)
        else:
            q["$lte"] = end
    return q
