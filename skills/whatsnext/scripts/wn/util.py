"""Small shared helpers: the current UTC time and parsing a stored UTC time."""

import datetime
import re

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?Z$")


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def parse_date(text):
    """A stored UTC time (`2026-10-27T14:05Z`, seconds optional) as a datetime, or None when it is not valid."""
    if not text or not DATE_RE.match(text):
        return None
    fmt = "%Y-%m-%dT%H:%M:%SZ" if text.count(":") == 2 else "%Y-%m-%dT%H:%MZ"
    try:
        return datetime.datetime.strptime(text, fmt)
    except ValueError:
        return None
