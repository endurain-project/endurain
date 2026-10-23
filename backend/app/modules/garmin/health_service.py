"""Garmin Connect health sync: body composition, daily steps and sleep."""

from datetime import UTC, date, datetime, timedelta

import garminconnect

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

_USERS_PAGE_SIZE = 100


def _to_int(value: float | None) -> int | None:
    """Return ``value`` as an int, or ``None`` when Garmin Connect sent none."""
    return int(value) if value is not None else None


def _epoch_ms_to_utc(value: int | None) -> datetime | None:
    """Return the datetime a Garmin Connect millisecond epoch names, or ``None`` when it sent none."""
    return datetime.fromtimestamp(value / 1000, tz=UTC) if value else None


def _sleep_score(score: dict | None) -> health_sleep_schema.SleepScore | None:
    """Return the sleep score a Garmin Connect score entry names, or ``None`` when it names none.

    Args:
        score: One entry of the ``sleepScores`` payload.

    Returns:
        The score, or ``None`` when the entry is empty or its qualifier is unknown.
    """
    key = score.get("qualifierKey") if score else None
    return health_sleep_schema.SleepScore(key) if key in health_sleep_schema.SleepScore._value2member_map_ else None


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
    try:
        # Fetch Garmin Connect body composition data for the specified date range
        garmin_bc = garminconnect_client.get_body_composition(str(start_date.date()), str(end_date.date()))
    except garminconnect.GarminConnectAuthenticationError:
        raise
    except Exception as err:
        # Log an informational event if no body composition were found
        logger.error(
            "Error fetching body composition for user",
            exc_info=err,
            extra=core_logger.context(user_id=user_id, start_date=start_date.date(), end_date=end_date.date()),
        )
        # Return 0 to indicate no body composition were processed
        return 0

    if garmin_bc is None or "dateWeightList" not in garmin_bc or not garmin_bc["dateWeightList"]:
        # Log an informational event if no body composition were found
        logger.info(
            "No new Garmin Connect body composition found: garmin_bc is None or empty",
            extra=core_logger.context(user_id=user_id, start_date=start_date.date(), end_date=end_date.date()),
        )
        # Return 0 to indicate no body composition were processed
        return 0

    # Set the count of processed body composition to 0
    count_processed = 0
    # Process body composition
    for bc in garmin_bc["dateWeightList"]:
        # Validate metabolic_age is a reasonable value (1-150 years)
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

        with SessionLocal() as db:
            health_weight_db = health_weight_integration.get_health_weight_by_date(user_id, str(health_weight.date), db)

            if health_weight_db:
                health_weight_update = health_weight_schema.HealthWeightUpdate(
                    id=health_weight_db.id, user_id=user_id, **health_weight.model_dump()
                )
                health_weight_integration.edit_health_weight(user_id, health_weight_update, db)
                logger.info(
                    "Body composition edited",
                    extra=core_logger.context(user_id=user_id, date=health_weight.date),
                )
            else:
                health_weight_create = health_weight_schema.HealthWeightCreate(**health_weight.model_dump())
                health_weight_integration.create_health_weight(user_id, health_weight_create, db)
                logger.info(
                    "Body composition created",
                    extra=core_logger.context(user_id=user_id, date=health_weight.date),
                )
        # Increment the count of processed body composition
        count_processed += 1
    # Return the count of processed body composition
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
    try:
        # Fetch Garmin Connect daily steps data for the specified date range
        garmin_ds = garminconnect_client.get_daily_steps(str(start_date.date()), str(end_date.date()))
    except garminconnect.GarminConnectAuthenticationError:
        raise
    except Exception as err:
        # Log an informational event if no daily steps were found
        logger.error(
            "Error fetching daily steps for user",
            exc_info=err,
            extra=core_logger.context(user_id=user_id, start_date=start_date.date(), end_date=end_date.date()),
        )
        # Return 0 to indicate no daily steps were processed
        return 0

    if garmin_ds is None or len(garmin_ds) == 0 or "totalSteps" not in garmin_ds[0] or not garmin_ds[0]["totalSteps"]:
        # Log an informational event if no daily steps were found
        logger.info(
            "No new Garmin Connect daily steps found: garmin_ds is None or empty",
            extra=core_logger.context(user_id=user_id, start_date=start_date.date(), end_date=end_date.date()),
        )
        # Return 0 to indicate no daily steps were processed
        return 0

    # Set the count of processed steps to 0
    count_processed = 0
    # Process steps
    for ds in garmin_ds:
        if ds["totalSteps"] is None:
            continue

        health_steps = health_steps_schema.HealthStepsBase(
            date=ds["calendarDate"],
            steps=ds["totalSteps"],
            source=health_steps_schema.Source.GARMIN,
        )

        with SessionLocal() as db:
            health_steps_db = health_steps_integration.get_health_steps_by_date(user_id, str(health_steps.date), db)

            if health_steps_db:
                health_steps_update = health_steps_schema.HealthStepsUpdate(
                    id=health_steps_db.id, user_id=user_id, **health_steps.model_dump()
                )
                health_steps_integration.edit_health_steps(user_id, health_steps_update, db)
                logger.info(
                    "Daily steps edited",
                    extra=core_logger.context(user_id=user_id, date=health_steps.date),
                )
            else:
                health_steps_create = health_steps_schema.HealthStepsCreate(**health_steps.model_dump())
                health_steps_integration.create_health_steps(user_id, health_steps_create, db)
                logger.info(
                    "Daily steps created",
                    extra=core_logger.context(user_id=user_id, date=health_steps.date),
                )
        # Increment the count of processed steps
        count_processed += 1
    # Return the count of processed steps
    return count_processed


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
    current_date = start_date

    # Iterate through each date since get_sleep_data only supports
    # single date
    while current_date <= end_date:
        date_string = current_date.strftime("%Y-%m-%d")

        try:
            garmin_sleep = garminconnect_client.get_sleep_data(date_string)
        except garminconnect.GarminConnectAuthenticationError:
            raise
        except Exception as err:
            logger.error(
                "Error fetching sleep data",
                exc_info=err,
                extra=core_logger.context(user_id=user_id, date=date_string),
            )
            current_date += timedelta(days=1)
            continue

        if garmin_sleep is None or "dailySleepDTO" not in garmin_sleep or not garmin_sleep["dailySleepDTO"]:
            logger.info(
                "No Garmin Connect sleep data found",
                extra=core_logger.context(user_id=user_id, date=date_string),
            )
            current_date += timedelta(days=1)
            continue

        sleep_dto = garmin_sleep["dailySleepDTO"]

        # For a date without sleep Garmin still returns a DTO whose fields are all null
        if not sleep_dto.get("id") or not sleep_dto.get("sleepTimeSeconds"):
            logger.info(
                "No Garmin Connect sleep data found",
                extra=core_logger.context(user_id=user_id, date=date_string),
            )
            current_date += timedelta(days=1)
            continue

        # Convert timestamps from milliseconds to datetime
        sleep_start_gmt = _epoch_ms_to_utc(sleep_dto.get("sleepStartTimestampGMT"))
        sleep_end_gmt = _epoch_ms_to_utc(sleep_dto.get("sleepEndTimestampGMT"))
        # NOTE: Garmin's ``*TimestampLocal`` epochs are already offset-shifted —
        # they encode the sleeper's WALL CLOCK, not an instant. Reading them with
        # ``tz=UTC`` therefore yields a datetime whose UTC components equal the
        # local wall clock, which is what every consumer of these two columns
        # wants (the edit form renders them straight into ``datetime-local``
        # inputs). The true instants live in the ``*_gmt`` pair above.
        #
        # This is the same "wall clock wearing an instant's clothes" shape that
        # was removed from activities: the columns are ``timestamptz`` but do not
        # hold a meaningful instant. Deriving them from the GMT pair plus the
        # recording offset (which is exactly ``local - gmt``) would remove the
        # ambiguity; until then, do not convert or compare these values.
        sleep_start_local = _epoch_ms_to_utc(sleep_dto.get("sleepStartTimestampLocal"))
        sleep_end_local = _epoch_ms_to_utc(sleep_dto.get("sleepEndTimestampLocal"))

        # Process sleep stages from sleepLevels array
        sleep_stages = []
        if garmin_sleep.get("sleepLevels"):
            for level in garmin_sleep["sleepLevels"]:
                activity_level = level.get("activityLevel")

                # Validate and convert activity_level to enum
                try:
                    # Map Garmin activity levels to sleep stage types
                    # 0=deep, 1=light, 2=REM, 3=awake
                    stage_type = health_sleep_schema.SleepStageType(activity_level)
                except (TypeError, ValueError):
                    # Skip unknown or missing levels
                    continue

                start_gmt_str = level.get("startGMT")
                end_gmt_str = level.get("endGMT")

                start_gmt = (
                    datetime.strptime(
                        start_gmt_str,
                        "%Y-%m-%dT%H:%M:%S.%f",
                    ).replace(tzinfo=UTC)
                    if start_gmt_str
                    else None
                )
                end_gmt = (
                    datetime.strptime(
                        end_gmt_str,
                        "%Y-%m-%dT%H:%M:%S.%f",
                    ).replace(tzinfo=UTC)
                    if end_gmt_str
                    else None
                )

                duration_seconds = None
                if start_gmt and end_gmt:
                    duration_seconds = int((end_gmt - start_gmt).total_seconds())

                sleep_stage = health_sleep_schema.HealthSleepStage(
                    stage_type=stage_type,
                    start_time_gmt=start_gmt,
                    end_time_gmt=end_gmt,
                    duration_seconds=duration_seconds,
                )
                sleep_stages.append(sleep_stage)

        # Extract sleep scores
        sleep_scores = sleep_dto.get("sleepScores", {})
        overall_score = sleep_scores.get("overall", {})
        total_duration_score = sleep_scores.get(
            "totalDuration",
            {},
        )
        awake_count_score = sleep_scores.get("awakeCount", {})
        deep_percentage_score = sleep_scores.get(
            "deepPercentage",
            {},
        )
        light_percentage_score = sleep_scores.get(
            "lightPercentage",
            {},
        )
        rem_percentage_score = sleep_scores.get(
            "remPercentage",
            {},
        )
        sleep_stress_score = sleep_scores.get("stress", {})

        health_sleep = health_sleep_schema.HealthSleepBase(
            date=sleep_dto["calendarDate"],
            sleep_start_time_gmt=sleep_start_gmt,
            sleep_end_time_gmt=sleep_end_gmt,
            sleep_start_time_local=sleep_start_local,
            sleep_end_time_local=sleep_end_local,
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
            sleep_score_overall=overall_score.get("value"),
            sleep_score_duration=total_duration_score.get("qualifierKey"),
            sleep_score_quality=overall_score.get("qualifierKey"),
            garminconnect_sleep_id=str(sleep_dto.get("id")),
            sleep_stages=sleep_stages if sleep_stages else None,
            source=health_sleep_schema.Source.GARMIN,
            hrv_status=(
                health_sleep_schema.HRVStatus(garmin_sleep.get("hrvStatus"))
                if garmin_sleep.get("hrvStatus")
                and garmin_sleep.get("hrvStatus") in health_sleep_schema.HRVStatus._value2member_map_
                else None
            ),
            resting_heart_rate=garmin_sleep.get("restingHeartRate"),
            avg_skin_temp_deviation=garmin_sleep.get("avgSkinTempDeviationC"),
            awake_count_score=_sleep_score(awake_count_score),
            rem_percentage_score=_sleep_score(rem_percentage_score),
            deep_percentage_score=_sleep_score(deep_percentage_score),
            light_percentage_score=_sleep_score(light_percentage_score),
            avg_sleep_stress=_to_int(sleep_dto.get("avgSleepStress")),
            sleep_stress_score=_sleep_score(sleep_stress_score),
        )

        with SessionLocal() as db:
            health_sleep_db = health_sleep_integration.get_health_sleep_by_date(user_id, str(health_sleep.date), db)

            if health_sleep_db:
                # Never overwrite a row written by another source; rows created before
                # ``source`` was stored are recognised by their Garmin sleep id
                if (
                    health_sleep_db.source != health_sleep_schema.Source.GARMIN
                    and not health_sleep_db.garminconnect_sleep_id
                ):
                    logger.info(
                        "Keeping existing non-Garmin sleep data",
                        extra=core_logger.context(user_id=user_id, date=health_sleep.date),
                    )
                    current_date += timedelta(days=1)
                    continue
                health_sleep_update = health_sleep_schema.HealthSleepUpdate(
                    id=health_sleep_db.id, user_id=user_id, **health_sleep.model_dump()
                )
                health_sleep_integration.edit_health_sleep(user_id, health_sleep_update, db)
                logger.info(
                    "Sleep data edited",
                    extra=core_logger.context(user_id=user_id, date=health_sleep.date),
                )
            else:
                health_sleep_create = health_sleep_schema.HealthSleepCreate(**health_sleep.model_dump())
                health_sleep_integration.create_health_sleep(user_id, health_sleep_create, db)
                logger.info(
                    "Sleep data created",
                    extra=core_logger.context(user_id=user_id, date=health_sleep.date),
                )

        count_processed += 1
        current_date += timedelta(days=1)

    return count_processed


