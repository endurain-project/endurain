"""Tests for users.users.crud module."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError
from tests._helpers.db import create_sqlite_session

import core.exceptions as core_exceptions
import migrations.startup as migrations_startup
import model_registry
import modules.users.users.crud as users_crud
import modules.users.users.models as users_models

model_registry.import_all_models()


@pytest.fixture(autouse=True)
def _patch_serializer():
    """Patch the serializer to a passthrough for MagicMock compatibility."""
    with patch(
        "modules.users.users.crud.users_serializers.to_read_schema",
        side_effect=lambda x: x,
    ):
        yield


def _one(mock_db, row):
    """Make the session's single-row SELECT return ``row`` (or None)."""
    mock_db.execute.return_value.scalar_one_or_none.return_value = row


def _many(mock_db, rows):
    """Make the session's multi-row SELECT return ``rows``."""
    mock_db.execute.return_value.scalars.return_value.all.return_value = rows


def _sql(mock_db) -> str:
    """Return the last statement the session was asked to execute, as SQL text."""
    return str(mock_db.execute.call_args.args[0].compile(compile_kwargs={"literal_binds": True}))


class TestReads:
    def test_get_all_users(self, mock_db):
        rows = [MagicMock(), MagicMock()]
        _many(mock_db, rows)

        assert users_crud.get_all_users(mock_db) == rows

    def test_get_user_by_id_found(self, mock_db):
        row = MagicMock(spec=users_models.Users)
        _one(mock_db, row)

        assert users_crud.get_user_by_id(1, mock_db) == row

    def test_get_user_by_id_missing(self, mock_db):
        _one(mock_db, None)

        assert users_crud.get_user_by_id(1, mock_db) is None

    def test_get_user_by_email_is_case_insensitive(self, mock_db):
        _one(mock_db, MagicMock())

        users_crud.get_user_by_email("Test@Example.COM", mock_db)

        assert "test@example.com" in _sql(mock_db)

    def test_get_user_by_username_decodes_and_lowercases(self, mock_db):
        _one(mock_db, None)

        users_crud.get_user_by_username("Some%20Body+Else", mock_db)

        assert "some body else" in _sql(mock_db)

    def test_search_escapes_like_wildcards(self, mock_db):
        _many(mock_db, [])

        users_crud.search_active_users_by_username("50%_off", 10, 0, mock_db)

        assert "ESCAPE" in _sql(mock_db)
        assert "50\\%\\_off" in _sql(mock_db)

    def test_search_only_returns_active_users_up_to_the_limit(self, mock_db):
        _many(mock_db, [])

        users_crud.search_active_users_by_username("ann", 7, 14, mock_db)

        sql = _sql(mock_db)
        assert "active IS true" in sql
        assert "LIMIT 7" in sql
        assert "OFFSET 14" in sql

    def test_get_users_admin_filters_on_access_type(self, mock_db):
        _many(mock_db, [])

        users_crud.get_users_admin(mock_db)

        assert "access_type" in _sql(mock_db)

    def test_lock_active_admin_ids_locks_active_admins_in_id_order(self, mock_db):
        mock_db.execute.return_value.scalars.return_value.all.return_value = [1, 3]

        assert users_crud.lock_active_admin_ids(mock_db) == [1, 3]

        sql = _sql(mock_db)
        assert "FOR UPDATE" in sql
        assert "ORDER BY users.id" in sql
        assert "active IS true" in sql

    @pytest.mark.parametrize("exists", [True, False])
    def test_any_user_exists_asks_for_a_row_not_a_count(self, mock_db, exists):
        mock_db.execute.return_value.scalar_one.return_value = exists

        assert users_crud.any_user_exists(mock_db) is exists

        sql = _sql(mock_db)
        assert "EXISTS" in sql
        assert "count" not in sql.lower()

    def test_lock_first_admin_creation_takes_a_transaction_scoped_advisory_lock(self, mock_db):
        users_crud.lock_first_admin_creation(mock_db)

        statement, params = mock_db.execute.call_args.args
        assert "pg_advisory_xact_lock" in str(statement)
        assert params == {"key": 7_203_419_002}

    def test_the_first_admin_lock_key_differs_from_the_migration_lock_key(self):
        assert users_crud._FIRST_ADMIN_LOCK_KEY != migrations_startup._MIGRATION_LOCK_KEY

    def test_get_stored_photo_keys_returns_scalars(self, mock_db):
        mock_db.execute.return_value.all.return_value = [(1, "1.png"), (2, None)]

        assert users_crud.get_stored_photo_keys(mock_db) == [(1, "1.png"), (2, None)]


