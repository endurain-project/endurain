"""The canonical recording every activity file decoder produces.

A decoder (``gpx_decoder``, ``tcx_decoder``, ``fit_decoder``) reads one file into a :class:`Recording` and does no
math: it keeps what the file says, with ``None`` for anything the file leaves out or writes as an unusable value, and
never invents a zero or a placeholder. ``assembly`` turns a recording into the activities ingestion stores, and the
encoders write one back out as a file.

A file holds one or more sessions. A session's samples are one aligned column per channel (one row per recorded
instant, in time order) rather than one object per sample, which keeps a long file small in memory and maps directly
onto arrays.
"""

import bisect
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

import core.exceptions as core_exceptions
import modules.activities.activity_exercise_titles.contracts as activity_exercise_titles_contracts
import modules.activities.activity_workout_steps.contracts as activity_workout_steps_contracts

#: The most samples one file may hold: about 5.8 days at one sample per second.
MAX_SAMPLES_PER_FILE = 500_000

#: The most sessions one file may hold.
MAX_SESSIONS_PER_FILE = 100

type FileFormat = Literal["gpx", "tcx", "fit"]


@dataclass(frozen=True, slots=True, kw_only=True)
class Samples:
    """One session's sample table, one row per recorded instant in time order.

    Every column has one entry per row. A channel the device did not record at an instant is ``None`` there.

    Attributes:
        time: When each sample was recorded, timezone-aware UTC, with the file's sub-second precision.
        lat: Latitude in degrees.
        lon: Longitude in degrees.
        altitude: Altitude in metres.
        distance: Cumulative distance in metres as the device recorded it.
        speed: Speed in metres per second as the device recorded it.
        heart_rate: Heart rate in beats per minute.
        cadence: Cadence in the device's native unit: revolutions per minute, a single leg's rate for running,
            with any fractional part folded in.
        power: Power in watts.
        temperature: Temperature in degrees Celsius.
    """

    time: tuple[datetime, ...] = ()
    lat: tuple[float | None, ...] = ()
    lon: tuple[float | None, ...] = ()
    altitude: tuple[float | None, ...] = ()
    distance: tuple[float | None, ...] = ()
    speed: tuple[float | None, ...] = ()
    heart_rate: tuple[int | None, ...] = ()
    cadence: tuple[float | None, ...] = ()
    power: tuple[int | None, ...] = ()
    temperature: tuple[float | None, ...] = ()

    def __len__(self) -> int:
        """Return the number of rows.

        Returns:
            The row count.
        """
        return len(self.time)


class FileLimits:
    """Counts what one file decodes and refuses a file past the sample or session limit.

    The count runs as the file is decoded, so a file over :data:`MAX_SAMPLES_PER_FILE` or
    :data:`MAX_SESSIONS_PER_FILE` is refused before the excess is held in memory. A decoder makes one per file and
    shares it between that file's sample builders.
    """

    def __init__(self) -> None:
        """Start both counts at zero."""
        self._samples = 0
        self._sessions = 0

    def count_sample(self) -> None:
        """Count one more sample.

        Raises:
            InvalidInputError: When the file passes the sample limit.
        """
        self._samples += 1
        if self._samples > MAX_SAMPLES_PER_FILE:
            raise core_exceptions.InvalidInputError(
                f"The file holds more than {MAX_SAMPLES_PER_FILE} samples, the most one file may hold"
            )

    def count_session(self) -> None:
        """Count one more session.

        Raises:
            InvalidInputError: When the file passes the session limit.
        """
        self._sessions += 1
        if self._sessions > MAX_SESSIONS_PER_FILE:
            raise core_exceptions.InvalidInputError(
                f"The file holds more than {MAX_SESSIONS_PER_FILE} sessions, the most one file may hold"
            )