def retrieve_garminconnect_users_health_for_days(days: int) -> None:
    """Fetch and store the last days of Garmin Connect health data for every linked user.

    Linked users are read a page at a time in short sessions, so no connection is held
    while Garmin is being called and one user failing does not stop the rest.

    Args:
        days: How many days back to fetch.
    """
    calculated_end_date = datetime.now(UTC)
    calculated_start_date = calculated_end_date - timedelta(days=days)

    after_id = 0
    while True:
        try:
            user_ids = garmin_service.linked_user_ids(after_id, _USERS_PAGE_SIZE)
        except Exception as err:
            logger.error(
                "Error getting users in retrieve_garminconnect_users_health_for_days",
                exc_info=err,
            )
            return
        if not user_ids:
            return
        for user_id in user_ids:
            try:
                get_user_garminconnect_health_by_dates(calculated_start_date, calculated_end_date, user_id)
            except Exception as err:
                logger.error(
                    "Error processing health data for user in retrieve_garminconnect_users_health_for_days",
                    exc_info=err,
                    extra=core_logger.context(user_id=user_id),
                )
        after_id = user_ids[-1]


def retrieve_recent_health() -> None:
    """Backfill the last day of Garmin Connect health stats for every linked user."""
    retrieve_garminconnect_users_health_for_days(1)


