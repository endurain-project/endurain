"""Blocking, unblocking and the block list."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from jasil.audit.models import AuditLog
from sqlalchemy import select

import core.exceptions as core_exceptions
import modules.followers.audit_actions as followers_audit_actions
import modules.followers.crud as followers_crud
import modules.followers.events as followers_events
import modules.followers.service as followers_service
from tests._factories.followers import make_block, make_follow
from tests._factories.users import make_user
from tests.followers.conftest import audited

_NOW = datetime(2025, 3, 10, 12, 0, tzinfo=UTC)


class TestBlockUser:
    def test_blocking_stores_a_one_way_block_and_audits_it_without_details(self, db, alice, bob):
        followers_service.block_user(alice.id, bob.id, db)

        assert followers_crud.is_blocked(alice.id, bob.id, db)
        assert not followers_crud.is_blocked(bob.id, alice.id, db)
        assert audited(db) == [(followers_audit_actions.BLOCK_ADD.id, str(bob.id), str(alice.id))]
        assert db.scalar(select(AuditLog.details).where(AuditLog.action_id == "followers.block.add")) is None

    def test_blocking_twice_is_idempotent_and_audited_once(self, db, alice, bob):
        followers_service.block_user(alice.id, bob.id, db)
        followers_service.block_user(alice.id, bob.id, db)

        assert followers_crud.list_blocked_user_ids(alice.id, db) == [bob.id]
        assert len(audited(db)) == 1

    @pytest.mark.parametrize("state", ["missing", "inactive", "pending"])
    def test_blocking_a_user_who_is_hidden_answers_like_blocking_a_known_one(self, db, alice, bob, hide, state):
        target = uuid.uuid4()
        if state != "missing":
            target = bob.id
            hide(db, bob.id, state)

        assert followers_service.block_user(alice.id, target, db) is None

    def test_blocking_a_user_that_does_not_exist_stores_nothing(self, db, alice):
        followers_service.block_user(alice.id, uuid.uuid4(), db)

        assert followers_crud.list_blocked_user_ids(alice.id, db) == []
        assert audited(db) == []

    def test_blocking_removes_follows_in_both_directions_and_takes_back_the_pending_request(
        self, db, alice, bob, published
    ):
        make_follow(db, alice.id, bob.id, accepted=True)
        make_follow(db, bob.id, alice.id, accepted=False)

        followers_service.block_user(alice.id, bob.id, db)

        assert followers_crud.get_follower_for_user_id_and_target_user_id(alice.id, bob.id, db) is None
        assert followers_crud.get_follower_for_user_id_and_target_user_id(bob.id, alice.id, db) is None
        assert followers_crud.is_blocked(alice.id, bob.id, db)
        [event] = published
        assert event.event_type == followers_events.FOLLOWER_REQUEST_REMOVED
        assert event.source == "api:block_user"
        assert event.payload == {"requester_user_id": str(bob.id), "target_user_id": str(alice.id)}

    def test_blocking_does_not_record_a_decline(self, db, alice, bob):
        make_follow(db, bob.id, alice.id, accepted=False)

        followers_service.block_user(alice.id, bob.id, db)

        assert followers_crud.get_last_decline_at(bob.id, alice.id, db) is None

    def test_blocking_leaves_other_peoples_follows_alone(self, db, alice, bob, carol):
        make_follow(db, carol.id, alice.id, accepted=True)
        make_follow(db, carol.id, bob.id, accepted=True)

        followers_service.block_user(alice.id, bob.id, db)

        assert followers_crud.count_followers_by_user_id(alice.id, db) == 1
        assert followers_crud.count_followers_by_user_id(bob.id, db) == 1

    def test_blocking_notifies_nobody_when_nothing_was_pending(self, db, alice, bob, published):
        make_follow(db, alice.id, bob.id, accepted=True)

        followers_service.block_user(alice.id, bob.id, db)
        followers_service.block_user(alice.id, make_user(db).id, db)

        assert published == []


class TestUnblockUser:
    def test_unblocking_removes_the_block_and_audits_it(self, db, alice, bob):
        make_block(db, alice.id, bob.id)

        followers_service.unblock_user(alice.id, bob.id, db)

        assert not followers_crud.is_blocked(alice.id, bob.id, db)
        assert audited(db) == [(followers_audit_actions.BLOCK_REMOVE.id, str(bob.id), str(alice.id))]

    def test_follows_removed_by_the_block_are_not_restored(self, db, alice, bob):
        make_follow(db, bob.id, alice.id, accepted=True)
        followers_service.block_user(alice.id, bob.id, db)

        followers_service.unblock_user(alice.id, bob.id, db)

        assert followers_crud.count_followers_by_user_id(alice.id, db) == 0

    def test_unblocking_someone_not_blocked_is_not_found_and_audits_nothing(self, db, alice, bob):
        with pytest.raises(core_exceptions.NotFoundError):
            followers_service.unblock_user(alice.id, bob.id, db)

        assert audited(db) == []


class TestListBlockedUsers:
    def test_lists_the_public_projection_newest_block_first(self, db, alice, bob, carol):
        make_block(db, alice.id, bob.id, created_at=_NOW - timedelta(hours=1))
        make_block(db, alice.id, carol.id, created_at=_NOW)

        page = followers_service.list_blocked_users(alice.id, db, page_number=1, num_records=10)

        assert [user.id for user in page.items] == [carol.id, bob.id]
        assert page.total == 2
        assert set(page.items[0].model_dump()) == {"id", "name", "username", "city", "photo_path"}

    def test_total_and_pages_leave_out_the_same_hidden_users(self, db, alice, hide):
        blocked = [make_user(db) for _ in range(4)]
        for index, user in enumerate(blocked):
            make_block(db, alice.id, user.id, created_at=_NOW + timedelta(hours=index))
        hide(db, blocked[1].id, "inactive")

        first = followers_service.list_blocked_users(alice.id, db, page_number=1, num_records=2)
        second = followers_service.list_blocked_users(alice.id, db, page_number=2, num_records=2)

        assert (first.total, second.total) == (3, 3)
        assert [user.id for user in first.items] == [blocked[3].id, blocked[2].id]
        assert [user.id for user in second.items] == [blocked[0].id]
        assert (first.next, second.next) == (2, None)

    def test_lists_only_the_callers_blocks(self, db, alice, bob):
        make_block(db, bob.id, alice.id)

        page = followers_service.list_blocked_users(alice.id, db, page_number=1, num_records=10)

        assert (page.items, page.total) == ([], 0)
