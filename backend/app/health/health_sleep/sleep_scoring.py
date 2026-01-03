"""
Sleep scoring calculations.
"""

import health.health_sleep.schema as health_sleep_schema

from datetime import datetime


def _calculate_sleep_duration_hours(
    total_sleep_seconds: int | None,
) -> float:
    """
    Convert total sleep seconds to hours.

    Args:
        total_sleep_seconds: Total sleep duration in seconds.

    Returns:
        Sleep duration in hours as float.
    """
    if total_sleep_seconds is None:
        return 0.0
    return total_sleep_seconds / 3600.0


def _calculate_stage_percentage(
    stage_seconds: int | None,
    total_sleep_seconds: int | None,
) -> float:
    """
    Calculate percentage of a sleep stage relative to total sleep.

    Args:
        stage_seconds: Duration of specific sleep stage in seconds.
        total_sleep_seconds: Total sleep duration in seconds.

    Returns:
        Percentage of sleep stage (0-100).
    """
    if stage_seconds is None or total_sleep_seconds is None or total_sleep_seconds == 0:
        return 0.0
    return (stage_seconds / total_sleep_seconds) * 100.0


def calculate_sleep_score_duration(
    sleep_start_time: datetime | None,
    sleep_end_time: datetime | None,
    total_sleep_seconds: int | None,
) -> tuple[int, str]:
    """
    Calculate sleep duration score based on total sleep time.

    Scoring criteria (based on adult sleep recommendations):
    - 7-9 hours: EXCELLENT (90-100 points)
    - 6-7 or 9-10 hours: GOOD (70-89 points)
    - 5-6 or 10-11 hours: FAIR (50-69 points)
    - < 5 or > 11 hours: POOR (0-49 points)

    Args:
        sleep_start_time: Start time of sleep session.
        sleep_end_time: End time of sleep session.
        total_sleep_seconds: Total sleep duration in seconds.

    Returns:
        Tuple of (score points 0-100, score label).
    """
    if total_sleep_seconds is None or total_sleep_seconds <= 0:
        return (0, "POOR")

    hours = _calculate_sleep_duration_hours(total_sleep_seconds)

    # Optimal sleep range: 7-9 hours
    if 7.0 <= hours <= 9.0:
        # Scale within optimal range (7h = 90pts, 8h = 100pts, 9h
        # = 90pts)
        if hours <= 8.0:
            score = int(90 + ((hours - 7.0) * 10))
        else:
            score = int(100 - ((hours - 8.0) * 10))
        return (score, "EXCELLENT")

    # Good sleep range: 6-7 or 9-10 hours
    if 6.0 <= hours < 7.0:
        score = int(70 + ((hours - 6.0) * 20))
        return (score, "GOOD")
    if 9.0 < hours <= 10.0:
        score = int(89 - ((hours - 9.0) * 19))
        return (score, "GOOD")

    # Fair sleep range: 5-6 or 10-11 hours
    if 5.0 <= hours < 6.0:
        score = int(50 + ((hours - 5.0) * 20))
        return (score, "FAIR")
    if 10.0 < hours <= 11.0:
        score = int(69 - ((hours - 10.0) * 19))
        return (score, "FAIR")

    # Poor sleep: < 5 or > 11 hours
    if hours < 5.0:
        score = max(0, int(49 * (hours / 5.0)))
        return (score, "POOR")
    # > 11 hours
    score = max(0, int(49 - ((hours - 11.0) * 5)))
    return (score, "POOR")