def get_user_garminconnect_health_by_dates(
    start_date: datetime,
    end_date: datetime,
    user_id: int,
) -> None:
    """Fetch and store one user's Garmin Connect health data for a window.

    No session is open while Garmin is being called; each record is stored in its own short
    one. An expired token unlinks the account and notifies the user.

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

        num_garminconnect_bc_processed = fetch_and_process_bc_by_dates(
            garminconnect_client, start_date, end_date, user_id
        )
        num_garminconnect_ds_processed = fetch_and_process_ds_by_dates(
            garminconnect_client, start_date, end_date, user_id
        )
        num_garminconnect_sleep_processed = fetch_and_process_sleep_by_dates(
            garminconnect_client, start_date, end_date, user_id
        )

        logger.info(
            "Garmin Connect body composition processed",
            extra=core_logger.context(user_id=user_id, count=num_garminconnect_bc_processed),
        )
        logger.info(
            "Garmin Connect daily steps processed",
            extra=core_logger.context(user_id=user_id, count=num_garminconnect_ds_processed),
        )
        logger.info(
            "Garmin Connect sleep data processed",
            extra=core_logger.context(user_id=user_id, count=num_garminconnect_sleep_processed),
        )
    except garminconnect.GarminConnectAuthenticationError as err:
        garmin_service.handle_rejected_token(user_id, session, err)
    except Exception as err:
        logger.error(
            "Error in get_user_garminconnect_health_by_dates",
            exc_info=err,
            extra=core_logger.context(user_id=user_id),
        )
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
