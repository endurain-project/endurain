"""Garmin Connect health sync: body composition, daily steps and sleep."""

from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import garminconnect
from pydantic import BaseModel
from sqlalchemy.orm import Session

import core.logger as core_logger
import modules.garmin.service as garmin_service
import modules.health.health_sleep.integration_service as health_sleep_integration
import modules.health.health_sleep.schema as health_sleep_schema
import modules.health.health_steps.integration_service as health_steps_integration
import modules.health.health_steps.schema as health_steps_schema
import modules.health.health_weight.integration_service as health_weight_integration
import modules.health.health_weight.schema as health_weight_schema
from core.database import SessionLocal

logger = core_logger.get_logger(__name__)


def _to_int(value: float | None) -> int | None:
    """Return ``value`` as an int, or ``None`` when Garmin Connect sent none."""
    return int(value) if value is not None else None


def _epoch_ms_to_utc(value: int | None) -> datetime | None:
    """Return the datetime a Garmin Connect millisecond epoch names, or ``None`` when it sent none."""
    return datetime.fromtimestamp(value / 1000, tz=UTC) if value else None


def _each_day(start_date: datetime, end_date: datetime) -> Iterator[date]:
    """Yield every calendar day from ``start_date`` to ``end_date``, inclusive."""
    day = start_date.date()
    while day <= end_date.date():
        yield day
        day += timedelta(days=1)


def _sleep_score(score: dict | None) -> health_sleep_schema.SleepScore | None:
    """Return the sleep score a Garmin Connect score entry names, or ``None`` when it names none.

    Args:
        score: One entry of the ``sleepScores`` payload.

    Returns:
        The score, or ``None`` when the entry is empty or its qualifier is unknown.
    """
    key = score.get("qualifierKey") if score else None
    return health_sleep_schema.SleepScore(key) if key in health_sleep_schema.SleepScore._value2member_map_ else None


def _fetch(
    fetch: Callable[[], Any],
    what: str,
    user_id: int,
    start_date: date,
    end_date: date,
) -> Any | None:
    """Call Garmin Connect for one kind of health data, treating a failed call as no data.

    Args:
        fetch: The Garmin Connect call.
        what: What is being fetched, for the log.
        user_id: The data's owner.
        start_date: First day requested.
        end_date: Last day requested.

    Returns:
        The payload, or ``None`` when the call failed.

    Raises:
        GarminConnectAuthenticationError: When Garmin Connect rejects the session.
    """
    try:
        return fetch()
    except garminconnect.GarminConnectAuthenticationError:
        raise
    except Exception as err:
        logger.error(
            "Error fetching Garmin Connect health data for user",
            exc_info=err,
            extra=core_logger.context(user_id=user_id, what=what, start_date=start_date, end_date=end_date),
        )
        return None


def _upsert(
    user_id: int,
    record: BaseModel,
    *,
    label: str,
    get: Callable[[int, str, Session], Any],
    edit: Callable[[int, Any, Session], Any],
    create: Callable[[int, Any, Session], Any],
    update_schema: type[BaseModel],
    create_schema: type[BaseModel],
    keep_existing: Callable[[Any], bool] | None = None,
) -> bool:
    """Store a health record in a short session of its own: edit the day's record, or create it.

    Args:
        user_id: The record's owner.
        record: The record built from Garmin Connect, carrying its ``date``.
        label: The kind of record, for the log.
        get: Reads the owner's record for a date.
        edit: Edits an existing record.
        create: Creates a record.
        update_schema: The schema ``edit`` takes.
        create_schema: The schema ``create`` takes.
        keep_existing: Tells whether an existing record must be left as it is.

    Returns:
        True when the record was stored, False when an existing one was kept.
    """
    fields = record.model_dump()
    with SessionLocal() as db:
        existing = get(user_id, str(fields["date"]), db)
        if existing and keep_existing is not None and keep_existing(existing):
            logger.info(
                "Keeping existing non-Garmin health record",
                extra=core_logger.context(user_id=user_id, record=label, date=fields["date"]),
            )
            return False
        if existing:
            edit(user_id, update_schema(id=existing.id, user_id=user_id, **fields), db)
            outcome = "edited"
        else:
            create(user_id, create_schema(**fields), db)
            outcome = "created"
    logger.info(
        "Garmin Connect health record stored",
        extra=core_logger.context(user_id=user_id, record=label, outcome=outcome, date=fields["date"]),
    )
    return True


