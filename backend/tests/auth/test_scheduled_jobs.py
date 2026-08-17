"""The auth module declares its own recurring maintenance jobs.

``core.scheduler`` used to enumerate them, which meant the platform imported the
domain. These assertions pin the cadences that were previously asserted against
the scheduler's hard-coded list.
"""

import modules.auth.maintenance as auth_maintenance
import modules.auth.scheduled_jobs as auth_scheduled_jobs


class TestRecurringJobs:
    def test_every_callable_comes_from_the_maintenance_surface(self):
        """Auth's scheduled work is reached through its one maintenance module."""
        surface = {getattr(auth_maintenance, name) for name in auth_maintenance.__all__}
        assert {job.func for job in auth_scheduled_jobs.recurring_jobs()} <= surface

    def test_idp_link_token_cleanup_runs_every_five_minutes(self):
        jobs = [
            job
            for job in auth_scheduled_jobs.recurring_jobs()
            if job.func is auth_maintenance.delete_idp_link_expired_tokens_from_db
        ]
        assert len(jobs) == 1
        assert jobs[0].minutes == 5
        assert "idp link token" in jobs[0].description.lower()

    def test_descriptions_are_unique(self):
        """The description is the job's stable ID, so a duplicate silently drops a job."""
        descriptions = [job.description for job in auth_scheduled_jobs.recurring_jobs()]
        assert len(descriptions) == len(set(descriptions))
