"""Heart-rate zone maths for activity streams.

Pure computation over samples and scalars: no session, no ORM, no other module.
The athlete's max heart rate arrives as the three values it is derived from
rather than as a user object. Taking ``users.schema.UserRead`` would make the
streams package depend on another module's *wire type* to read three fields, so
a change to what a user looks like on the API would change how heart-rate zones
are computed.
"""

import datetime
from collections.abc import Sequence
from typing import Annotated, TypedDict

import numpy as np
from pydantic import Field

import core.timezone as core_timezone
import modules.activities.computation as activities_computation

#: The instant offsets are counted from; only the gaps between samples matter to the zones.
_EPOCH = datetime.datetime(1970, 1, 1, tzinfo=datetime.UTC)
_DEFAULT_MAX_HEART_RATE: int = 220
_HR_ZONE_1_PERCENT: float = 0.6
_HR_ZONE_2_PERCENT: float = 0.7
_HR_ZONE_3_PERCENT: float = 0.8
_HR_ZONE_4_PERCENT: float = 0.9


class HrZone(TypedDict):
    """One heart-rate zone of a breakdown.

    Attributes:
        percent: Share of the recorded heart-rate time spent in the zone, 0-100.
        hr: The zone's heart-rate range, e.g. ``"120 - 139"``.
        time_seconds: Time spent in the zone, in seconds.
    """

    percent: Annotated[
        float, Field(description="Share of the recorded heart-rate time spent in the zone, as a percentage (0-100)")
    ]
    hr: Annotated[str, Field(description="The zone's heart-rate range in beats per minute, such as 120 - 139")]
    time_seconds: Annotated[
        int,
        Field(description="Time spent in the zone in seconds, each sample counting the time it holds until the next"),
    ]


class HrZoneBreakdown(TypedDict):
    """An activity's time in each of the five heart-rate zones."""

    zone_1: HrZone
    zone_2: HrZone
    zone_3: HrZone
    zone_4: HrZone
    zone_5: HrZone


def resolve_max_heart_rate(
    max_heart_rate: int | None,
    birthdate: datetime.date | None,
    timezone_name: str | None,
) -> int | None:
    """Resolve an athlete's max heart rate.

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
    offsets_ms: Sequence[int],
    heart_rate: Sequence[float | None],
    max_heart_rate: int,
) -> HrZoneBreakdown | None:
    """Compute the time spent in each heart-rate zone of an activity's samples.

    Each sample holds its heart rate until the next sample, capped at the pause threshold of the heart-rate samples,
    so a smart recording that stores a value for ten seconds counts ten seconds, and a pause adds no more than the
    threshold.
    Samples sharing an instant share it. A heart rate of 0 is a dropout: it is left out together with its time, as is
    a sample without a heart rate.

    Args:
        offsets_ms: Each sample's time, in milliseconds from the activity start.
        heart_rate: Each sample's heart rate in bpm, ``None`` where it has none; aligned with ``offsets_ms``.
        max_heart_rate: The user's max heart rate, in bpm.

    Returns:
        A dict of zone_1..zone_5 entries, or None when no zone holds any time (no heart rate, a single instant).
    """
    measured = [(offset, hr) for offset, hr in zip(offsets_ms, heart_rate, strict=True) if hr is not None]
    # The heart rate's own sampling sets the threshold, not the samples of the other channels in between.
    threshold = activities_computation.pause_threshold_seconds(
        [_EPOCH + datetime.timedelta(milliseconds=offset) for offset, _ in measured]
    )
    kept = [(offset / 1000, hr) for offset, hr in measured if hr]
    if not kept:
        return None
    held = activities_computation.held_seconds([seconds for seconds, _ in kept], threshold)
    total = float(held.sum())
    if total == 0.0:
        return None

    zone_1 = max_heart_rate * _HR_ZONE_1_PERCENT
    zone_2 = max_heart_rate * _HR_ZONE_2_PERCENT
    zone_3 = max_heart_rate * _HR_ZONE_3_PERCENT
    zone_4 = max_heart_rate * _HR_ZONE_4_PERCENT

    zone_of = np.searchsorted([zone_1, zone_2, zone_3, zone_4], np.array([float(hr) for _, hr in kept]), side="right")
    zone_time = np.bincount(zone_of, weights=held, minlength=5)
    zone_percentages = [round(float(seconds) / total * 100, 2) for seconds in zone_time]
    zone_time_seconds = [round(float(seconds)) for seconds in zone_time]

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