def calculate_sleep_score_quality(
    deep_sleep_seconds: int | None,
    light_sleep_seconds: int | None,
    rem_sleep_seconds: int | None,
    awake_sleep_seconds: int | None,
    total_sleep_seconds: int | None,
) -> tuple[int, str]:
    """
    Calculate sleep quality score based on sleep stage composition.

    Scoring based on optimal sleep stage percentages:
    - Deep: 13-23% optimal (peak at 18%)
    - REM: 20-25% optimal (peak at 22.5%)
    - Light: 45-55% optimal (peak at 50%)
    - Awake: < 5% optimal

    Args:
        deep_sleep_seconds: Duration of deep sleep in seconds.
        light_sleep_seconds: Duration of light sleep in seconds.
        rem_sleep_seconds: Duration of REM sleep in seconds.
        awake_sleep_seconds: Duration of awake time in seconds.
        total_sleep_seconds: Total sleep duration in seconds.

    Returns:
        Tuple of (score points 0-100, score label).
    """
    if total_sleep_seconds is None or total_sleep_seconds <= 0:
        return (0, "POOR")

    # Calculate percentages
    deep_pct = _calculate_stage_percentage(deep_sleep_seconds, total_sleep_seconds)
    rem_pct = _calculate_stage_percentage(rem_sleep_seconds, total_sleep_seconds)
    light_pct = _calculate_stage_percentage(light_sleep_seconds, total_sleep_seconds)
    awake_pct = _calculate_stage_percentage(awake_sleep_seconds, total_sleep_seconds)

    # Score each component (0-100)
    deep_score = _score_sleep_stage(deep_pct, 13.0, 23.0, 18.0)
    rem_score = _score_sleep_stage(rem_pct, 20.0, 25.0, 22.5)
    light_score = _score_sleep_stage(light_pct, 45.0, 55.0, 50.0)

    # Awake penalty (lower is better)
    if awake_pct <= 5.0:
        awake_score = 100 - (awake_pct * 4)
    else:
        awake_score = max(0, 80 - ((awake_pct - 5.0) * 10))

    # Weighted average: deep 25%, REM 30%, light 25%, awake 20%
    total_score = int(
        (deep_score * 0.25)
        + (rem_score * 0.30)
        + (light_score * 0.25)
        + (awake_score * 0.20)
    )

    # Determine label
    if total_score >= 90:
        return (total_score, "EXCELLENT")
    if total_score >= 70:
        return (total_score, "GOOD")
    if total_score >= 50:
        return (total_score, "FAIR")
    return (total_score, "POOR")


def _score_sleep_stage(
    actual_pct: float,
    min_optimal: float,
    max_optimal: float,
    peak_optimal: float,
) -> float:
    """
    Score a sleep stage percentage against optimal range.

    Args:
        actual_pct: Actual percentage of sleep stage.
        min_optimal: Minimum optimal percentage.
        max_optimal: Maximum optimal percentage.
        peak_optimal: Peak optimal percentage.

    Returns:
        Score from 0-100.
    """
    if min_optimal <= actual_pct <= max_optimal:
        # Within optimal range, calculate distance from peak
        if actual_pct <= peak_optimal:
            # Between min and peak
            range_span = peak_optimal - min_optimal
            if range_span > 0:
                score = 80 + ((actual_pct - min_optimal) / range_span) * 20
            else:
                score = 100
        else:
            # Between peak and max
            range_span = max_optimal - peak_optimal
            if range_span > 0:
                score = 100 - ((actual_pct - peak_optimal) / range_span) * 20
            else:
                score = 100
        return min(100, max(80, score))

    if actual_pct < min_optimal:
        # Below optimal range
        if min_optimal > 0:
            score = 80 * (actual_pct / min_optimal)
        else:
            score = 0
        return max(0, score)

    # Above optimal range
    over_pct = actual_pct - max_optimal
    score = max(0, 80 - (over_pct * 4))
    return score


def calculate_awake_count_score(
    awake_count: int | None,
) -> tuple[int, str]:
    """
    Calculate score based on number of awakenings during sleep.

    Scoring criteria:
    - 0-1 awakenings: EXCELLENT (90-100 points)
    - 2-3 awakenings: GOOD (70-89 points)
    - 4-5 awakenings: FAIR (50-69 points)
    - 6+ awakenings: POOR (0-49 points)

    Args:
        awake_count: Number of times awakened during sleep.

    Returns:
        Tuple of (score points 0-100, score label).
    """
    if awake_count is None:
        return (50, "FAIR")

    if awake_count <= 1:
        score = 100 - (awake_count * 5)
        return (score, "EXCELLENT")
    if awake_count <= 3:
        score = 89 - ((awake_count - 2) * 10)
        return (score, "GOOD")
    if awake_count <= 5:
        score = 69 - ((awake_count - 4) * 10)
        return (score, "FAIR")

    # 6+ awakenings
    score = max(0, 49 - ((awake_count - 6) * 5))
    return (score, "POOR")


def calculate_rem_percentage_score(
    rem_sleep_seconds: int | None,
    total_sleep_seconds: int | None,
) -> tuple[int, str]:
    """
    Calculate score for REM sleep percentage.

    Optimal REM: 20-25% of total sleep (peak at 22.5%).

    Args:
        rem_sleep_seconds: Duration of REM sleep in seconds.
        total_sleep_seconds: Total sleep duration in seconds.

    Returns:
        Tuple of (score points 0-100, score label).
    """
    if total_sleep_seconds is None or total_sleep_seconds <= 0:
        return (0, "POOR")

    rem_pct = _calculate_stage_percentage(rem_sleep_seconds, total_sleep_seconds)
    score = int(_score_sleep_stage(rem_pct, 20.0, 25.0, 22.5))

    if score >= 90:
        return (score, "EXCELLENT")
    if score >= 70:
        return (score, "GOOD")
    if score >= 50:
        return (score, "FAIR")
    return (score, "POOR")