def fetch_and_process_bc_by_dates(
    garminconnect_client: garminconnect.Garmin,
    start_date: datetime,
    end_date: datetime,
    user_id: int,
) -> int:
    """Fetch and store body composition from Garmin Connect.

    Args:
        garminconnect_client: Authenticated Garmin Connect client.
        start_date: Start date for the retrieval.
        end_date: End date for the retrieval.
        user_id: The records' owner.

    Returns:
        Number of body composition records processed.
    """
    garmin_bc = _fetch(
        lambda: garminconnect_client.get_body_composition(str(start_date.date()), str(end_date.date())),
        "body composition",
        user_id,
        start_date.date(),
        end_date.date(),
    )

    if not garmin_bc or not garmin_bc.get("dateWeightList"):
        logger.info(
            "No new Garmin Connect body composition found",
            extra=core_logger.context(user_id=user_id, start_date=start_date.date(), end_date=end_date.date()),
        )
        return 0

    count_processed = 0
    for bc in garmin_bc["dateWeightList"]:
        # A metabolic age outside 1-150 years is a bad reading
        metabolic_age = bc.get("metabolicAge")
        if metabolic_age is not None and (metabolic_age < 1 or metabolic_age > 150):
            metabolic_age = None

        health_weight = health_weight_schema.HealthWeightBase(
            date=bc["calendarDate"],
            weight=bc["weight"] / 1000 if bc["weight"] is not None else None,
            bmi=bc["bmi"],
            body_fat=bc["bodyFat"],
            body_water=bc["bodyWater"],
            bone_mass=(bc["boneMass"] / 1000 if bc["boneMass"] is not None else None),
            muscle_mass=(bc["muscleMass"] / 1000 if bc["muscleMass"] is not None else None),
            physique_rating=bc["physiqueRating"],
            visceral_fat=bc["visceralFat"],
            metabolic_age=metabolic_age,
            source=health_weight_schema.Source.GARMIN,
        )
        _upsert(
            user_id,
            health_weight,
            label="Body composition",
            get=health_weight_integration.get_health_weight_by_date,
            edit=health_weight_integration.edit_health_weight,
            create=health_weight_integration.create_health_weight,
            update_schema=health_weight_schema.HealthWeightUpdate,
            create_schema=health_weight_schema.HealthWeightCreate,
        )
        count_processed += 1
    return count_processed


def fetch_and_process_ds_by_dates(
    garminconnect_client: garminconnect.Garmin,
    start_date: datetime,
    end_date: datetime,
    user_id: int,
) -> int:
    """Fetch and store daily steps from Garmin Connect.

    Args:
        garminconnect_client: Authenticated Garmin Connect client.
        start_date: Start date for the retrieval.
        end_date: End date for the retrieval.
        user_id: The records' owner.

    Returns:
        Number of daily steps records processed.
    """
    garmin_ds = _fetch(
        lambda: garminconnect_client.get_daily_steps(str(start_date.date()), str(end_date.date())),
        "daily steps",
        user_id,
        start_date.date(),
        end_date.date(),
    )

    if not garmin_ds or not garmin_ds[0].get("totalSteps"):
        logger.info(
            "No new Garmin Connect daily steps found",
            extra=core_logger.context(user_id=user_id, start_date=start_date.date(), end_date=end_date.date()),
        )
        return 0

    count_processed = 0
    for ds in garmin_ds:
        if ds["totalSteps"] is None:
            continue

        health_steps = health_steps_schema.HealthStepsBase(
            date=ds["calendarDate"],
            steps=ds["totalSteps"],
            source=health_steps_schema.Source.GARMIN,
        )
        _upsert(
            user_id,
            health_steps,
            label="Daily steps",
            get=health_steps_integration.get_health_steps_by_date,
            edit=health_steps_integration.edit_health_steps,
            create=health_steps_integration.create_health_steps,
            update_schema=health_steps_schema.HealthStepsUpdate,
            create_schema=health_steps_schema.HealthStepsCreate,
        )
        count_processed += 1
    return count_processed


