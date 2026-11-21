"""The users' persistence, on the real database."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

import core.etag as core_etag
import core.exceptions as core_exceptions
import modules.auth.identity_provider_links.integration_service as identity_provider_links_integration
import modules.users.users.crud as users_crud
import modules.users.users.models as users_models
from tests._factories.identity_links import make_identity_link, make_identity_provider
from tests._factories.users import make_admin, make_user

_LATER = datetime.now(UTC) + timedelta(hours=1)


def _row(db, user_id) -> users_models.Users:
    """Read the stored row, refreshed from the database."""
    row = db.get(users_models.Users, user_id)
    db.refresh(row)
    return row


class TestReads:
    def test_a_user_is_read_by_id_and_a_missing_one_is_none(self, db):
        user = make_user(db, city="Porto")

        assert users_crud.get_user_by_id(user.id, db).city == "Porto"
        assert users_crud.get_user_by_id(uuid.uuid4(), db) is None

    def test_an_email_is_found_whatever_its_case(self, db):
        user = make_user(db, email="Mixed.Case@example.com".lower())

        assert users_crud.get_user_by_email("MIXED.CASE@EXAMPLE.COM", db).id == user.id
        assert users_crud.get_user_by_email("nobody@example.com", db) is None

    def test_a_username_is_found_whatever_its_case(self, db):
        user = make_user(db, username="some.name")

        assert users_crud.get_user_by_username("Some.NAME", db).id == user.id
        assert users_crud.get_user_by_username("other", db) is None

    def test_only_administrators_are_listed_as_administrators(self, db):
        admin = make_admin(db)
        make_user(db)

        assert [user.id for user in users_crud.get_users_admin(db)] == [admin.id]

    def test_several_users_are_read_in_one_call_and_a_repeated_id_is_read_once(self, db):
        first, second = make_user(db), make_user(db)
        make_user(db)

        found = users_crud.get_users_by_ids([first.id, second.id, first.id, uuid.uuid4()], db)

        assert sorted(user.id for user in found) == sorted([first.id, second.id])

    def test_no_ids_read_nothing(self, db):
        make_user(db)

        assert users_crud.get_users_by_ids([], db) == []

    def test_the_users_table_is_empty_until_a_user_exists(self, db):
        assert users_crud.any_user_exists(db) is False

        make_user(db)

        assert users_crud.any_user_exists(db) is True

    def test_the_stored_photo_keys_are_the_raw_column_values(self, db):
        with_photo = make_user(db, photo_path="the-key.png")
        without = make_user(db)

        assert dict(users_crud.get_stored_photo_keys(db)) == {with_photo.id: "the-key.png", without.id: None}

    def test_a_users_photo_key_is_read_and_a_missing_user_has_none(self, db):
        user = make_user(db, photo_path="the-key.png")

        assert users_crud.get_photo_key(user.id, db) == "the-key.png"
        assert users_crud.get_photo_key(uuid.uuid4(), db) is None

    def test_the_photo_keys_of_several_users_leave_out_those_without_a_photo(self, db):
        with_photo = make_user(db, photo_path="a.png")
        without = make_user(db)

        assert users_crud.get_photo_keys_by_user_ids([with_photo.id, without.id, uuid.uuid4()], db) == {
            with_photo.id: "a.png"
        }

    def test_a_user_is_created_after_a_moment_only_when_it_is_newer(self, db):
        moment = datetime(2025, 1, 1, tzinfo=UTC)
        newer = make_user(db, created_at=moment + timedelta(seconds=1))
        same = make_user(db, created_at=moment)
        older = make_user(db, created_at=moment - timedelta(seconds=1))

        assert users_crud.was_created_after(newer.id, moment, db) is True
        assert users_crud.was_created_after(same.id, moment, db) is False
        assert users_crud.was_created_after(older.id, moment, db) is False
        assert users_crud.was_created_after(uuid.uuid4(), moment, db) is False

    def test_a_user_is_deactivated_when_it_carries_a_deactivation_time(self, db):
        active = make_user(db)
        deactivated = make_user(db, active=False)
        sign_up = make_user(db, active=False, deactivated_at=None, pending_admin_approval=True)

        assert users_crud.is_deactivated(active.id, db) is False
        assert users_crud.is_deactivated(deactivated.id, db) is True
        assert users_crud.is_deactivated(sign_up.id, db) is False

    def test_the_deactivation_of_a_missing_user_is_not_found(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            users_crud.is_deactivated(uuid.uuid4(), db)


class TestListFilters:
    @pytest.fixture
    def people(self, db):
        return {
            "active": make_user(db, username="anna"),
            "inactive": make_user(db, username="bruno", active=False),
            "pending": make_user(db, username="carla", active=False, deactivated_at=None, pending_admin_approval=True),
            "unverified": make_user(db, username="dora", email_verified=False),
        }

    @staticmethod
    def _names(db, **filters) -> list[str]:
        return [user.username for user in users_crud.get_users_with_pagination(db, **filters)]

    def test_users_are_listed_by_username_with_the_total_of_the_filter(self, db, people):
        assert self._names(db) == ["anna", "bruno", "carla", "dora"]
        assert users_crud.get_users_number(db) == 4

    @pytest.mark.parametrize(
        ("filters", "expected"),
        [
            ({"active": True}, ["anna", "dora"]),
            ({"active": False}, ["bruno", "carla"]),
            ({"email_verified": False}, ["dora"]),
            ({"pending_approval": True}, ["carla"]),
            ({"pending_approval": False, "active": False}, ["bruno"]),
            ({"username": "ANNA"}, ["anna"]),
            ({"username_contains": "OR"}, ["dora"]),
        ],
    )
    def test_a_filter_keeps_only_the_users_in_that_state(self, db, people, filters, expected):
        assert self._names(db, **filters) == expected
        assert users_crud.get_users_number(db, **filters) == len(expected)

    def test_the_excluded_users_are_left_out_of_the_page_and_the_count(self, db, people):
        excluded = [people["active"].id, people["inactive"].id]

        assert self._names(db, exclude_user_ids=excluded) == ["carla", "dora"]
        assert users_crud.get_users_number(db, exclude_user_ids=excluded) == 2

    def test_the_external_auth_filter_uses_the_users_with_a_provider_link(self, db, people):
        idp = make_identity_provider(db, "crud-idp")
        make_identity_link(db, people["inactive"].id, idp, "subject-1")
        linked = identity_provider_links_integration.select_linked_user_ids()

        assert self._names(db, external_auth=True, linked_user_ids=linked) == ["bruno"]
        assert self._names(db, external_auth=False, linked_user_ids=linked) == ["anna", "carla", "dora"]
        assert users_crud.get_users_number(db, external_auth=True, linked_user_ids=linked) == 1

    def test_a_page_is_a_window_of_the_username_order(self, db, people):
        assert self._names(db, page_number=2, num_records=2) == ["carla", "dora"]
        assert self._names(db, page_number=3, num_records=2) == []

    def test_a_page_is_skipped_without_both_arguments(self, db, people):
        assert len(self._names(db, page_number=2)) == 4
        assert len(self._names(db, num_records=1)) == 4


class TestCreate:
    def test_a_user_is_stored_with_its_defaults(self, db):
        created = users_crud.create_user(
            {
                "name": "Anna",
                "username": "anna",
                "email": "anna@example.com",
                "preferred_language": "en",
                "access_type": "regular",
            },
            db,
        )

        row = _row(db, created.id)
        assert (row.username, row.units, row.gender, row.currency, row.first_day_of_week) == (
            "anna",
            "metric",
            "male",
            "euro",
            "monday",
        )
        assert (row.active, row.email_verified, row.pending_admin_approval, row.version) == (True, False, False, 1)
        assert (row.deactivated_at, row.deletion_requested_at, row.deletion_attempts) == (None, None, 0)
        assert row.created_at is not None

    @pytest.mark.parametrize("field", ["username", "email"])
    def test_a_taken_username_or_email_is_a_conflict(self, db, field):
        taken = make_user(db)
        values = {"name": "Other", "username": "free", "email": "free@example.com", "preferred_language": "en"}
        values.update(access_type="regular", **{field: getattr(taken, field)})

        with pytest.raises(core_exceptions.ConflictError, match="Duplicate entry"):
            users_crud.create_user(values, db)

    def test_the_database_refuses_an_unknown_access_type(self, db):
        with pytest.raises(IntegrityError, match="ck_users_access_type"):
            db.add(
                users_models.Users(
                    name="X", username="x", email="x@example.com", preferred_language="en", access_type="superuser"
                )
            )
            db.flush()


class TestUpdate:
    def test_the_changes_are_stored_and_the_version_moves(self, db):
        user = make_user(db, city="Porto")

        updated = users_crud.update_user(user.id, {"city": "Lisbon", "height": 180}, db)

        row = _row(db, user.id)
        assert (updated.city, updated.height, updated.version) == ("Lisbon", 180, user.version + 1)
        assert (row.city, row.height) == ("Lisbon", 180)

    def test_a_response_only_property_is_skipped(self, db):
        user = make_user(db)

        users_crud.update_user(user.id, {"photo_url": "ignored", "city": "Faro"}, db)

        assert _row(db, user.id).city == "Faro"

    def test_a_missing_user_is_not_found(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            users_crud.update_user(uuid.uuid4(), {"city": "Faro"}, db)

    @pytest.mark.parametrize("field", ["username", "email"])
    def test_taking_another_users_username_or_email_is_a_conflict(self, db, field):
        other = make_user(db)
        user = make_user(db)

        with pytest.raises(core_exceptions.ConflictError):
            users_crud.update_user(user.id, {field: getattr(other, field)}, db)

    def test_an_edit_that_names_the_stored_version_is_applied(self, db):
        user = make_user(db)

        users_crud.update_user(user.id, {"city": "Faro"}, db, if_match=core_etag.format_etag(user.version))

        assert _row(db, user.id).city == "Faro"

    def test_an_edit_that_names_another_version_is_refused_and_changes_nothing(self, db):
        user = make_user(db, city="Porto")

        with pytest.raises(core_exceptions.PreconditionFailedError):
            users_crud.update_user(user.id, {"city": "Faro"}, db, if_match='"99"')

        assert _row(db, user.id).city == "Porto"

    def test_deactivating_an_active_user_stamps_the_deactivation_time(self, db):
        user = make_user(db)

        users_crud.update_user(user.id, {"active": False}, db)

        assert _row(db, user.id).deactivated_at is not None

    def test_deactivating_an_inactive_user_keeps_its_first_deactivation_time(self, db):
        stamp = datetime(2024, 5, 1, tzinfo=UTC)
        user = make_user(db, active=False, deactivated_at=stamp)

        users_crud.update_user(user.id, {"active": False}, db)

        assert _row(db, user.id).deactivated_at == stamp

    def test_reactivating_a_user_clears_the_deactivation_and_cancels_a_queued_deletion(self, db):
        user = make_user(db)
        users_crud.stage_deletion_request(user.id, db)
        users_crud.record_deletion_attempt(user.id, db)

        users_crud.update_user(user.id, {"active": True}, db)

        row = _row(db, user.id)
        assert (row.active, row.deactivated_at, row.deletion_requested_at, row.deletion_attempts) == (
            True,
            None,
            None,
            0,
        )

    def test_another_edit_leaves_a_queued_deletion_alone(self, db):
        user = make_user(db)
        users_crud.stage_deletion_request(user.id, db)

        users_crud.update_user(user.id, {"city": "Faro"}, db)

        assert _row(db, user.id).deletion_requested_at is not None


class TestPhotoKeys:
    def test_replacing_the_key_returns_the_one_it_replaced(self, db):
        user = make_user(db, photo_path="old.png")

        assert users_crud.replace_photo_key(user.id, "new.png", db) == "old.png"
        assert users_crud.get_photo_key(user.id, db) == "new.png"
        assert users_crud.replace_photo_key(user.id, None, db) == "new.png"
        assert users_crud.replace_photo_key(user.id, "again.png", db) is None

    def test_replacing_the_key_of_a_missing_user_is_not_found(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            users_crud.replace_photo_key(uuid.uuid4(), "x.png", db)

    def test_a_batch_rewrites_a_key_only_where_the_user_still_holds_the_old_one(self, db):
        moved = make_user(db, photo_path="a.png")
        changed_since = make_user(db, photo_path="elsewhere.png")
        version = _row(db, moved.id).version

        users_crud.replace_photo_keys([(moved.id, "a.png", "b.png"), (changed_since.id, "a.png", "b.png")], db)

        assert users_crud.get_photo_key(moved.id, db) == "b.png"
        assert users_crud.get_photo_key(changed_since.id, db) == "elsewhere.png"
        assert _row(db, moved.id).version == version


class TestAdministratorLock:
    def test_the_active_administrators_are_returned_in_id_order(self, db):
        admins = [make_admin(db) for _ in range(3)]
        make_admin(db, active=False)
        make_user(db)

        assert users_crud.lock_active_admin_ids(db) == sorted(admin.id for admin in admins)

    def test_the_first_admin_lock_is_a_transaction_scoped_advisory_lock(self, db):
        users_crud.lock_first_admin_creation(db)

        held = db.execute(
            sa.text("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND pid = pg_backend_pid()")
        ).scalar_one()
        assert held == 1


class TestApproval:
    def test_a_pending_user_is_approved_and_activated(self, db):
        user = make_user(db, active=False, deactivated_at=None, pending_admin_approval=True)

        assert users_crud.approve_pending_user(user.id, db) is True

        row = _row(db, user.id)
        assert (row.active, row.pending_admin_approval) == (True, False)

    @pytest.mark.parametrize("marker", ["deactivated_at", "deletion_requested_at"])
    def test_a_deactivated_or_queued_pending_user_is_left_untouched(self, db, marker):
        fields = {"deactivated_at": None, "deletion_requested_at": None, marker: _LATER}
        user = make_user(db, active=False, pending_admin_approval=True, **fields)

        assert users_crud.approve_pending_user(user.id, db) is False

        row = _row(db, user.id)
        assert (row.active, row.pending_admin_approval) == (False, True)

    def test_a_user_not_awaiting_approval_is_left_untouched(self, db):
        user = make_user(db)

        assert users_crud.approve_pending_user(user.id, db) is False

    def test_approving_a_missing_user_is_not_found(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            users_crud.approve_pending_user(uuid.uuid4(), db)


class TestDeletion:
    def test_staging_a_deletion_deactivates_the_user_and_marks_it(self, db):
        user = make_user(db)

        users_crud.stage_deletion_request(user.id, db)

        row = _row(db, user.id)
        assert row.active is False
        assert row.deactivated_at is not None
        assert row.deletion_requested_at is not None
        assert row.deletion_attempts == 0
        assert users_crud.get_user_by_id(user.id, db).deletion_requested_at is not None

    def test_staging_the_deletion_of_a_missing_user_is_not_found(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            users_crud.stage_deletion_request(uuid.uuid4(), db)

    def test_an_attempt_is_counted_only_while_the_deletion_is_queued(self, db):
        user = make_user(db)
        assert users_crud.record_deletion_attempt(user.id, db) is None
        assert users_crud.record_deletion_attempt(uuid.uuid4(), db) is None

        users_crud.stage_deletion_request(user.id, db)

        assert users_crud.record_deletion_attempt(user.id, db) == 1
        assert users_crud.record_deletion_attempt(user.id, db) == 2
        assert users_crud.get_deletion_attempts(user.id, db) == 2

    def test_the_attempts_of_a_missing_user_are_none(self, db):
        assert users_crud.get_deletion_attempts(uuid.uuid4(), db) is None

    def test_a_deletion_is_cancelled_once_the_marker_is_cleared(self, db):
        user = make_user(db)
        users_crud.stage_deletion_request(user.id, db)
        assert users_crud.is_deletion_cancelled(user.id, db) is False

        users_crud.update_user(user.id, {"active": True}, db)

        assert users_crud.is_deletion_cancelled(user.id, db) is True

    def test_a_deletion_of_a_missing_user_is_not_cancelled(self, db):
        assert users_crud.is_deletion_cancelled(uuid.uuid4(), db) is False

    def test_a_queued_deletion_is_stalled_once_it_is_older_than_the_cutoff_and_under_the_attempt_cap(self, db):
        user = make_user(db)
        users_crud.stage_deletion_request(user.id, db)

        def stalled(**overrides) -> list[uuid.UUID]:
            args = {"requested_before": _LATER, "max_attempts": 5, "after_id": None, "limit": 100} | overrides
            return users_crud.list_stalled_deletion_ids(
                args["requested_before"], args["max_attempts"], args["after_id"], args["limit"], db
            )

        assert stalled() == [user.id]
        assert stalled(requested_before=datetime.now(UTC) - timedelta(hours=1)) == []
        assert stalled(after_id=user.id) == []
        users_crud.record_deletion_attempt(user.id, db)
        assert stalled(max_attempts=2) == [user.id]
        assert stalled(max_attempts=1) == []

    def test_stalled_deletions_page_in_id_order_up_to_the_limit(self, db):
        ids = sorted(make_user(db).id for _ in range(3))
        for user_id in ids:
            users_crud.stage_deletion_request(user_id, db)

        first_page = users_crud.list_stalled_deletion_ids(_LATER, 5, None, 2, db)
        second_page = users_crud.list_stalled_deletion_ids(_LATER, 5, first_page[-1], 2, db)

        assert (first_page, second_page) == (ids[:2], ids[2:])

    def test_deleting_a_user_removes_the_row(self, db):
        user = make_user(db)

        users_crud.delete_user(user.id, db)

        assert db.get(users_models.Users, user.id) is None

    def test_deleting_a_missing_user_is_not_found(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            users_crud.delete_user(uuid.uuid4(), db)
