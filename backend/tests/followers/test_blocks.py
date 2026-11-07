"""Tests for the block list and the re-request cooldown."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import jasil.testing as jasil_testing
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import core.exceptions as core_exceptions
import modules.followers.audit_actions as followers_audit_actions
import modules.followers.constants as followers_constants
import modules.followers.crud as followers_crud
import modules.followers.service as followers_service
import modules.users.users.models as users_models
from tests._helpers.db import create_sqlite_session_factory, ensure_user


@pytest.fixture
def factory():
    factory = create_sqlite_session_factory()
    ensure_user(factory, 1)
    ensure_user(factory, 2)
    yield factory
    factory.kw["bind"].dispose()


def _hide(factory, user_id: int, state: str) -> None:
    with factory() as db:
        user = db.get(users_models.Users, user_id)
        user.active = state != "inactive"
        user.pending_admin_approval = state == "pending"
        db.commit()


class TestBlockUser:
    def test_blocking_stores_the_block_and_audits_it(self, factory):
        with factory() as db, jasil_testing.capture_audit() as audit:
            followers_service.block_user(1, 2, db)

        with factory() as db:
            assert followers_crud.is_blocked(1, 2, db)
            assert not followers_crud.is_blocked(2, 1, db)
        entry = audit.assert_audited(
            followers_audit_actions.BLOCK_ADD.id, target_type="user", target_id="2", target_owner_id="1"
        )
        assert entry.details is None

    def test_blocking_twice_is_idempotent_and_audited_once(self, factory):
        with factory() as db:
            followers_service.block_user(1, 2, db)
        with factory() as db, jasil_testing.capture_audit() as audit:
            followers_service.block_user(1, 2, db)

        audit.assert_not_audited(followers_audit_actions.BLOCK_ADD.id)
        with factory() as db:
            assert len(followers_crud.list_blocked_user_ids(1, db)) == 1

    @pytest.mark.parametrize("state", ["missing", "inactive", "pending"])
    def test_blocking_a_hidden_user_answers_like_blocking_a_known_one(self, factory, state):
        if state == "missing":
            target = 99
        else:
            target = 2
            _hide(factory, target, state)

        with factory() as db:
            assert followers_service.block_user(1, target, db) is None

    def test_blocking_removes_follows_in_both_directions_including_pending(self, factory):
        with factory() as db:
            followers_crud.create_follower(1, 2, db)
            followers_crud.accept_follower(2, 1, db)
            followers_crud.create_follower(2, 1, db)
            db.commit()

        with factory() as db, patch("modules.followers.service.followers_event_publishers") as publishers:
            publishers.publish_follower_request_removed.side_effect = lambda *a, commit, **k: commit()
            followers_service.block_user(1, 2, db)

        with factory() as db:
            assert followers_crud.get_follower_for_user_id_and_target_user_id(1, 2, db) is None
            assert followers_crud.get_follower_for_user_id_and_target_user_id(2, 1, db) is None
            assert followers_crud.is_blocked(1, 2, db)
        publishers.publish_follower_request_removed.assert_called_once()

    def test_blocking_notifies_nobody_when_nothing_was_pending(self, factory):
        with factory() as db, patch("modules.followers.service.followers_event_publishers") as publishers:
            followers_service.block_user(1, 2, db)

        publishers.publish_follower_requested.assert_not_called()
        publishers.publish_follower_accepted.assert_not_called()
        publishers.publish_follower_request_removed.assert_not_called()


class TestUnblockUser:
    def test_unblocking_removes_the_block_and_audits_it(self, factory):
        with factory() as db:
            followers_service.block_user(1, 2, db)

        with factory() as db, jasil_testing.capture_audit() as audit:
            followers_service.unblock_user(1, 2, db)

        with factory() as db:
            assert not followers_crud.is_blocked(1, 2, db)
        audit.assert_audited(
            followers_audit_actions.BLOCK_REMOVE.id, target_type="user", target_id="2", target_owner_id="1"
        )

    def test_unblocking_someone_not_blocked_is_not_found(self, factory):
        with factory() as db, pytest.raises(core_exceptions.NotFoundError):
            followers_service.unblock_user(1, 2, db)


class TestListBlockedUsers:
    def test_lists_the_public_projection_newest_block_first(self, factory):
        ensure_user(factory, 3)
        with factory() as db:
            followers_service.block_user(1, 2, db)
            followers_service.block_user(1, 3, db)

        with factory() as db:
            page = followers_service.list_blocked_users(1, db, page_number=1, num_records=10)

        assert [user.id for user in page.items] == [3, 2]
        assert page.total == 2
        assert set(page.items[0].model_dump()) == {"id", "name", "username", "city", "photo_path"}

    def test_total_and_pages_leave_out_the_same_hidden_users(self, factory):
        for user_id in (3, 4, 5):
            ensure_user(factory, user_id)
        with factory() as db:
            for user_id in (2, 3, 4, 5):
                followers_service.block_user(1, user_id, db)
        _hide(factory, 3, "inactive")

        with factory() as db:
            first = followers_service.list_blocked_users(1, db, page_number=1, num_records=2)
            second = followers_service.list_blocked_users(1, db, page_number=2, num_records=2)

        assert (first.total, second.total) == (3, 3)
        assert [user.id for user in first.items] == [5, 4]
        assert [user.id for user in second.items] == [2]
        assert first.next == 2 and second.next is None

    def test_lists_only_the_callers_blocks(self, factory):
        with factory() as db:
            followers_service.block_user(2, 1, db)

        with factory() as db:
            page = followers_service.list_blocked_users(1, db, page_number=1, num_records=10)

        assert page.items == []
        assert page.total == 0


class TestFollowRefusals:
    def test_a_blocked_requester_gets_the_answer_for_a_target_that_cannot_be_followed(self, factory):
        with factory() as db:
            followers_service.block_user(2, 1, db)

        with factory() as db, pytest.raises(core_exceptions.NotFoundError) as blocked:
            followers_service.follow_user(1, 2, db)
        _hide(factory, 2, "inactive")
        with factory() as db, pytest.raises(core_exceptions.NotFoundError) as hidden:
            followers_service.follow_user(1, 2, db)

        assert (blocked.value.status_code, blocked.value.detail) == (hidden.value.status_code, hidden.value.detail)

    def test_the_blocker_cannot_follow_the_user_they_blocked(self, factory):
        with factory() as db:
            followers_service.block_user(1, 2, db)

        with factory() as db, pytest.raises(core_exceptions.ConflictError) as refused:
            followers_service.follow_user(1, 2, db)

        assert refused.value.status_code == 409
        assert refused.value.detail == "Unblock this user first"
        with factory() as db:
            assert followers_crud.get_follower_for_user_id_and_target_user_id(1, 2, db) is None

    def test_a_request_from_a_blocked_user_cannot_be_accepted(self, factory):
        with factory() as db:
            followers_crud.create_follower(2, 1, db)
            db.commit()
        with factory() as db:
            followers_service.block_user(1, 2, db)

        with (
            factory() as db,
            patch("modules.followers.service.followers_crud.lock_accepted_followees"),
            pytest.raises(core_exceptions.NotFoundError),
        ):
            followers_service.accept_follow_request(1, 2, db)

    def test_a_declined_requester_waits_seven_days(self, factory):
        declined_at = datetime.now(UTC) - timedelta(days=1)
        with factory() as db:
            followers_crud.record_decline(1, 2, declined_at, db)
            db.commit()

        with factory() as db, pytest.raises(core_exceptions.TooManyRequestsError) as refused:
            followers_service.follow_user(1, 2, db)

        assert refused.value.status_code == 429
        assert refused.value.retry_at == declined_at + followers_constants.FOLLOW_REQUEST_COOLDOWN

    def test_the_cooldown_ends_after_seven_days(self, factory):
        declined_at = datetime.now(UTC) - followers_constants.FOLLOW_REQUEST_COOLDOWN - timedelta(minutes=1)
        with factory() as db:
            followers_crud.record_decline(1, 2, declined_at, db)
            db.commit()

        with factory() as db, patch("modules.followers.service.followers_event_publishers") as publishers:
            publishers.publish_follower_requested.side_effect = lambda *a, commit, **k: commit()
            with patch("modules.followers.service.followers_crud.lock_pending_requests"):
                followers_service.follow_user(1, 2, db)

    def test_declining_records_the_decline(self, factory):
        with factory() as db:
            followers_crud.create_follower(1, 2, db)
            db.commit()

        with factory() as db, patch("modules.followers.service.followers_event_publishers") as publishers:
            publishers.publish_follower_request_removed.side_effect = lambda *a, commit, **k: commit()
            followers_service.reject_follow_request(2, 1, db)

        with factory() as db:
            declined_at = followers_crud.get_last_decline_at(1, 2, db)
        assert declined_at is not None
        assert datetime.now(UTC) - declined_at < timedelta(minutes=1)

    def test_removing_a_pending_follower_through_the_relationship_also_records_the_decline(self, factory):
        with factory() as db:
            followers_crud.create_follower(1, 2, db)
            db.commit()

        with factory() as db, patch("modules.followers.service.followers_event_publishers") as publishers:
            publishers.publish_follower_request_removed.side_effect = lambda *a, commit, **k: commit()
            followers_service.delete_relationship(2, 1, 2, db)

        with factory() as db:
            assert followers_crud.get_last_decline_at(1, 2, db) is not None

    def test_withdrawing_your_own_request_is_not_a_decline(self, factory):
        with factory() as db:
            followers_crud.create_follower(1, 2, db)
            db.commit()

        with factory() as db, patch("modules.followers.service.followers_event_publishers") as publishers:
            publishers.publish_follower_request_removed.side_effect = lambda *a, commit, **k: commit()
            followers_service.delete_relationship(2, 1, 1, db)

        with factory() as db:
            assert followers_crud.get_last_decline_at(1, 2, db) is None


class TestRelationshipReportsTheCallersBlock:
    def test_is_blocked_is_the_callers_block_of_the_other_user(self, factory):
        with factory() as db:
            followers_service.block_user(1, 2, db)

        with factory() as db:
            mine = followers_service.get_user_relationship(2, 1, db)
            theirs = followers_service.get_user_relationship(1, 2, db)

        assert mine.is_blocked is True
        assert theirs.is_blocked is False


def _build_app(mock_db):
    import core.database as core_db
    import modules.auth.dependencies as auth_deps
    import modules.followers.blocks_router as router

    app = FastAPI()
    app.include_router(router.router, prefix="/profile/blocked-users")
    core_exceptions.register_exception_handlers(app)
    app.dependency_overrides[auth_deps.check_scopes] = lambda: None
    app.dependency_overrides[auth_deps.get_sub_from_access_token] = lambda: 1
    app.dependency_overrides[core_db.get_db] = lambda: mock_db
    return app


class TestBlocksRouter:
    @patch("modules.followers.service.block_user")
    def test_put_blocks_and_answers_204(self, mock_block, mock_db):
        response = TestClient(_build_app(mock_db)).put(
            "/profile/blocked-users/2", headers={"Authorization": "Bearer x"}
        )

        assert response.status_code == 204
        mock_block.assert_called_once_with(1, 2, mock_db)

    @patch("modules.followers.service.block_user")
    def test_blocking_yourself_is_422(self, mock_block, mock_db):
        response = TestClient(_build_app(mock_db)).put(
            "/profile/blocked-users/1", headers={"Authorization": "Bearer x"}
        )

        assert response.status_code == 422
        mock_block.assert_not_called()

    @patch("modules.followers.service.unblock_user")
    def test_delete_unblocks_and_answers_204(self, mock_unblock, mock_db):
        response = TestClient(_build_app(mock_db)).delete(
            "/profile/blocked-users/2", headers={"Authorization": "Bearer x"}
        )

        assert response.status_code == 204
        mock_unblock.assert_called_once_with(1, 2, mock_db)

    @patch("modules.followers.service.list_blocked_users")
    def test_get_lists_a_page(self, mock_list, mock_db):
        import modules.users.users.schema as users_schema

        mock_list.return_value = users_schema.UserPublicPage.build(
            [users_schema.UserPublicRead(id=2, name="Bob", username="bob")], 1, 1, 100
        )

        response = TestClient(_build_app(mock_db)).get("/profile/blocked-users", headers={"Authorization": "Bearer x"})

        assert response.status_code == 200
        assert response.json()["items"][0]["username"] == "bob"
        assert response.json()["total"] == 1
