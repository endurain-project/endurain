"""Application logic for the daily health dashboard.

Reads each health package only through its ``integration_service``; the dashboard
owns no table.
"""

from sqlalchemy.orm import Session

import modules.health.health_dashboard.schema as health_dashboard_schema
import modules.health.health_fasting.integration_service as health_fasting_integration
import modules.health.health_poop.integration_service as health_poop_integration
import modules.health.health_sleep.integration_service as health_sleep_integration
import modules.health.health_steps.integration_service as health_steps_integration
import modules.health.health_targets.integration_service as health_targets_integration
import modules.health.health_water.integration_service as health_water_integration
import modules.health.health_weight.integration_service as health_weight_integration
import modules.users.users.integration_service as users_integration


def get_daily_stats(user_id: int, db: Session) -> health_dashboard_schema.HealthDashboardResponse:
    """Build a user's dashboard: today's sleep, steps, water and bowel movements, plus the latest weight and fast.

    "Today" is the user's own calendar day.

    Args:
        user_id: The dashboard's owner.
        db: Database session.

    Returns:
        The consolidated dashboard; a metric without data is ``None``.
    """
    today = str(users_integration.local_today(user_id, db))

    today_sleep = health_sleep_integration.get_health_sleep_by_date(user_id, today, db)
    latest_weight = health_weight_integration.get_latest_health_weight(user_id, db)
    today_steps = health_steps_integration.get_health_steps_by_date(user_id, today, db)
    active_fasting = health_fasting_integration.get_active_fasting(user_id, db)
    today_water = health_water_integration.get_health_water_by_date(user_id, today, db)
    today_poop_records = health_poop_integration.list_health_poop_by_date(user_id, today, db)
    targets = health_targets_integration.get_health_targets(user_id, db)

    sleep_data = None
    if today_sleep and today_sleep.hrv_status is not None:
        sleep_data = health_dashboard_schema.HealthSleepDashboard(
            total_sleep_seconds=today_sleep.total_sleep_seconds,
            resting_heart_rate=today_sleep.resting_heart_rate,
            hrv_status=str(today_sleep.hrv_status),
            avg_skin_temp_deviation=today_sleep.avg_skin_temp_deviation,
        )

    weight_data = None
    if latest_weight:
        weight_data = health_dashboard_schema.HealthWeightDashboard(
            weight=latest_weight.weight,
            bmi=latest_weight.bmi,
        )

    steps_data = None
    if today_steps:
        steps_data = health_dashboard_schema.HealthStepsDashboard(steps=today_steps.steps)

    fasting_data = None
    if active_fasting and active_fasting.fast_start_time is not None and active_fasting.status is not None:
        fasting_data = health_dashboard_schema.HealthFastingDashboard(
            id=active_fasting.id,
            fast_start_time=active_fasting.fast_start_time,
            fast_end_time=active_fasting.fast_end_time,
            status=str(active_fasting.status),
            actual_duration_seconds=active_fasting.actual_duration_seconds,
        )

    water_data = None
    if today_water and today_water.amount_ml is not None:
        water_data = health_dashboard_schema.HealthWaterDashboard(amount_ml=float(today_water.amount_ml))

    poop_data = None
    if today_poop_records:
        poop_data = health_dashboard_schema.HealthPoopDashboard(count=len(today_poop_records))

    return health_dashboard_schema.HealthDashboardResponse(
        sleep=sleep_data,
        weight=weight_data,
        steps=steps_data,
        fasting=fasting_data,
        water=water_data,
        poop=poop_data,
        targets=targets,
    )
