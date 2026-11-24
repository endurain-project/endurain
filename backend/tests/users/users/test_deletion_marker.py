"""The queued-deletion marker, the approval gate and the sweep's queries, across committed sessions."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

import modules.users.users.crud as users_crud
import modules.users.users.models as users_models
from tests._factories.users import make_sign_up, make_user

_LATER = datetime.now(UTC) + timedelta(hours=1)


@pytest.fixture
def user_id(committed_sessions) -> uuid.UUID:
    with committed_sessions() as db:
        created = make_user(db)
        db.commit()
    return created.id


def _stage_and_commit(factory, user_id) -> None:
    with factory() as db:
        users_crud.stage_deletion_request(user_id, db)
        db.commit()


def _stalled(factory, **overrides) -> list[uuid.UUID]:
    args = {"requested_before": _LATER, "max_attempts": 5, "after_id": None, "limit": 100} | overrides
    with factory() as db:
        return users_crud.list_stalled_deletion_ids(
            args["requested_before"], args["max_attempts"], args["after_id"], args["limit"], db
        )


class TestQueuedDeletion:
    def test_a_queued_deletion_deactivates_the_user_and_is_found_once_stalled(self, committed_sessions, user_id):
        assert _stalled(committed_sessions) == []

        _stage_and_commit(committed_sessions, user_id)

        with committed_sessions() as db:
            user = db.get(users_models.Users, user_id)
            assert user.active is False
            assert user.deletion_requested_at is not None
            assert user.deletion_attempts == 0
        assert _stalled(committed_sessions) == [user_id]
        # Not stalled yet: queued after the cutoff.
        assert _stalled(committed_sessions, requested_before=datetime.now(UTC) - timedelta(hours=1)) == []

    def test_a_queued_deletion_shows_on_the_user_read(self, committed_sessions, user_id):
        with committed_sessions() as db:
            assert users_crud.get_user_by_id(user_id, db).deletion_requested_at is None

        _stage_and_commit(committed_sessions, user_id)

        with committed_sessions() as db:
            assert users_crud.get_user_by_id(user_id, db).deletion_requested_at is not None

    def test_a_user_past_the_attempt_cap_is_left_alone(self, committed_sessions, user_id):
        _stage_and_commit(committed_sessions, user_id)

        for _ in range(2):
            with committed_sessions() as db:
                users_crud.record_deletion_attempt(user_id, db)
                db.commit()

        assert _stalled(committed_sessions, max_attempts=3) == [user_id]
        assert _stalled(committed_sessions, max_attempts=2) == []

    def test_paging_resumes_after_the_last_id(self, committed_sessions, user_id):
        _stage_and_commit(committed_sessions, user_id)

        assert _stalled(committed_sessions, after_id=user_id) == []

    def test_recording_an_attempt_counts_it_and_ignores_an_account_not_queued(self, committed_sessions, user_id):
        with committed_sessions() as db:
            assert users_crud.record_deletion_attempt(user_id, db) is None

        _stage_and_commit(committed_sessions, user_id)
        with committed_sessions() as db:
            assert users_crud.record_deletion_attempt(user_id, db) == 1
            db.commit()
        with committed_sessions() as db:
            assert users_crud.record_deletion_attempt(user_id, db) == 2

    def test_reactivating_the_account_cancels_the_queued_deletion(self, committed_sessions, user_id):
        _stage_and_commit(committed_sessions, user_id)

        with committed_sessions() as db:
            users_crud.update_user(user_id, {"active": True}, db)
            db.commit()

        assert _stalled(committed_sessions) == []
        with committed_sessions() as db:
            assert users_crud.record_deletion_attempt(user_id, db) is None


class TestApproval:
    @pytest.fixture
    def waiting(self, committed_sessions) -> uuid.UUID:
        with committed_sessions() as db:
            created = make_sign_up(db, pending_admin_approval=True)
            db.commit()
        return created.id

    @staticmethod
    def _approve(factory, user_id) -> bool:
        with factory() as db:
            approved = users_crud.approve_pending_user(user_id, db)
            db.commit()
        return approved

    def test_approving_a_pending_user_activates_it_and_bumps_the_version(self, committed_sessions, waiting):
        with committed_sessions() as db:
            before = db.get(users_models.Users, waiting).version

        assert self._approve(committed_sessions, waiting) is True

        with committed_sessions() as db:
            user = db.get(users_models.Users, waiting)
            assert (user.active, user.pending_admin_approval, user.version) == (True, False, before + 1)

    @pytest.mark.parametrize("marker", ["deactivated_at", "deletion_requested_at"])
    def test_approval_leaves_a_deactivated_or_queued_user_untouched(self, committed_sessions, waiting, marker):
        with committed_sessions() as db:
            setattr(db.get(users_models.Users, waiting), marker, _LATER)
            db.commit()
        with committed_sessions() as db:
            before = db.get(users_models.Users, waiting).version

        assert self._approve(committed_sessions, waiting) is False

        with committed_sessions() as db:
            user = db.get(users_models.Users, waiting)
            assert (user.active, user.pending_admin_approval, user.version) == (False, True, before)
            assert getattr(user, marker) is not None

    def test_approval_leaves_an_already_approved_user_untouched(self, committed_sessions, user_id):
        assert self._approve(committed_sessions, user_id) is False