def _parse_sleep_stages(sleep_levels: list[dict] | None) -> list[health_sleep_schema.HealthSleepStage]:
    """Build the sleep stages a Garmin Connect ``sleepLevels`` payload names.

    Args:
        sleep_levels: The payload's ``sleepLevels`` entries.

    Returns:
        The stages, skipping entries whose activity level is unknown or missing.
    """
    sleep_stages = []
    for level in sleep_levels or []:
        # Garmin activity levels map to stage types: 0=deep, 1=light, 2=REM, 3=awake
        try:
            stage_type = health_sleep_schema.SleepStageType(level.get("activityLevel"))
        except (TypeError, ValueError):
            continue

        start_gmt_str = level.get("startGMT")
        end_gmt_str = level.get("endGMT")
        start_gmt = (
            datetime.strptime(start_gmt_str, "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=UTC) if start_gmt_str else None
        )
        end_gmt = datetime.strptime(end_gmt_str, "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=UTC) if end_gmt_str else None

        sleep_stages.append(
            health_sleep_schema.HealthSleepStage(
                stage_type=stage_type,
                start_time_gmt=start_gmt,
                end_time_gmt=end_gmt,
                duration_seconds=int((end_gmt - start_gmt).total_seconds()) if start_gmt and end_gmt else None,
            )
        )
    return sleep_stages


def _build_sleep(garmin_sleep: dict, sleep_dto: dict) -> health_sleep_schema.HealthSleepBase:
    """Build the sleep record a day's Garmin Connect sleep payload describes.

    Args:
        garmin_sleep: The whole sleep payload.
        sleep_dto: Its ``dailySleepDTO`` entry.

    Returns:
        The sleep record.
    """
    # NOTE: Garmin's ``*TimestampLocal`` epochs are already offset-shifted —
    # they encode the sleeper's WALL CLOCK, not an instant. Reading them with
    # ``tz=UTC`` therefore yields a datetime whose UTC components equal the
    # local wall clock, which is what every consumer of these two columns
    # wants (the edit form renders them straight into ``datetime-local``
    # inputs). The true instants live in the ``*_gmt`` pair.
    #
    # This is the same "wall clock wearing an instant's clothes" shape that
    # was removed from activities: the columns are ``timestamptz`` but do not
    # hold a meaningful instant. Deriving them from the GMT pair plus the
    # recording offset (which is exactly ``local - gmt``) would remove the
    # ambiguity; until then, do not convert or compare these values.
    sleep_scores = sleep_dto.get("sleepScores", {})
    hrv_status = garmin_sleep.get("hrvStatus")

    return health_sleep_schema.HealthSleepBase(
        date=sleep_dto["calendarDate"],
        sleep_start_time_gmt=_epoch_ms_to_utc(sleep_dto.get("sleepStartTimestampGMT")),
        sleep_end_time_gmt=_epoch_ms_to_utc(sleep_dto.get("sleepEndTimestampGMT")),
        sleep_start_time_local=_epoch_ms_to_utc(sleep_dto.get("sleepStartTimestampLocal")),
        sleep_end_time_local=_epoch_ms_to_utc(sleep_dto.get("sleepEndTimestampLocal")),
        total_sleep_seconds=sleep_dto.get("sleepTimeSeconds"),
        nap_time_seconds=sleep_dto.get("napTimeSeconds"),
        unmeasurable_sleep_seconds=sleep_dto.get("unmeasurableSleepSeconds"),
        deep_sleep_seconds=sleep_dto.get("deepSleepSeconds"),
        light_sleep_seconds=sleep_dto.get("lightSleepSeconds"),
        rem_sleep_seconds=sleep_dto.get("remSleepSeconds"),
        awake_sleep_seconds=sleep_dto.get("awakeSleepSeconds"),
        avg_heart_rate=_to_int(sleep_dto.get("avgHeartRate")),
        min_heart_rate=None,
        max_heart_rate=None,
        avg_spo2=_to_int(sleep_dto.get("averageSpO2Value")),
        lowest_spo2=sleep_dto.get("lowestSpO2Value"),
        highest_spo2=sleep_dto.get("highestSpO2Value"),
        avg_respiration=_to_int(sleep_dto.get("averageRespirationValue")),
        lowest_respiration=_to_int(sleep_dto.get("lowestRespirationValue")),
        highest_respiration=_to_int(sleep_dto.get("highestRespirationValue")),
        avg_stress_level=_to_int(sleep_dto.get("avgSleepStress")),
        awake_count=sleep_dto.get("awakeCount"),
        restless_moments_count=None,
        sleep_score_overall=sleep_scores.get("overall", {}).get("value"),
        sleep_score_duration=sleep_scores.get("totalDuration", {}).get("qualifierKey"),
        sleep_score_quality=sleep_scores.get("overall", {}).get("qualifierKey"),
        garminconnect_sleep_id=str(sleep_dto.get("id")),
        sleep_stages=_parse_sleep_stages(garmin_sleep.get("sleepLevels")) or None,
        source=health_sleep_schema.Source.GARMIN,
        hrv_status=(
            health_sleep_schema.HRVStatus(hrv_status)
            if hrv_status and hrv_status in health_sleep_schema.HRVStatus._value2member_map_
            else None
        ),
        resting_heart_rate=garmin_sleep.get("restingHeartRate"),
        avg_skin_temp_deviation=garmin_sleep.get("avgSkinTempDeviationC"),
        awake_count_score=_sleep_score(sleep_scores.get("awakeCount", {})),
        rem_percentage_score=_sleep_score(sleep_scores.get("remPercentage", {})),
        deep_percentage_score=_sleep_score(sleep_scores.get("deepPercentage", {})),
        light_percentage_score=_sleep_score(sleep_scores.get("lightPercentage", {})),
        avg_sleep_stress=_to_int(sleep_dto.get("avgSleepStress")),
        sleep_stress_score=_sleep_score(sleep_scores.get("stress", {})),
    )


def _is_other_source_sleep(existing: Any) -> bool:
    """Tell whether a stored sleep record came from another source than Garmin Connect.

    Rows created before ``source`` was stored are recognised by their Garmin sleep id.
    """
    return existing.source != health_sleep_schema.Source.GARMIN and not existing.garminconnect_sleep_id


def fetch_and_process_sleep_by_dates(
    garminconnect_client: garminconnect.Garmin,
    start_date: datetime,
    end_date: datetime,
    user_id: int,
) -> int:
    """Fetch and process sleep data from Garmin Connect.

    Args:
        garminconnect_client: Authenticated Garmin Connect client.
        start_date: Start date for sleep data retrieval.
        end_date: End date for sleep data retrieval.
        user_id: ID of the user to process sleep data for.

    Returns:
        Number of sleep records processed.
    """
    count_processed = 0

    # get_sleep_data only supports a single date
    for day in _each_day(start_date, end_date):
        garmin_sleep = _fetch(
            lambda day=day: garminconnect_client.get_sleep_data(day.isoformat()),
            "sleep data",
            user_id,
            day,
            day,
        )

        sleep_dto = garmin_sleep.get("dailySleepDTO") if garmin_sleep else None
        # For a date without sleep Garmin still returns a DTO whose fields are all null
        if not sleep_dto or not sleep_dto.get("id") or not sleep_dto.get("sleepTimeSeconds"):
            logger.info(
                "No Garmin Connect sleep data found",
                extra=core_logger.context(user_id=user_id, date=day),
            )
            continue

        stored = _upsert(
            user_id,
            _build_sleep(garmin_sleep, sleep_dto),
            label="Sleep data",
            get=health_sleep_integration.get_health_sleep_by_date,
            edit=health_sleep_integration.edit_health_sleep,
            create=health_sleep_integration.create_health_sleep,
            update_schema=health_sleep_schema.HealthSleepUpdate,
            create_schema=health_sleep_schema.HealthSleepCreate,
            keep_existing=_is_other_source_sleep,
        )
        count_processed += stored

    return count_processed


def get_user_garminconnect_health_by_dates(
    start_date: datetime,
    end_date: datetime,
    user_id: int,
) -> None:
    """Fetch and store one user's Garmin Connect health data for a window.

    No session is open while Garmin is being called; each record is stored in its own short
    one. An expired token unlinks the account and notifies the user. Any other failure
    propagates, so a durable worker retries the sync.

    Args:
        start_date: Start of the window.
        end_date: End of the window.
        user_id: The user to sync.
    """
    session = None
    try:
        with SessionLocal() as db:
            session = garmin_service.get_user_garminconnect_session(user_id, db)

        if session is None:
            return
        garminconnect_client = session.client

        logger.info(
            "Started Garmin Connect health processing for date range",
            extra=core_logger.context(user_id=user_id, start_date=start_date.date(), end_date=end_date.date()),
        )

        for what, fetch in (
            ("body composition", fetch_and_process_bc_by_dates),
            ("daily steps", fetch_and_process_ds_by_dates),
            ("sleep data", fetch_and_process_sleep_by_dates),
        ):
            count = fetch(garminconnect_client, start_date, end_date, user_id)
            logger.info(
                "Garmin Connect health data processed",
                extra=core_logger.context(user_id=user_id, what=what, count=count),
            )
    except garminconnect.GarminConnectAuthenticationError as err:
        garmin_service.handle_rejected_token(user_id, session, err)
    finally:
        if session is not None:
            garmin_service.save_refreshed_token(user_id, session)


def sync_health_for_dates(start_date: date, end_date: date, user_id: int) -> None:
    """Fetch and store one user's Garmin Connect health data for whole days.

    Args:
        start_date: First day to fetch.
        end_date: Last day to fetch, inclusive.
        user_id: The user to sync.
    """
    logger.info(
        "Garmin Connect health data will be processed in the background",
        extra=core_logger.context(user_id=user_id),
    )
    get_user_garminconnect_health_by_dates(
        datetime.combine(start_date, datetime.min.time(), tzinfo=UTC),
        datetime.combine(end_date, datetime.max.time(), tzinfo=UTC),
        user_id,
    )
