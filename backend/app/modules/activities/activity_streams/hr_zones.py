"""Heart-rate zone maths for activity streams.

Pure computation over samples and scalars: no session, no ORM, no other module.
Split out of the package's ``utils`` grab-bag, which held this alongside stream
serialization and visibility masking — three jobs whose only shared property was
having nowhere else to live.

The athlete's max heart rate arrives as the three values it is derived from
rather than as a user object. Taking ``users.schema.UsersRead`` made the streams
package depend on another module's *wire type* to read three fields, so a change
to what a user looks like on the API was a change to how heart-rate zones are
computed.
"""

import datetime

import numpy as np

import core.timezone as core_timezone

_DEFAULT_MAX_HEART_RATE: int = 220
_HR_ZONE_1_PERCENT: float = 0.6
_HR_ZONE_2_PERCENT: float = 0.7
_HR_ZONE_3_PERCENT: float = 0.8
_HR_ZONE_4_PERCENT: float = 0.9


def resolve_max_heart_rate(
    max_heart_rate: int | None,
    birthdate: datetime.date | None,
    timezone_name: str | None,
) -> int | None:
    """
    Resolve an athlete's max heart rate.

    Args:
        max_heart_rate: The stored max heart rate, if the athlete set one.
        birthdate: The athlete's date of birth, used for the age-derived
            fallback.
        timezone_name: The athlete's IANA timezone, or None to use the server's.

    Returns:
        The stored max HR, the age-derived value (220 - age), or None.
    """
    if max_heart_rate:
        return max_heart_rate
    if birthdate:
        return _DEFAULT_MAX_HEART_RATE - _age_in_years(birthdate, timezone_name)
    return None


def _age_in_years(birthdate: datetime.date, timezone_name: str | None) -> int:
    """Return completed years lived, as of today in the athlete's own timezone.

    Subtracting birth years alone counts someone born in December as a year older
    for the eleven months before their birthday, which skews the ``220 - age``
    fallback by a full year; comparing (month, day) fixes that. Resolving "today"
    in the athlete's zone rather than UTC then fixes the remaining one-day error
    around the birthday itself, which would otherwise age a user in UTC+13 a day
    early and one in UTC-11 a day late.

    Args:
        birthdate: The user's date of birth.
        timezone_name: The user's IANA timezone, or None to use the server's.

    Returns:
        Completed years since ``birthdate``.
    """
    today = core_timezone.today_in(core_timezone.or_default(timezone_name))
    had_birthday = (today.month, today.day) >= (birthdate.month, birthdate.day)
    return today.year - birthdate.year - (0 if had_birthday else 1)


def compute_hr_zone_breakdown_sync(
    waypoints: list[dict],
    max_heart_rate: int,
    total_timer_time: float | None,
) -> dict | None:
    """
    Compute the HR zone breakdown for a set of waypoints.

    Args:
        waypoints: List of waypoint dicts (each may contain an "hr" key).
        max_heart_rate: The user's max heart rate.
        total_timer_time: Activity total timer time in seconds (may be falsy).

    Returns:
        A dict of zone_1..zone_5 entries, or None if it cannot be computed.
    """

    if not waypoints or not isinstance(waypoints, list):
        return None

    zone_1 = max_heart_rate * _HR_ZONE_1_PERCENT
    zone_2 = max_heart_rate * _HR_ZONE_2_PERCENT
    zone_3 = max_heart_rate * _HR_ZONE_3_PERCENT
    zone_4 = max_heart_rate * _HR_ZONE_4_PERCENT

    def _compute_zone_counts(
        waypoints: list[dict],
        zone_1: float,
        zone_2: float,
        zone_3: float,
        zone_4: float,
    ) -> list[float] | None:
        """
        Compute per-zone percentage counts from waypoints.

        Args:
            waypoints: List of waypoint dicts with optional "hr" key.
            zone_1: Upper bound of zone 1.
            zone_2: Upper bound of zone 2.
            zone_3: Upper bound of zone 3.
            zone_4: Upper bound of zone 4.

        Returns:
            List of five zone percentages (0-100), or None if no
            HR data is present.
        """
        hr_values = np.array([float(hr) for wp in waypoints if (hr := wp.get("hr")) is not None])
        total = len(hr_values)
        if total == 0:
            return None

        zone_counts = [
            np.sum(hr_values < zone_1),
            np.sum((hr_values >= zone_1) & (hr_values < zone_2)),
            np.sum((hr_values >= zone_2) & (hr_values < zone_3)),
            np.sum((hr_values >= zone_3) & (hr_values < zone_4)),
            np.sum(hr_values >= zone_4),
        ]
        return [round((count / total) * 100, 2) for count in zone_counts]

    zone_percentages: list[float] | None = _compute_zone_counts(waypoints, zone_1, zone_2, zone_3, zone_4)

    if zone_percentages is None:
        return None

    if total_timer_time:
        zone_time_seconds = [int((percent / 100) * float(total_timer_time)) for percent in zone_percentages]
    else:
        zone_time_seconds = [0, 0, 0, 0, 0]

    zone_hr = {
        "zone_1": f"< {int(zone_1)}",
        "zone_2": f"{int(zone_1)} - {int(zone_2) - 1}",
        "zone_3": f"{int(zone_2)} - {int(zone_3) - 1}",
        "zone_4": f"{int(zone_3)} - {int(zone_4) - 1}",
        "zone_5": f">= {int(zone_4)}",
    }

    return {
        "zone_1": {"percent": zone_percentages[0], "hr": zone_hr["zone_1"], "time_seconds": zone_time_seconds[0]},
        "zone_2": {"percent": zone_percentages[1], "hr": zone_hr["zone_2"], "time_seconds": zone_time_seconds[1]},
        "zone_3": {"percent": zone_percentages[2], "hr": zone_hr["zone_3"], "time_seconds": zone_time_seconds[2]},
        "zone_4": {"percent": zone_percentages[3], "hr": zone_hr["zone_4"], "time_seconds": zone_time_seconds[3]},
        "zone_5": {"percent": zone_percentages[4], "hr": zone_hr["zone_5"], "time_seconds": zone_time_seconds[4]},
    }