class TestListFilters:
    def test_count_without_filters_has_no_where(self, mock_db):
        mock_db.execute.return_value.scalar_one.return_value = 3

        assert users_crud.get_users_number(mock_db) == 3
        assert "WHERE" not in _sql(mock_db)

    def test_count_applies_every_false_filter(self, mock_db):
        mock_db.execute.return_value.scalar_one.return_value = 0

        users_crud.get_users_number(mock_db, False, False, False)

        sql = _sql(mock_db)
        assert "active" in sql and "email_verified" in sql and "pending_admin_approval" in sql

    def test_list_filters_by_username_contains(self, mock_db):
        _many(mock_db, [])

        users_crud.get_users_with_pagination(mock_db, username="Ann%")

        sql = _sql(mock_db)
        assert "lower(users.username) LIKE" in sql
        assert "ann\\%" in sql

    def test_page_is_ordered_and_offset(self, mock_db):
        _many(mock_db, [])

        users_crud.get_users_with_pagination(mock_db, page_number=3, num_records=10)

        sql = _sql(mock_db)
        assert "ORDER BY" in sql
        assert "LIMIT 10 OFFSET 20" in sql

    def test_no_pagination_without_both_arguments(self, mock_db):
        _many(mock_db, [])

        users_crud.get_users_with_pagination(mock_db, page_number=3)

        assert "LIMIT" not in _sql(mock_db)


class TestCreateUser:
    def test_stages_without_committing(self, mock_db):
        result = users_crud.create_user({"name": "A", "username": "a", "email": "a@x.com"}, mock_db)

        assert isinstance(result, users_models.Users)
        assert result.username == "a"
        mock_db.add.assert_called_once_with(result)
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_duplicate_is_a_conflict(self, mock_db):
        mock_db.flush.side_effect = IntegrityError("", "", "duplicate key")

        with pytest.raises(core_exceptions.ConflictError):
            users_crud.create_user({"name": "A", "username": "a", "email": "a@x.com"}, mock_db)


class TestUpdateUser:
    def test_applies_the_changes_and_stages(self, mock_db):
        row = MagicMock(spec=users_models.Users)
        _one(mock_db, row)

        result = users_crud.update_user(1, {"name": "New", "height": 180}, mock_db)

        assert result == row
        assert row.name == "New"
        assert row.height == 180
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_skips_read_only_properties(self, mock_db):
        row = MagicMock(spec=users_models.Users)
        _one(mock_db, row)

        with patch.object(users_models.Users, "computed", property(lambda self: 1), create=True):
            users_crud.update_user(1, {"computed": 5, "name": "New"}, mock_db)

        assert row.name == "New"

    def test_reactivating_an_account_cancels_its_queued_deletion(self, mock_db):
        row = MagicMock(spec=users_models.Users)
        row.deletion_requested_at = "2026-01-01"
        row.deletion_attempts = 3
        _one(mock_db, row)

        users_crud.update_user(1, {"active": True}, mock_db)

        assert row.deletion_requested_at is None
        assert row.deletion_attempts == 0

    def test_other_edits_leave_a_queued_deletion_alone(self, mock_db):
        row = MagicMock(spec=users_models.Users)
        row.deletion_requested_at = "2026-01-01"
        _one(mock_db, row)

        users_crud.update_user(1, {"name": "New", "active": False}, mock_db)

        assert row.deletion_requested_at == "2026-01-01"

    def test_missing_user_is_not_found(self, mock_db):
        _one(mock_db, None)

        with pytest.raises(core_exceptions.NotFoundError):
            users_crud.update_user(1, {"name": "New"}, mock_db)

    def test_duplicate_is_a_conflict(self, mock_db):
        _one(mock_db, MagicMock(spec=users_models.Users))
        mock_db.flush.side_effect = IntegrityError("", "", "duplicate key")

        with pytest.raises(core_exceptions.ConflictError):
            users_crud.update_user(1, {"username": "taken"}, mock_db)


class TestDeleteUser:
    def test_stages_the_deletion(self, mock_db):
        row = MagicMock(spec=users_models.Users)
        _one(mock_db, row)

        users_crud.delete_user(1, mock_db)

        mock_db.delete.assert_called_once_with(row)
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_missing_user_is_not_found(self, mock_db):
        _one(mock_db, None)

        with pytest.raises(core_exceptions.NotFoundError):
            users_crud.delete_user(1, mock_db)


