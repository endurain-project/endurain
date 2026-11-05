"""The revoked-access deletion job pages through the due users and survives one user's failure."""

from unittest.mock import patch

import core.exceptions as core_exceptions
import modules.strava.constants as strava_constants
import modules.strava.scheduled_jobs as strava_scheduled_jobs


def test_the_job_is_registered_under_its_own_lock():
    (job,) = strava_scheduled_jobs.recurring_jobs()

    assert job.func is strava_scheduled_jobs.delete_revoked_data
    assert job.lock_name == strava_scheduled_jobs.REVOKED_DATA_DELETE_LOCK


def test_every_due_user_is_deleted_page_by_page():
    page = strava_constants.REVOKED_DELETE_PAGE_SIZE
    first = list(range(1, page + 1))
    pages = {0: first, page: [page + 1]}
    with (
        patch.object(
            strava_scheduled_jobs.strava_service, "revoked_user_ids_due", side_effect=lambda after, _n: pages[after]
        ),
        patch.object(strava_scheduled_jobs.strava_service, "delete_revoked_data") as delete,
    ):
        strava_scheduled_jobs.delete_revoked_data()

    assert [call.args[0] for call in delete.call_args_list] == [*first, page + 1]


def test_a_failed_user_is_logged_and_the_rest_still_run():
    with (
        patch.object(strava_scheduled_jobs.strava_service, "revoked_user_ids_due", return_value=[1, 2]),
        patch.object(
            strava_scheduled_jobs.strava_service,
            "delete_revoked_data",
            side_effect=[core_exceptions.DependencyFailedError("boom"), True],
        ) as delete,
    ):
        strava_scheduled_jobs.delete_revoked_data()

    assert [call.args[0] for call in delete.call_args_list] == [1, 2]


def test_no_due_user_does_nothing():
    with (
        patch.object(strava_scheduled_jobs.strava_service, "revoked_user_ids_due", return_value=[]),
        patch.object(strava_scheduled_jobs.strava_service, "delete_revoked_data") as delete,
    ):
        strava_scheduled_jobs.delete_revoked_data()

    delete.assert_not_called()
