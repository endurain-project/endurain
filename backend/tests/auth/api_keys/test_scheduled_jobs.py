"""The scheduled purge deletes API keys revoked or expired longer ago than the retention, and no others."""

import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa

import module_registry as runtime_module_registry
import modules.auth.api_keys.constants as api_keys_constants
import modules.auth.api_keys.models as api_keys_models
import modules.auth.api_keys.scheduled_jobs as api_keys_jobs
import modules.auth.api_keys.service as api_keys_service
from tests._factories.api_keys import make_api_key
from tests._factories.users import make_user

_SCOPES = [api_keys_constants.ApiKeyScope.ACTIVITIES_UPLOAD]
_RETENTION = api_keys_constants.STALE_API_KEY_RETENTION


def _arrange(committed_sessions) -> tuple[set[uuid.UUID], set[uuid.UUID]]:
    """Store keys around the retention boundary; return the ids that stay and those a purge deletes."""
    now = datetime.now(UTC)
    margin = timedelta(hours=1)
    with committed_sessions() as db:
        user = make_user(db)
        ids = {}
        for label, options in {
            "live": {},
            "expired_inside_retention": {"expires_at": now - _RETENTION + margin},
            "expired_beyond_retention": {"expires_at": now - _RETENTION - margin},
            "revoked_inside_retention": {},
            "revoked_beyond_retention": {},
        }.items():
            ids[label] = make_api_key(db, user, scopes=_SCOPES, name=label, **options)[0].id
        for label, revoked_at in (
            ("revoked_inside_retention", now - _RETENTION + margin),
            ("revoked_beyond_retention", now - _RETENTION - margin),
        ):
            db.execute(
                sa.update(api_keys_models.UsersApiKeys)
                .where(api_keys_models.UsersApiKeys.id == ids[label])
                .values(is_active=False, revoked_at=revoked_at)
            )
        db.commit()
    stale = {ids["expired_beyond_retention"], ids["revoked_beyond_retention"]}
    return set(ids.values()) - stale, stale


def _stored(committed_sessions) -> set[uuid.UUID]:
    with committed_sessions() as db:
        return set(db.scalars(sa.select(api_keys_models.UsersApiKeys.id)))


def test_the_service_deletes_the_keys_beyond_the_retention_and_commits(committed_sessions):
    kept, _ = _arrange(committed_sessions)

    with committed_sessions() as db:
        assert api_keys_service.delete_stale_api_keys(db) == 2

    assert _stored(committed_sessions) == kept


def test_the_job_purges_in_a_session_of_its_own(committed_sessions):
    kept, _ = _arrange(committed_sessions)

    api_keys_jobs.delete_stale_api_keys_from_db()

    assert _stored(committed_sessions) == kept


def test_the_purge_is_a_recurring_job_holding_a_distributed_lock():
    module = next(module for module in runtime_module_registry.MODULES if module.name == "api_keys")
    jobs = module.recurring_jobs()
    assert [job.lock_name for job in jobs] == [api_keys_jobs.PURGE_LOCK_NAME]
    assert jobs[0].func is api_keys_jobs.delete_stale_api_keys_from_db
