"""UTC ISO-8601 for storage; household-local phrasing only for spoken text."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def to_utc_iso(value: str | datetime) -> str:
    dt = datetime.fromisoformat(value) if isinstance(value, str) else value
    if dt.tzinfo is None:
        raise ValueError(f"timestamp without timezone: {value!r}")
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def spoken_until(ends_at: str, tz: str, now: datetime) -> str:
    """'8 PM Saturday' (within a week) or '8 PM October 29', in the household's time zone.

    Never 'today'/'tomorrow': summaries are stored and read back later, so relative days go stale.
    """
    zone = ZoneInfo(tz)
    end = parse_utc(ends_at).astimezone(zone)
    local_now = now.astimezone(zone)
    clock = end.strftime("%I:%M %p").lstrip("0").replace(":00", "")
    if (end.date() - local_now.date()).days < 7:
        return f"{clock} {end.strftime('%A')}"
    return f"{clock} {end.strftime('%B')} {end.day}"
