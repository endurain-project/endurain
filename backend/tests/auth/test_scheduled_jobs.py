"""The auth module declares its own recurring maintenance jobs.

``core.scheduler`` used to enumerate them, which meant the platform imported the
domain. These assertions pin the cadences that were previously asserted against
the scheduler's hard-coded list.
"""

import modules.auth.maintenance as auth_maintenance
import modules.auth.mfa.scheduled_jobs as mfa_scheduled_jobs
import modules.auth.password_reset_tokens.scheduled_jobs as password_reset_jobs
import modules.auth.scheduled_jobs as auth_scheduled_jobs
import modules.auth.sign_up_tokens.scheduled_jobs as sign_up_jobs


class TestRecurringJobs:
    def test_every_callable_comes_from_its_owning_surface(self):
        """The auth aggregate collects jobs from the owning auth packages."""
        surface = {getattr(auth_maintenance, name) for name in auth_maintenance.__all__}
        surface.update(job.func for job in mfa_scheduled_jobs.recurring_jobs())
        assert {job.func for job in auth_scheduled_jobs.recurring_jobs()} <= surface

    def test_pending_mfa_cleanup_runs_every_five_minutes(self):
        jobs = [
            job
            for job in auth_scheduled_jobs.recurring_jobs()
            if job.func is mfa_scheduled_jobs.cleanup_expired_pending_mfa_logins
        ]
        assert len(jobs) == 1
        assert jobs[0].minutes == 5

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

    def test_token_cleanup_is_owned_by_each_token_package(self):
        for jobs_module in (password_reset_jobs, sign_up_jobs):
            jobs = jobs_module.recurring_jobs()
            assert len(jobs) == 1
            assert jobs[0].minutes == 60
