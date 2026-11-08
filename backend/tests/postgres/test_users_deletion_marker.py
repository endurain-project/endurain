"""The queued-deletion marker and the sweep's queries, against real PostgreSQL."""

from datetime import UTC, datetime, timedelta

import pytest

import modules.users.users.crud as users_crud
import modules.users.users.models as users_models
from tests._helpers.db import ensure_user

_LATER = datetime.now(UTC) + timedelta(hours=1)


@pytest.fixture
def factory(pg_factory):
    ensure_user(pg_factory, 1)
    with pg_factory() as db:
        # The helper's placeholder language is not one the read schema accepts.
        db.get(users_models.Users, 1).preferred_language = "en"
        db.commit()
    return pg_factory


def _stage_and_commit(factory) -> None:
    with factory() as db:
        users_crud.stage_deletion_request(1, db)
        db.commit()


def _stalled(factory, **overrides) -> list[int]:
    args = {"requested_before": _LATER, "max_attempts": 5, "after_id": 0, "limit": 100} | overrides
    with factory() as db:
        return users_crud.list_stalled_deletion_ids(
            args["requested_before"], args["max_attempts"], args["after_id"], args["limit"], db
        )


def test_a_queued_deletion_deactivates_the_user_and_is_found_once_stalled(factory):
    assert _stalled(factory) == []

    _stage_and_commit(factory)

    with factory() as db:
        user = db.get(users_models.Users, 1)
        assert user.active is False
        assert user.deletion_requested_at is not None
        assert user.deletion_attempts == 0
    assert _stalled(factory) == [1]
    # Not stalled yet: queued after the cutoff.
    assert _stalled(factory, requested_before=datetime.now(UTC) - timedelta(hours=1)) == []


def test_a_queued_deletion_shows_on_the_user_read(factory):
    with factory() as db:
        assert users_crud.get_user_by_id(1, db).deletion_requested_at is None

    _stage_and_commit(factory)

    with factory() as db:
        assert users_crud.get_user_by_id(1, db).deletion_requested_at is not None


def test_a_user_past_the_attempt_cap_is_left_alone(factory):
    _stage_and_commit(factory)

    for _ in range(2):
        with factory() as db:
            users_crud.record_deletion_attempt(1, db)
            db.commit()

    assert _stalled(factory, max_attempts=3) == [1]
    assert _stalled(factory, max_attempts=2) == []


def test_paging_resumes_after_the_last_id(factory):
    _stage_and_commit(factory)

    assert _stalled(factory, after_id=1) == []


def test_recording_an_attempt_counts_it_and_ignores_an_account_not_queued(factory):
    with factory() as db:
        assert users_crud.record_deletion_attempt(1, db) is None

    _stage_and_commit(factory)
    with factory() as db:
        assert users_crud.record_deletion_attempt(1, db) == 1
        db.commit()
    with factory() as db:
        assert users_crud.record_deletion_attempt(1, db) == 2


def test_reactivating_the_account_cancels_the_queued_deletion(factory):
    _stage_and_commit(factory)

    with factory() as db:
        users_crud.update_user(1, {"active": True}, db)
        db.commit()

    assert _stalled(factory) == []
    with factory() as db:
        assert users_crud.record_deletion_attempt(1, db) is None


def _approve(factory) -> bool:
    with factory() as db:
        approved = users_crud.approve_pending_user(1, db)
        db.commit()
    return approved


def _set(factory, **fields) -> None:
    with factory() as db:
        for name, value in fields.items():
            setattr(db.get(users_models.Users, 1), name, value)
        db.commit()


def test_approving_a_pending_user_activates_it_and_bumps_the_version(factory):
    _set(factory, active=False, pending_admin_approval=True)
    with factory() as db:
        before = db.get(users_models.Users, 1).version

    assert _approve(factory) is True

    with factory() as db:
        user = db.get(users_models.Users, 1)
        assert (user.active, user.pending_admin_approval, user.version) == (True, False, before + 1)


@pytest.mark.parametrize("marker", ["deactivated_at", "deletion_requested_at"])
def test_approval_leaves_a_deactivated_or_queued_user_untouched(factory, marker):
    _set(factory, active=False, pending_admin_approval=True, **{marker: _LATER})
    with factory() as db:
        before = db.get(users_models.Users, 1).version

    assert _approve(factory) is False

    with factory() as db:
        user = db.get(users_models.Users, 1)
        assert (user.active, user.pending_admin_approval, user.version) == (False, True, before)
        assert getattr(user, marker) is not None


def test_approval_leaves_an_already_approved_user_untouched(factory):
    assert _approve(factory) is False
