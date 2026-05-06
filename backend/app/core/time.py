"""Time helpers — UTC-aware everywhere.

The DB columns are stored as naive UTC for compatibility with SQLite
batch migrations; `utc_now()` returns naive-UTC, while `now_aware()`
returns a tz-aware datetime for app-level math and serialization.
"""
from datetime import datetime, timezone


def now_aware() -> datetime:
    """Timezone-aware UTC `datetime` (preferred for new code)."""
    return datetime.now(timezone.utc)


def utc_now() -> datetime:
    """Naive UTC `datetime` (matches existing DB columns)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
