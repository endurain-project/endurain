"""Backup-code persistence on PostgreSQL: replacement, listing, single use decided by the database."""

import uuid
from datetime import UTC, datetime, timedelta

import psycopg.errors
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

import core.exceptions as core_exceptions
import modules.auth.mfa_backup_codes.crud as backup_codes_crud
import modules.auth.mfa_backup_codes.models as backup_codes_models
from tests._factories.users import make_user


def _add(db, user_id, code_hash: str, **fields: object) -> backup_codes_models.MFABackupCode:
    row = backup_codes_models.MFABackupCode(user_id=user_id, code_hash=code_hash, **fields)
    db.add(row)
    db.flush()
    return row


def _hashes(db, user_id) -> set[str]:
    return {code.code_hash for code in backup_codes_crud.get_user_backup_codes(user_id, db)}


class TestCreate:
    def test_creating_codes_replaces_the_users_existing_ones_and_leaves_other_users_alone(self, db):
        user, other = make_user(db), make_user(db)
        backup_codes_crud.create_backup_codes(user.id, ["old-a", "old-b"], db)
        backup_codes_crud.create_backup_codes(other.id, ["theirs"], db)

        backup_codes_crud.create_backup_codes(user.id, ["hash-a", "hash-b", "hash-c"], db)

        assert _hashes(db, user.id) == {"hash-a", "hash-b", "hash-c"}
        assert _hashes(db, other.id) == {"theirs"}

    def test_a_stored_code_starts_unused_and_without_expiry(self, db):
        user = make_user(db)
        backup_codes_crud.create_backup_codes(user.id, ["hash-a"], db)

        row = db.scalars(
            sa.select(backup_codes_models.MFABackupCode).where(backup_codes_models.MFABackupCode.user_id == user.id)
        ).one()

        assert (row.used, row.used_at, row.expires_at) == (False, None, None)

    def test_no_two_stored_codes_can_share_a_hash(self, db):
        user = make_user(db)
        _add(db, user.id, "same")

        with pytest.raises(IntegrityError) as exc_info:
            backup_codes_crud.create_backup_codes(user.id, ["same", "same"], db)

        assert isinstance(exc_info.value.orig, psycopg.errors.UniqueViolation)


class TestListUnused:
    def test_used_expired_and_other_users_codes_are_left_out(self, db):
        user, other = make_user(db), make_user(db)
        now = datetime.now(UTC)
        live = _add(db, user.id, "live")
        no_expiry_yet = _add(db, user.id, "later", expires_at=now + timedelta(days=1))
        _add(db, user.id, "used", used=True, used_at=now)
        _add(db, user.id, "expired", expires_at=now - timedelta(seconds=1))
        _add(db, other.id, "theirs")

        unused = backup_codes_crud.get_user_unused_backup_codes(user.id, db)

        assert {code.id for code in unused} == {live.id, no_expiry_yet.id}
        assert len(backup_codes_crud.get_user_backup_codes(user.id, db)) == 4


class TestMarkAsUsed:
    def test_an_unused_code_is_consumed_and_stamped(self, db):
        user = make_user(db)
        row = _add(db, user.id, "hash")
        before = datetime.now(UTC)

        backup_codes_crud.mark_backup_code_as_used(row.id, user.id, db)

        db.refresh(row)
        assert row.used is True
        assert row.used_at is not None and before <= row.used_at <= datetime.now(UTC)

    def test_a_second_use_of_the_same_code_is_refused(self, db):
        user = make_user(db)
        row = _add(db, user.id, "hash")
        backup_codes_crud.mark_backup_code_as_used(row.id, user.id, db)

        with pytest.raises(core_exceptions.NotFoundError):
            backup_codes_crud.mark_backup_code_as_used(row.id, user.id, db)

    def test_another_users_code_and_a_missing_code_are_refused_and_stay_unused(self, db):
        user, other = make_user(db), make_user(db)
        row = _add(db, other.id, "hash")

        with pytest.raises(core_exceptions.NotFoundError):
            backup_codes_crud.mark_backup_code_as_used(row.id, user.id, db)
        with pytest.raises(core_exceptions.NotFoundError):
            backup_codes_crud.mark_backup_code_as_used(uuid.uuid4(), user.id, db)

        db.refresh(row)
        assert row.used is False

    def test_a_session_holding_a_stale_copy_cannot_consume_a_code_another_session_used(self, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db)
            row = _add(db, user.id, "hash")
            db.commit()
            row_id, user_id = row.id, user.id

        with committed_sessions() as stale, committed_sessions() as winner:
            assert stale.get(backup_codes_models.MFABackupCode, row_id).used is False
            backup_codes_crud.mark_backup_code_as_used(row_id, user_id, winner)
            winner.commit()

            with pytest.raises(core_exceptions.NotFoundError):
                backup_codes_crud.mark_backup_code_as_used(row_id, user_id, stale)


class TestDelete:
    def test_deleting_removes_every_code_of_the_user_and_returns_how_many(self, db):
        user, other = make_user(db), make_user(db)
        backup_codes_crud.create_backup_codes(user.id, ["a", "b", "c"], db)
        backup_codes_crud.create_backup_codes(other.id, ["theirs"], db)

        assert backup_codes_crud.delete_user_backup_codes(user.id, db) == 3

        assert _hashes(db, user.id) == set()
        assert _hashes(db, other.id) == {"theirs"}

    def test_deleting_a_user_deletes_their_codes(self, db):
        user = make_user(db)
        backup_codes_crud.create_backup_codes(user.id, ["a"], db)

        db.execute(sa.text("DELETE FROM users WHERE id = :id"), {"id": user.id})

        assert _hashes(db, user.id) == set()
