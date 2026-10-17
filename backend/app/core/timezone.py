"""Centralized timezone conversion utilities."""

import functools
from datetime import date, datetime, timedelta
from typing import overload
from zoneinfo import ZoneInfo

from timezonefinder import TimezoneFinder

import core.config as core_config

# ISO 8601 datetime format without offset, used for the
# naive UTC wall-clock strings persisted by file parsers.
_DT_FMT = "%Y-%m-%dT%H:%M:%S"

#: Widest real-world UTC offset (Pacific/Kiritimati, +14:00).
#:
#: Used wherever the server has to be tolerant of a timezone the request never
#: carries: widening an indexable pre-filter on a raw UTC column so it cannot
#: exclude a row the exact local-time predicate would keep, and bounding "is this
#: plausibly the caller's current year?" checks.
MAX_UTC_OFFSET = timedelta(hours=14)


#: Legacy IANA link names mapped to the canonical zone they point at.
#:
#: PostgreSQL builds that omit the legacy ``backward`` links (the ``postgres:18``
#: image does) reject these in ``AT TIME ZONE``, which turns every date-filtered
#: activity query into a 500 for a user holding one. Activities are therefore
#: stored under the canonical name. Only the geographic and country-style
#: aliases are listed; abbreviations such as ``EST`` or ``CET`` name no place.
_LEGACY_ALIASES: dict[str, str] = {
    "Africa/Asmera": "Africa/Asmara",
    "America/Buenos_Aires": "America/Argentina/Buenos_Aires",
    "America/Catamarca": "America/Argentina/Catamarca",
    "America/Cordoba": "America/Argentina/Cordoba",
    "America/Fort_Wayne": "America/Indiana/Indianapolis",
    "America/Godthab": "America/Nuuk",
    "America/Indianapolis": "America/Indiana/Indianapolis",
    "America/Jujuy": "America/Argentina/Jujuy",
    "America/Knox_IN": "America/Indiana/Knox",
    "America/Louisville": "America/Kentucky/Louisville",
    "America/Mendoza": "America/Argentina/Mendoza",
    "America/Rosario": "America/Argentina/Cordoba",
    "Asia/Calcutta": "Asia/Kolkata",
    "Asia/Dacca": "Asia/Dhaka",
    "Asia/Katmandu": "Asia/Kathmandu",
    "Asia/Macao": "Asia/Macau",
    "Asia/Rangoon": "Asia/Yangon",
    "Asia/Saigon": "Asia/Ho_Chi_Minh",
    "Asia/Ulan_Bator": "Asia/Ulaanbaatar",
    "Atlantic/Faeroe": "Atlantic/Faroe",
    "Australia/ACT": "Australia/Sydney",
    "Australia/NSW": "Australia/Sydney",
    "Australia/North": "Australia/Darwin",
    "Australia/Queensland": "Australia/Brisbane",
    "Australia/South": "Australia/Adelaide",
    "Australia/Tasmania": "Australia/Hobart",
    "Australia/Victoria": "Australia/Melbourne",
    "Australia/West": "Australia/Perth",
    "Brazil/Acre": "America/Rio_Branco",
    "Brazil/East": "America/Sao_Paulo",
    "Brazil/West": "America/Manaus",
    "Canada/Atlantic": "America/Halifax",
    "Canada/Central": "America/Winnipeg",
    "Canada/Eastern": "America/Toronto",
    "Canada/Mountain": "America/Edmonton",
    "Canada/Newfoundland": "America/St_Johns",
    "Canada/Pacific": "America/Vancouver",
    "Canada/Saskatchewan": "America/Regina",
    "Canada/Yukon": "America/Whitehorse",
    "Chile/Continental": "America/Santiago",
    "Cuba": "America/Havana",
    "Egypt": "Africa/Cairo",
    "Eire": "Europe/Dublin",
    "Europe/Kiev": "Europe/Kyiv",
    "GB": "Europe/London",
    "GB-Eire": "Europe/London",
    "GMT0": "Etc/GMT",
    "Greenwich": "Etc/GMT",
    "Hongkong": "Asia/Hong_Kong",
    "Iceland": "Atlantic/Reykjavik",
    "Iran": "Asia/Tehran",
    "Israel": "Asia/Jerusalem",
    "Jamaica": "America/Jamaica",
    "Japan": "Asia/Tokyo",
    "Libya": "Africa/Tripoli",
    "Mexico/BajaNorte": "America/Tijuana",
    "Mexico/General": "America/Mexico_City",
    "NZ": "Pacific/Auckland",
    "NZ-CHAT": "Pacific/Chatham",
    "Navajo": "America/Denver",
    "PRC": "Asia/Shanghai",
    "Poland": "Europe/Warsaw",
    "Portugal": "Europe/Lisbon",
    "ROC": "Asia/Taipei",
    "ROK": "Asia/Seoul",
    "Singapore": "Asia/Singapore",
    "Turkey": "Europe/Istanbul",
    "UCT": "Etc/UTC",
    "US/Alaska": "America/Anchorage",
    "US/Aleutian": "America/Adak",
    "US/Arizona": "America/Phoenix",
    "US/Central": "America/Chicago",
    "US/East-Indiana": "America/Indiana/Indianapolis",
    "US/Eastern": "America/New_York",
    "US/Hawaii": "Pacific/Honolulu",
    "US/Indiana-Starke": "America/Indiana/Knox",
    "US/Michigan": "America/Detroit",
    "US/Mountain": "America/Denver",
    "US/Pacific": "America/Los_Angeles",
    "US/Samoa": "Pacific/Pago_Pago",
    "Universal": "Etc/UTC",
    "W-SU": "Europe/Moscow",
    "Zulu": "Etc/UTC",
}