def calculate_deep_percentage_score(
    deep_sleep_seconds: int | None,
    total_sleep_seconds: int | None,
) -> tuple[int, str]:
    """
    Calculate score for deep sleep percentage.

    Optimal deep sleep: 13-23% of total sleep (peak at 18%).

    Args:
        deep_sleep_seconds: Duration of deep sleep in seconds.
        total_sleep_seconds: Total sleep duration in seconds.

    Returns:
        Tuple of (score points 0-100, score label).
    """
    if total_sleep_seconds is None or total_sleep_seconds <= 0:
        return (0, "POOR")

    deep_pct = _calculate_stage_percentage(deep_sleep_seconds, total_sleep_seconds)
    score = int(_score_sleep_stage(deep_pct, 13.0, 23.0, 18.0))

    if score >= 90:
        return (score, "EXCELLENT")
    if score >= 70:
        return (score, "GOOD")
    if score >= 50:
        return (score, "FAIR")
    return (score, "POOR")


def calculate_light_percentage_score(
    light_sleep_seconds: int | None,
    total_sleep_seconds: int | None,
) -> tuple[int, str]:
    """
    Calculate score for light sleep percentage.

    Optimal light sleep: 45-55% of total sleep (peak at 50%).

    Args:
        light_sleep_seconds: Duration of light sleep in seconds.
        total_sleep_seconds: Total sleep duration in seconds.

    Returns:
        Tuple of (score points 0-100, score label).
    """
    if total_sleep_seconds is None or total_sleep_seconds <= 0:
        return (0, "POOR")

    light_pct = _calculate_stage_percentage(light_sleep_seconds, total_sleep_seconds)
    score = int(_score_sleep_stage(light_pct, 45.0, 55.0, 50.0))

    if score >= 90:
        return (score, "EXCELLENT")
    if score >= 70:
        return (score, "GOOD")
    if score >= 50:
        return (score, "FAIR")
    return (score, "POOR")


def calculate_sleep_stress_score(
    avg_sleep_stress: int | None,
    restless_moments_count: int | None,
) -> tuple[int, str]:
    """
    Calculate sleep stress score.

    Based on average stress level and restless moments.
    Garmin stress scale: 0-25 (rest), 26-50 (low), 51-75 (med),
    76-100 (high).

    Args:
        avg_sleep_stress: Average stress level during sleep (0-100).
        restless_moments_count: Count of restless moments.

    Returns:
        Tuple of (score points 0-100, score label).
    """
    if avg_sleep_stress is None:
        return (50, "FAIR")

    stress_value = float(avg_sleep_stress)

    # Base score from stress level (inverted: lower stress =
    # higher score)
    if stress_value <= 25:  # Rest state
        base_score = 100
    elif stress_value <= 50:  # Low stress
        base_score = 90 - ((stress_value - 25) / 25 * 20)
    elif stress_value <= 75:  # Medium stress
        base_score = 70 - ((stress_value - 50) / 25 * 20)
    else:  # High stress
        base_score = 50 - ((stress_value - 75) / 25 * 50)

    # Penalty for restless moments
    restless_penalty = 0
    if restless_moments_count is not None:
        if restless_moments_count <= 5:
            restless_penalty = restless_moments_count * 2
        else:
            restless_penalty = 10 + ((restless_moments_count - 5) * 3)

    final_score = int(max(0, base_score - restless_penalty))

    if final_score >= 90:
        return (final_score, "EXCELLENT")
    if final_score >= 70:
        return (final_score, "GOOD")
    if final_score >= 50:
        return (final_score, "FAIR")
    return (final_score, "POOR")