class TestStageDeletionRequest:
    def test_deactivates_and_marks_the_user(self, mock_db):
        row = MagicMock(spec=users_models.Users)
        row.deletion_attempts = 4
        _one(mock_db, row)

        users_crud.stage_deletion_request(1, mock_db)

        assert row.active is False
        assert row.deletion_requested_at is not None
        assert row.deletion_attempts == 0
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_missing_user_is_not_found(self, mock_db):
        _one(mock_db, None)

        with pytest.raises(core_exceptions.NotFoundError):
            users_crud.stage_deletion_request(1, mock_db)


class TestRecordDeletionAttempt:
    def test_counts_the_attempt(self, mock_db):
        row = MagicMock(spec=users_models.Users)
        row.deletion_requested_at = "2026-01-01"
        row.deletion_attempts = 1
        _one(mock_db, row)

        assert users_crud.record_deletion_attempt(1, mock_db) == 2
        mock_db.flush.assert_called_once()
        mock_db.commit.assert_not_called()

    def test_a_user_that_is_gone_is_none(self, mock_db):
        _one(mock_db, None)

        assert users_crud.record_deletion_attempt(1, mock_db) is None

    def test_a_user_no_longer_queued_for_deletion_is_none(self, mock_db):
        row = MagicMock(spec=users_models.Users)
        row.deletion_requested_at = None
        _one(mock_db, row)

        assert users_crud.record_deletion_attempt(1, mock_db) is None
        mock_db.flush.assert_not_called()


class TestIsDeletionCancelled:
    def test_a_user_still_queued_for_deletion_is_not_cancelled(self, mock_db):
        row = MagicMock(spec=users_models.Users)
        row.deletion_requested_at = "2026-01-01"
        _one(mock_db, row)

        assert users_crud.is_deletion_cancelled(1, mock_db) is False

    def test_a_user_whose_marker_was_cleared_is_cancelled(self, mock_db):
        row = MagicMock(spec=users_models.Users)
        row.deletion_requested_at = None
        _one(mock_db, row)

        assert users_crud.is_deletion_cancelled(1, mock_db) is True

    def test_a_user_that_is_gone_is_not_cancelled(self, mock_db):
        _one(mock_db, None)

        assert users_crud.is_deletion_cancelled(1, mock_db) is False


class TestGetPhotoKeysByUserIds:
    def test_returns_the_photo_each_existing_user_names(self):
        db = create_sqlite_session()
        for user_id, photo in ((1, "1.png"), (2, None), (3, "3.jpg")):
            db.add(
                users_models.Users(
                    id=user_id,
                    name=f"User {user_id}",
                    username=f"user{user_id}",
                    email=f"user{user_id}@example.com",
                    preferred_language="us",
                    access_type="regular",
                    photo_path=photo,
                )
            )
        db.commit()

        # A user without a photo, and one that does not exist, name nothing.
        assert users_crud.get_photo_keys_by_user_ids([1, 2, 3, 4], db) == {1: "1.png", 3: "3.jpg"}
        db.close()


class TestListStalledDeletionIds:
    def test_returns_the_ids_the_query_found(self, mock_db):
        mock_db.scalars.return_value.all.return_value = [3, 5]

        assert users_crud.list_stalled_deletion_ids(datetime(2026, 1, 1, tzinfo=UTC), 5, 0, 100, mock_db) == [3, 5]


class TestGetUsersByIds:
    """The batched read is an SQL ``IN``, so it runs against a real session."""

    @pytest.fixture
    def db(self):
        session = create_sqlite_session()
        for user_id in (1, 2, 3):
            session.add(
                users_models.Users(
                    id=user_id,
                    name=f"User {user_id}",
                    username=f"user{user_id}",
                    email=f"user{user_id}@example.com",
                    preferred_language="us",
                    access_type="regular",
                )
            )
        session.commit()
        yield session
        session.close()

    def test_returns_only_the_requested_users(self, db):
        found = users_crud.get_users_by_ids({1, 3, 99}, db)

        assert sorted(user.id for user in found) == [1, 3]

    def test_a_repeated_id_returns_one_row(self, db):
        found = users_crud.get_users_by_ids([2, 2, 2], db)

        assert [user.id for user in found] == [2]

    def test_no_ids_return_nothing_without_querying(self, mock_db):
        assert users_crud.get_users_by_ids([], mock_db) == []
        mock_db.execute.assert_not_called()