def canonical(tz_name: str | None) -> str | None:
    """Return the canonical IANA name for a possibly legacy timezone alias.

    Args:
        tz_name: An IANA timezone name, or None.

    Returns:
        The canonical name when ``tz_name`` is a known legacy alias, otherwise
        ``tz_name`` unchanged.
    """
    return _LEGACY_ALIASES.get(tz_name, tz_name) if tz_name else tz_name


def or_default(tz_name: str | None) -> str:
    """Return the given IANA timezone, or the server's configured default.

    The fallback is a fact about the *server* (``settings.TZ``), so it belongs
    here rather than in whichever domain module happens to hold a nullable
    timezone column.

    Args:
        tz_name: An IANA timezone name, or None.

    Returns:
        An IANA timezone name.
    """
    return tz_name or core_config.settings.TZ


@functools.lru_cache(maxsize=1)
def _timezone_finder() -> TimezoneFinder:
    """Return a process-wide cached TimezoneFinder.

    Constructing ``TimezoneFinder`` loads its bundled timezone polygon data, so
    it is built once and reused instead of per activity (a single instance is
    safe for concurrent ``timezone_at`` reads).

    Returns:
        The shared TimezoneFinder.
    """
    return TimezoneFinder()


def from_lat_lon(latitude: float, longitude: float, fallback_tz: str | None = None) -> str:
    """Return the IANA timezone a coordinate falls in, or a fallback.

    ``timezone_at`` answers ``None`` over open ocean and in the gaps between
    timezone polygons, so the fallback is not optional decoration: the Strava
    adapter used to assign the raw result straight onto the activity, discarding
    the athlete's own timezone it had just resolved whenever the lookup missed.
    Every caller resolves the same way now.

    Args:
        latitude: WGS-84 latitude in decimal degrees.
        longitude: WGS-84 longitude in decimal degrees.
        fallback_tz: Timezone to use when the lookup finds none; defaults to the
            server's configured timezone.

    Returns:
        An IANA timezone name.
    """
    return _timezone_finder().timezone_at(lat=latitude, lng=longitude) or or_default(fallback_tz)


def today_in(tz_name: str) -> date:
    """Return today's calendar date in the given IANA timezone.

    "Which day is it?" is a local question that the server cannot answer from
    its own clock: a request carries no timezone, so ``date.today()`` silently
    answers in the container's zone and ``datetime.now(UTC).date()`` in UTC.
    Either is wrong for any user not on that zone — a day behind for up to 13
    hours at UTC+13, a day ahead for up to 11 hours at UTC-11.

    Callers supply the zone explicitly (typically the athlete's stored
    ``users.timezone``, falling back to ``settings.TZ``) so the choice is
    visible at the call site rather than buried in a default.

    Args:
        tz_name: IANA timezone name to resolve "today" in.

    Returns:
        The current calendar date in that timezone.
    """
    return datetime.now(ZoneInfo(tz_name)).date()


@overload
def to_utc_aware(dt: datetime | str) -> datetime: ...


@overload
def to_utc_aware(dt: None) -> None: ...


def to_utc_aware(dt: datetime | str | None) -> datetime | None:
    """
    Normalize a datetime or ISO string to UTC-aware.

    Parses ISO 8601 strings and attaches UTC to naive
    datetimes (the import parsers emit naive UTC wall
    clock values). Ensures stored timestamps carry an
    explicit UTC offset instead of relying on the
    database session timezone.

    The overloads state the actual contract: ``None`` is
    returned only for a ``None`` input, so callers that
    already hold a value do not have to re-check the
    result for ``None``.

    Args:
        dt: A datetime, ISO 8601 string, or None.

    Returns:
        A UTC-aware datetime, or None if dt is None.
    """
    if dt is None:
        return None
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(ZoneInfo("UTC"))


def format_utc(dt: datetime | str | None) -> str:
    """
    Format a datetime as a UTC ISO 8601 string (no offset).

    File timestamps may carry a non-UTC offset (e.g.
    2026-03-28T08:19:19-07:00). Converting to UTC before
    formatting preserves the actual instant; without it the
    offset is silently dropped and the wall-clock is stored
    as if it were UTC. Naive datetimes are assumed to be UTC.

    Used for the **waypoint** timestamps inside stream payloads, which are
    stored as JSON strings. For an activity's ``start_time``/``end_time`` use
    :func:`to_utc_second` instead — those are real ``datetime`` columns, and
    round-tripping them through a string only to parse it back loses the type
    for no benefit.

    Args:
        dt: A datetime, ISO 8601 string, or None.

    Returns:
        UTC ISO 8601 string without an offset, or an empty
        string if dt is None.
    """
    aware = to_utc_aware(dt)
    return aware.strftime(_DT_FMT) if aware else ""


@overload
def to_utc_second(dt: datetime | str) -> datetime: ...


@overload
def to_utc_second(dt: None) -> None: ...


def to_utc_second(dt: datetime | str | None) -> datetime | None:
    """
    Normalize to UTC-aware and truncate to whole seconds.

    The resolution every ingestion producer already agreed on: the file parsers
    and the provider adapters all used to format their activity start/end times
    with a second-precision pattern and let the schema validator parse them
    back. That round-trip made the value a ``str`` at the type level even though
    every consumer needs a ``datetime``, so this does the same normalization
    directly.

    Truncation is preserved rather than dropped because the start-time duplicate
    check compares stored instants for equality: devices report whole seconds,
    and letting sub-second noise through would make the same activity re-imported
    from a different source look like a new one.

    Args:
        dt: A datetime, ISO 8601 string, or None.

    Returns:
        A UTC-aware datetime with microseconds zeroed, or None if dt is None.
    """
    aware = to_utc_aware(dt)
    return aware.replace(microsecond=0) if aware is not None else None