def calculate_sleep_score_overall(
    sleep_start_time: datetime | None,
    sleep_end_time: datetime | None,
    total_sleep_seconds: int | None,
    deep_sleep_seconds: int | None,
    light_sleep_seconds: int | None,
    rem_sleep_seconds: int | None,
    awake_sleep_seconds: int | None,
    awake_count: int | None,
    restless_moments_count: int | None,
    avg_sleep_stress: int | None,
) -> int:
    """
    Calculate overall sleep score (0-100).

    Combines multiple sleep metrics with weighted contributions:
    - Duration score: 30%
    - Quality score: 40%
    - Awake count: 10%
    - Stress score: 20%

    Args:
        sleep_start_time: Start time of sleep session.
        sleep_end_time: End time of sleep session.
        total_sleep_seconds: Total sleep duration in seconds.
        deep_sleep_seconds: Duration of deep sleep in seconds.
        light_sleep_seconds: Duration of light sleep in seconds.
        rem_sleep_seconds: Duration of REM sleep in seconds.
        awake_sleep_seconds: Duration of awake time in seconds.
        awake_count: Number of times awakened during sleep.
        restless_moments_count: Count of restless moments.
        avg_sleep_stress: Average stress level during sleep.

    Returns:
        Overall sleep score from 0-100.
    """
    # Calculate component scores
    duration_score, _ = calculate_sleep_score_duration(
        sleep_start_time, sleep_end_time, total_sleep_seconds
    )

    quality_score, _ = calculate_sleep_score_quality(
        deep_sleep_seconds,
        light_sleep_seconds,
        rem_sleep_seconds,
        awake_sleep_seconds,
        total_sleep_seconds,
    )

    awake_score, _ = calculate_awake_count_score(awake_count)

    stress_score, _ = calculate_sleep_stress_score(
        avg_sleep_stress, restless_moments_count
    )

    # Weighted combination
    overall_score = int(
        (duration_score * 0.30)
        + (quality_score * 0.40)
        + (awake_score * 0.10)
        + (stress_score * 0.20)
    )

    return max(0, min(100, overall_score))


def _calculate_and_set_sleep_scores(
    health_sleep: health_sleep_schema.HealthSleep,
) -> None:
    """
    Calculate and set all sleep scores for a health sleep record.

    This function computes sleep quality scores and updates the
    health_sleep object in place with calculated values.

    Args:
        health_sleep: The health sleep record to update with scores.

    Returns:
        None: Updates health_sleep object in place.
    """
    # Calculate overall sleep score
    health_sleep.sleep_score_overall = calculate_sleep_score_overall(
        health_sleep.sleep_start_time_local,
        health_sleep.sleep_end_time_local,
        health_sleep.total_sleep_seconds,
        health_sleep.deep_sleep_seconds,
        health_sleep.light_sleep_seconds,
        health_sleep.rem_sleep_seconds,
        health_sleep.awake_sleep_seconds,
        health_sleep.awake_count,
        health_sleep.restless_moments_count,
        health_sleep.avg_sleep_stress,
    )

    # Calculate duration score
    _, duration_label = calculate_sleep_score_duration(
        health_sleep.sleep_start_time_local,
        health_sleep.sleep_end_time_local,
        health_sleep.total_sleep_seconds,
    )
    health_sleep.sleep_score_duration = health_sleep_schema.SleepScore(duration_label)

    # Calculate quality score
    _, quality_label = calculate_sleep_score_quality(
        health_sleep.deep_sleep_seconds,
        health_sleep.light_sleep_seconds,
        health_sleep.rem_sleep_seconds,
        health_sleep.awake_sleep_seconds,
        health_sleep.total_sleep_seconds,
    )
    health_sleep.sleep_score_quality = health_sleep_schema.SleepScore(quality_label)

    # Calculate awake count score
    _, awake_label = calculate_awake_count_score(health_sleep.awake_count)
    health_sleep.awake_count_score = health_sleep_schema.SleepScore(awake_label)

    # Calculate REM percentage score
    _, rem_label = calculate_rem_percentage_score(
        health_sleep.rem_sleep_seconds,
        health_sleep.total_sleep_seconds,
    )
    health_sleep.rem_percentage_score = health_sleep_schema.SleepScore(rem_label)

    # Calculate deep percentage score
    _, deep_label = calculate_deep_percentage_score(
        health_sleep.deep_sleep_seconds,
        health_sleep.total_sleep_seconds,
    )
    health_sleep.deep_percentage_score = health_sleep_schema.SleepScore(deep_label)

    # Calculate light percentage score
    _, light_label = calculate_light_percentage_score(
        health_sleep.light_sleep_seconds,
        health_sleep.total_sleep_seconds,
    )
    health_sleep.light_percentage_score = health_sleep_schema.SleepScore(light_label)

    # Calculate sleep stress score
    _, stress_label = calculate_sleep_stress_score(
        health_sleep.avg_sleep_stress,
        health_sleep.restless_moments_count,
    )
    health_sleep.sleep_stress_score = health_sleep_schema.SleepScore(stress_label)