class SamplesBuilder:
    """Appends samples row by row and builds the aligned :class:`Samples` columns in time order.

    A decoder appends rows in the order the file writes them; :meth:`build` reorders them by time when the file wrote
    them out of order, keeping the file order of equal times.
    """

    def __init__(self, limits: FileLimits) -> None:
        """Start an empty table counted against the file's limits.

        Args:
            limits: The file's limits, shared by every builder of the file.
        """
        self._limits = limits
        self._in_order = True
        self._time: list[datetime] = []
        self._lat: list[float | None] = []
        self._lon: list[float | None] = []
        self._altitude: list[float | None] = []
        self._distance: list[float | None] = []
        self._speed: list[float | None] = []
        self._heart_rate: list[int | None] = []
        self._cadence: list[float | None] = []
        self._power: list[int | None] = []
        self._temperature: list[float | None] = []

    def append(
        self,
        time: datetime,
        *,
        lat: float | None = None,
        lon: float | None = None,
        altitude: float | None = None,
        distance: float | None = None,
        speed: float | None = None,
        heart_rate: int | None = None,
        cadence: float | None = None,
        power: int | None = None,
        temperature: float | None = None,
    ) -> None:
        """Append one sample; a channel left out is ``None`` for this row.

        Args:
            time: When the sample was recorded, timezone-aware UTC.
            lat: Latitude in degrees.
            lon: Longitude in degrees.
            altitude: Altitude in metres.
            distance: Cumulative distance in metres.
            speed: Speed in metres per second.
            heart_rate: Heart rate in beats per minute.
            cadence: Cadence in the device's native unit.
            power: Power in watts.
            temperature: Temperature in degrees Celsius.

        Raises:
            InvalidInputError: When the file passes the sample limit.
        """
        self._limits.count_sample()
        if self._time and time < self._time[-1]:
            self._in_order = False
        self._time.append(time)
        self._lat.append(lat)
        self._lon.append(lon)
        self._altitude.append(altitude)
        self._distance.append(distance)
        self._speed.append(speed)
        self._heart_rate.append(heart_rate)
        self._cadence.append(cadence)
        self._power.append(power)
        self._temperature.append(temperature)

    def __len__(self) -> int:
        """Return the number of rows appended so far.

        Returns:
            The row count.
        """
        return len(self._time)

    def build(self) -> Samples:
        """Return the rows appended so far, in time order.

        Returns:
            The sample table.
        """
        order = range(len(self._time)) if self._in_order else sorted(range(len(self._time)), key=self._time.__getitem__)
        return Samples(
            time=tuple(self._time[row] for row in order),
            lat=tuple(self._lat[row] for row in order),
            lon=tuple(self._lon[row] for row in order),
            altitude=tuple(self._altitude[row] for row in order),
            distance=tuple(self._distance[row] for row in order),
            speed=tuple(self._speed[row] for row in order),
            heart_rate=tuple(self._heart_rate[row] for row in order),
            cadence=tuple(self._cadence[row] for row in order),
            power=tuple(self._power[row] for row in order),
            temperature=tuple(self._temperature[row] for row in order),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class Pause:
    """A stretch inside a session where the device was not timing, from when it stopped to when it resumed.

    Attributes:
        start: When timing stopped, UTC.
        end: When timing resumed, UTC.
    """

    start: datetime
    end: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class Lap:
    """A lap the device recorded, with the summary the file gives for it.

    Attributes:
        start_time: When the lap started, UTC.
        start_position_lat: Start latitude in degrees.
        start_position_long: Start longitude in degrees.
        end_position_lat: End latitude in degrees.
        end_position_long: End longitude in degrees.
        total_elapsed_time: Elapsed seconds.
        total_timer_time: Timed seconds.
        total_distance: Distance in metres.
        total_cycles: Cycles (strides, strokes or revolutions).
        total_calories: Calories in kcal.
        avg_heart_rate: Average heart rate in beats per minute.
        max_heart_rate: Maximum heart rate in beats per minute.
        avg_cadence: Average cadence in the device's native unit, whole part.
        max_cadence: Maximum cadence in the device's native unit, whole part.
        avg_fractional_cadence: The fractional part of the average cadence.
        max_fractional_cadence: The fractional part of the maximum cadence.
        avg_power: Average power in watts.
        max_power: Maximum power in watts.
        normalized_power: Normalized power in watts.
        total_work: Work in joules.
        total_ascent: Ascent in metres.
        total_descent: Descent in metres.
        avg_speed: Average speed in metres per second.
        max_speed: Maximum speed in metres per second.
        min_altitude: Lowest altitude in metres.
        max_altitude: Highest altitude in metres.
        intensity: The lap's intensity as the file names it (``active``, ``rest`` and so on).
        lap_trigger: What ended the lap as the file names it (``manual``, ``distance`` and so on).
        sport: The lap's sport as the file names it.
        sub_sport: The lap's sub sport as the file names it.
        avg_vertical_oscillation: Average vertical oscillation in millimetres.
        avg_stance_time: Average ground contact time in milliseconds.
        avg_vertical_ratio: Average vertical ratio in percent.
        avg_step_length: Average step length in millimetres.
    """

    start_time: datetime
    start_position_lat: float | None = None
    start_position_long: float | None = None
    end_position_lat: float | None = None
    end_position_long: float | None = None
    total_elapsed_time: float | None = None
    total_timer_time: float | None = None
    total_distance: float | None = None
    total_cycles: int | None = None
    total_calories: int | None = None
    avg_heart_rate: int | None = None
    max_heart_rate: int | None = None
    avg_cadence: int | None = None
    max_cadence: int | None = None
    avg_fractional_cadence: float | None = None
    max_fractional_cadence: float | None = None
    avg_power: int | None = None
    max_power: int | None = None
    normalized_power: int | None = None
    total_work: int | None = None
    total_ascent: int | None = None
    total_descent: int | None = None
    avg_speed: float | None = None
    max_speed: float | None = None
    min_altitude: float | None = None
    max_altitude: float | None = None
    intensity: str | None = None
    lap_trigger: str | None = None
    sport: str | None = None
    sub_sport: str | None = None
    avg_vertical_oscillation: float | None = None
    avg_stance_time: float | None = None
    avg_vertical_ratio: float | None = None
    avg_step_length: float | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Length:
    """One pool length of a lap-swimming session.

    Attributes:
        message_index: The length's index in the file.
        start_time: When the length started, UTC.
        total_elapsed_time: Elapsed seconds.
        total_timer_time: Timed seconds, ``None`` when the file gives none.
        total_strokes: Strokes.
        avg_speed: Average speed in metres per second.
        swim_stroke: The stroke as the file names it.
        avg_swimming_cadence: Average cadence in strokes per minute.
        length_type: ``active`` for a swum length, ``idle`` for rest.
    """

    message_index: int | None = None
    start_time: datetime | None = None
    total_elapsed_time: float | None = None
    total_timer_time: float | None = None
    total_strokes: int | None = None
    avg_speed: float | None = None
    swim_stroke: str | None = None
    avg_swimming_cadence: int | None = None
    length_type: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class SplitSummary:
    """A FIT split summary: the working time of one kind of split.

    Attributes:
        split_type: The split type as the file names it (``interval_active``, ``interval_rest`` and so on).
        total_timer_time: Working seconds, ``None`` when the file gives none.
    """

    split_type: str | None = None
    total_timer_time: float | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class DeviceSummary:
    """The totals the device itself reported for a session, each ``None`` when the file gives none.

    Attributes:
        total_elapsed_time: Elapsed seconds.
        total_timer_time: Timed seconds.
        distance: Distance in metres.
        calories: Calories in kcal.
        avg_heart_rate: Average heart rate in beats per minute.
        max_heart_rate: Maximum heart rate in beats per minute.
        avg_cadence: Average cadence in the device's native unit, whole part.
        max_cadence: Maximum cadence in the device's native unit, whole part.
        avg_fractional_cadence: The fractional part of the average cadence.
        max_fractional_cadence: The fractional part of the maximum cadence.
        avg_power: Average power in watts.
        max_power: Maximum power in watts.
        normalized_power: Normalized power in watts.
        avg_speed: Average speed in metres per second.
        max_speed: Maximum speed in metres per second.
        total_ascent: Ascent in metres.
        total_descent: Descent in metres.
        total_cycles: Cycles (strides, strokes or revolutions).
        workout_feeling: The athlete's feeling rating.
        workout_rpe: The athlete's perceived exertion.
        start_lat: Start latitude in degrees.
        start_lon: Start longitude in degrees.
    """

    total_elapsed_time: float | None = None
    total_timer_time: float | None = None
    distance: float | None = None
    calories: int | None = None
    avg_heart_rate: int | None = None
    max_heart_rate: int | None = None
    avg_cadence: int | None = None
    max_cadence: int | None = None
    avg_fractional_cadence: float | None = None
    max_fractional_cadence: float | None = None
    avg_power: int | None = None
    max_power: int | None = None
    normalized_power: int | None = None
    avg_speed: float | None = None
    max_speed: float | None = None
    total_ascent: int | None = None
    total_descent: int | None = None
    total_cycles: int | None = None
    workout_feeling: int | None = None
    workout_rpe: int | None = None
    start_lat: float | None = None
    start_lon: float | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class Session:
    """One activity's worth of a file: a FIT session, a TCX ``Activity`` or a GPX file's tracks.

    Attributes:
        sport: The sport as a name ``activity_constants.define_activity_type`` resolves; ``None`` when the file names
            none.
        start_time: When the session started, UTC.
        samples: The session's samples, cut to its time range.
        pauses: Where the device stopped timing, in time order.
        laps: The laps the device recorded, in time order; empty when the file records none.
        lengths: The session's pool lengths.
        split_summaries: The session's FIT split summaries.
        sets: The session's FIT workout sets, each the row ``activity_sets`` stores.
        workout_steps: The planned workout steps the session followed.
        summary: The totals the device reported for the session.
    """

    sport: str | None
    start_time: datetime
    samples: Samples
    pauses: tuple[Pause, ...] = ()
    laps: tuple[Lap, ...] = ()
    lengths: tuple[Length, ...] = ()
    split_summaries: tuple[SplitSummary, ...] = ()
    sets: tuple[list[object], ...] = ()
    workout_steps: tuple[activity_workout_steps_contracts.ActivityWorkoutStepsCreate, ...] = ()
    summary: DeviceSummary = field(default_factory=DeviceSummary)


@dataclass(frozen=True, slots=True, kw_only=True)
class Recording:
    """Everything one activity file holds, as it holds it.

    Attributes:
        format: The file format the recording was decoded from.
        sessions: The file's sessions, in time order.
        name: The activity name the file gives, ``None`` when it gives none.
        description: The activity description the file gives.
        creator: The application or device that wrote the file, as the file names it.
        manufacturer: The device manufacturer as the file names it.
        product: The device product as the file names it.
        local_time_offset: Seconds from UTC to the device's local time, as the FIT ``activity`` message gives it
            (``local_timestamp - timestamp``).
        device_time_offset: Seconds from UTC to the device's local time, as the FIT ``device_settings`` message gives
            it.
        exercise_titles: The FIT exercise titles, file-scoped.
    """

    format: FileFormat
    sessions: tuple[Session, ...]
    name: str | None = None
    description: str | None = None
    creator: str | None = None
    manufacturer: str | None = None
    product: str | None = None
    local_time_offset: int | None = None
    device_time_offset: int | None = None
    exercise_titles: tuple[activity_exercise_titles_contracts.ActivityExerciseTitlesCreate, ...] = ()


def samples_between(samples: Samples, start: datetime, end: datetime | None, *, end_inclusive: bool = False) -> Samples:
    """Return the rows recorded from ``start`` (inclusive) to ``end``.

    ``end`` is exclusive by default, so a sample on the instant one session ends and the next starts belongs to the
    later one only; ``end_inclusive`` keeps a sample on ``end`` itself, for a range that ends where nothing follows.

    Args:
        samples: The table to cut.
        start: The first instant to keep.
        end: Where the range ends; ``None`` keeps everything from ``start`` on.
        end_inclusive: Whether a sample at ``end`` belongs to the range.

    Returns:
        The rows in the range.
    """
    first = bisect.bisect_left(samples.time, start)
    if end is None:
        last = len(samples)
    elif end_inclusive:
        last = bisect.bisect_right(samples.time, end)
    else:
        last = bisect.bisect_left(samples.time, end)
    return Samples(
        time=samples.time[first:last],
        lat=samples.lat[first:last],
        lon=samples.lon[first:last],
        altitude=samples.altitude[first:last],
        distance=samples.distance[first:last],
        speed=samples.speed[first:last],
        heart_rate=samples.heart_rate[first:last],
        cadence=samples.cadence[first:last],
        power=samples.power[first:last],
        temperature=samples.temperature[first:last],
    )
