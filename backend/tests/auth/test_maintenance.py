"""Auth maintenance: stale sessions and past tokens are purged in bounded batches, and each job holds its lock."""

import contextlib
import types
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

import core.database as core_database
import core.scheduler as core_scheduler
import module_registry as runtime_module_registry
import modules.auth.password_reset_tokens.models as password_reset_models
import modules.auth.password_reset_tokens.service as password_reset_service
import modules.auth.sessions.models as sessions_models
import modules.auth.sessions.scheduled_jobs as sessions_jobs
import modules.auth.sessions.service as sessions_service
import modules.auth.sign_up_tokens.models as sign_up_models
import modules.auth.sign_up_tokens.service as sign_up_service
from tests._factories.auth import make_session
from tests._factories.server_settings import edit_server_settings
from tests._factories.tokens import make_reset_token, make_sign_up_token
from tests._factories.users import make_user

_PAST = datetime.now(UTC) - timedelta(days=2)
_CLEANED_UP_BY = ("oauth_state", "rotated_refresh_tokens", "password_reset_tokens", "sign_up_tokens", "sessions")


def _count(db, model) -> int:
    return db.scalar(sa.select(sa.func.count()).select_from(model))


def _module(name: str) -> runtime_module_registry.RuntimeModule:
    return next(module for module in runtime_module_registry.MODULES if module.name == name)


class TestSessionPurge:
    def test_expired_sessions_go_with_the_idle_timeout_off(self, db):
        edit_server_settings(db, session_idle_timeout_enabled=False)
        user = make_user(db)
        make_session(db, user, expires_at=_PAST)
        live = make_session(db, user)
        idle = make_session(db, user, last_activity_at=_PAST - timedelta(days=30))

        assert sessions_service.delete_expired_sessions(db) == 1
        assert sessions_service.delete_idle_sessions(db) == 0

        remaining = set(db.scalars(sa.select(sessions_models.UsersSessions.id)))
        assert remaining == {live.id, idle.id}

    def test_idle_sessions_go_past_the_configured_timeout(self, db):
        edit_server_settings(db, session_idle_timeout_enabled=True, session_idle_timeout_hours=1)
        user = make_user(db)
        idle = make_session(db, user, last_activity_at=datetime.now(UTC) - timedelta(hours=2))
        active = make_session(db, user, last_activity_at=datetime.now(UTC) - timedelta(minutes=30))

        assert sessions_service.delete_idle_sessions(db) == 1

        assert set(db.scalars(sa.select(sessions_models.UsersSessions.id))) == {active.id}
        assert idle.id not in set(db.scalars(sa.select(sessions_models.UsersSessions.id)))

    def test_the_job_runs_both_purges(self, db):
        edit_server_settings(db, session_idle_timeout_enabled=True, session_idle_timeout_hours=1)
        user = make_user(db)
        make_session(db, user, expires_at=_PAST)
        make_session(db, user, last_activity_at=datetime.now(UTC) - timedelta(hours=3))
        live = make_session(db, user)

        sessions_jobs.delete_stale_sessions()

        assert set(db.scalars(sa.select(sessions_models.UsersSessions.id))) == {live.id}


class TestTokenPurge:
    def test_past_tokens_go_across_batches_and_current_ones_stay(self, db, monkeypatch):
        monkeypatch.setattr(core_database, "PURGE_BATCH_SIZE", 2)
        stale_reset, current_reset = make_user(db), make_user(db)
        make_reset_token(db, stale_reset, expires_at=_PAST)
        make_reset_token(db, current_reset)
        stale_sign_ups = [make_user(db, active=False) for _ in range(3)]
        for user in stale_sign_ups:
            make_sign_up_token(db, user, expires_at=_PAST)
        make_sign_up_token(db, make_user(db, active=False))

        assert password_reset_service.delete_expired_password_reset_tokens(db) == 1
        assert sign_up_service.delete_expired_sign_up_tokens(db) == 3

        assert _count(db, password_reset_models.PasswordResetToken) == 1
        assert _count(db, sign_up_models.SignUpToken) == 1


class TestJobDeclarations:
    def test_every_cleanup_job_holds_a_lock_of_its_own(self):
        names = [job.lock_name for name in _CLEANED_UP_BY for job in _module(name).recurring_jobs()]

        assert names and all(names)
        assert len(names) == len(set(names))

    def test_a_token_purge_at_startup_shares_the_lock_of_its_recurring_job(self):
        for name in ("oauth_state", "password_reset_tokens", "sign_up_tokens"):
            module = _module(name)
            assert module.startup_tasks
            assert {task.lock_name for task in module.startup_tasks} == {
                job.lock_name for job in module.recurring_jobs()
            }

    def test_the_unverified_sign_up_purge_is_hourly_with_its_own_lock_and_startup_task(self):
        module = _module("sign_up_tokens")
        jobs = {job.func.__name__: job for job in module.recurring_jobs()}
        purge = jobs["delete_unverified_sign_ups_from_db"]

        assert purge.minutes == 60
        assert purge.lock_name == "auth_unverified_sign_ups_purge"
        assert purge.lock_name != jobs["delete_expired_tokens_from_db"].lock_name
        assert any(
            task.name == "purge_unverified_sign_ups" and task.lock_name == purge.lock_name
            for task in module.startup_tasks
        )

    def test_the_reencryption_startup_tasks_hold_distinct_locks(self):
        locks = [
            task.lock_name
            for module in runtime_module_registry.MODULES
            for task in module.startup_tasks
            if task.name.startswith("reencrypt_")
        ]

        assert len(locks) == 6 and all(locks) and len(set(locks)) == len(locks)

    def test_mfa_has_no_recurring_job(self):
        assert _module("mfa").recurring_jobs is None


class TestStartupTaskLock:
    def test_a_task_without_a_lock_runs(self):
        ran: list[str] = []

        runtime_module_registry.StartupTask("task", "Running task", lambda: ran.append("x")).run()

        assert ran == ["x"]

    def test_a_task_skips_while_another_replica_holds_its_lock(self, monkeypatch):
        ran: list[str] = []
        taken: list[str] = []

        class _HeldElsewhere:
            @contextlib.contextmanager
            def try_acquire(self, name: str, ttl_seconds: int | None = None):
                taken.append(name)
                yield False

        platform = types.SimpleNamespace(lock=_HeldElsewhere())
        monkeypatch.setattr(
            core_scheduler, "platform_runtime", types.SimpleNamespace(get_active_platform=lambda: platform)
        )

        runtime_module_registry.StartupTask("task", "Running task", lambda: ran.append("x"), lock_name="lock-b").run()

        assert (ran, taken) == ([], ["lock-b"])
