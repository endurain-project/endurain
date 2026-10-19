"""Tests for Strava recurring job declarations."""

import modules.strava.scheduled_jobs as strava_scheduled_jobs


def test_strava_declares_no_recurring_job_of_its_own():
    """The activity pull is one refresh job per linked user, queued by activity ingestion.

    It also refreshes that user's token, so there is no separate pass over every
    user to declare here.
    """
    assert strava_scheduled_jobs.recurring_jobs() == ()
