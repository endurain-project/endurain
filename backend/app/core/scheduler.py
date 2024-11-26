from apscheduler.schedulers.background import BackgroundScheduler

import strava.utils as strava_utils
import strava.activity_utils as strava_activity_utils

import garmin.activity_utils as garmin_activity_utils

import core.logger as core_logger

scheduler = BackgroundScheduler()


def start_scheduler():
    # Start the scheduler
    scheduler.start()

    # Log the addition of the job to refresh Strava user tokens
    core_logger.print_to_log(
        "Added scheduler job to refresh Strava user tokens every 60 minutes"
    )
    scheduler.add_job(strava_utils.refresh_strava_tokens_job, "interval", minutes=60)

    # Log the addition of the job to retrieve last day Strava users activities
    core_logger.print_to_log(
        "Added scheduler job to retrieve last day Strava users activities every 60 minutes"
    )
    scheduler.add_job(
        strava_activity_utils.retrieve_strava_users_activities_for_days,
        "interval",
        minutes=60,
        args=[1],
    )

    # Log the addition of the job to retrieve last day Garmin Connect users activities
    core_logger.print_to_log(
        "Added scheduler job to retrieve last day Garmin Connect users activities every 60 minutes"
    )
    # Add scheduler jobs to retrieve last day activities from Garmin Connect
    scheduler.add_job(
        garmin_activity_utils.retrieve_garminconnect_users_activities_for_days,
        "interval",
        minutes=60,
        args=[1],
    )


def stop_scheduler():
    scheduler.shutdown()
