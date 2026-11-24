"""Backup codes are generated hashed, verified against every unused hash and consumed once, with audit and event."""

import string
from datetime import UTC, datetime, timedelta

import jasil.runtime as jasil_runtime
import pytest
import sqlalchemy as sa
from jasil.events import Event

import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.mfa_backup_codes.audit_actions as backup_codes_audit_actions
import modules.auth.mfa_backup_codes.crud as backup_codes_crud
import modules.auth.mfa_backup_codes.events as backup_codes_events
import modules.auth.mfa_backup_codes.models as backup_codes_models
import modules.auth.mfa_backup_codes.service as backup_codes_service
from tests._factories.users import audit_rows_of, make_user

_ACTION = backup_codes_audit_actions.BACKUP_CODE_USE


@pytest.fixture
def hasher():
    return credentials_integration.get_password_hasher()


@pytest.fixture
def used_events() -> list[Event]:
    """The backup-code-used events published during the test, as the bus delivers them."""
    events: list[Event] = []
    jasil_runtime.get_active_platform().events.subscribe(backup_codes_events.BACKUP_CODE_USED, events.append)
    return events


class _CountingVerifier:
    """Verifies with the real hasher and counts the hashes it was asked about."""

    def __init__(self, hasher) -> None:
        self._hasher = hasher
        self.calls = 0

    def verify_password(self, candidate: str, password_hash: str) -> bool:
        self.calls += 1
        return self._hasher.verify_password(candidate, password_hash)


def _stored(db, user_id) -> list[backup_codes_models.MFABackupCode]:
    return list(
        db.scalars(
            sa.select(backup_codes_models.MFABackupCode).where(backup_codes_models.MFABackupCode.user_id == user_id)
        )
    )


class TestGenerate:
    def test_a_code_is_two_groups_of_four_from_the_alphabet_without_ambiguous_characters(self):
        allowed = set(string.ascii_uppercase + string.digits) - set("01OI")

        codes = [backup_codes_service.generate_backup_code() for _ in range(200)]

        assert all(len(code) == 9 and code[4] == "-" for code in codes)
        assert all(set(code.replace("-", "")) <= allowed for code in codes)
        assert len(set(codes)) == len(codes)


class TestCreate:
    def test_ten_codes_are_returned_once_and_only_their_hashes_are_stored(self, db, hasher):
        user = make_user(db)

        codes = backup_codes_service.create_backup_codes(user.id, hasher, db)

        stored = _stored(db, user.id)
        assert len(codes) == len(set(codes)) == len(stored) == 10
        assert not set(codes) & {row.code_hash for row in stored}
        assert all(any(hasher.verify_password(code, row.code_hash) for row in stored) for code in codes[:2])

    def test_new_codes_replace_the_old_ones_so_an_old_code_no_longer_works(self, db, hasher):
        user = make_user(db)
        old = backup_codes_service.create_backup_codes(user.id, hasher, db)
        new = backup_codes_service.create_backup_codes(user.id, hasher, db)

        assert len(_stored(db, user.id)) == 10
        assert backup_codes_service.verify_and_consume_backup_code(user.id, old[0], hasher, db) is False
        assert backup_codes_service.verify_and_consume_backup_code(user.id, new[0], hasher, db) is True


class TestVerifyAndConsume:
    def test_a_valid_code_is_consumed_audited_with_the_number_left_and_announced(self, db, hasher, used_events):
        user = make_user(db)
        codes = backup_codes_service.create_backup_codes(user.id, hasher, db)

        assert backup_codes_service.verify_and_consume_backup_code(user.id, codes[3], hasher, db) is True
        db.commit()

        assert sum(row.used for row in _stored(db, user.id)) == 1
        (row,) = audit_rows_of(db, _ACTION.id)
        assert (row.outcome, row.target_type, row.target_id, row.target_owner_id) == (
            "success",
            "user",
            str(user.id),
            str(user.id),
        )
        assert row.details == {"remaining_codes": 9}
        assert codes[3] not in repr(row.details)
        (event,) = used_events
        assert event.payload == {"user_id": str(user.id), "backup_codes_remaining": 9}
        assert codes[3] not in repr(event)

    def test_a_consumed_code_is_refused_the_second_time(self, db, hasher, used_events):
        user = make_user(db)
        codes = backup_codes_service.create_backup_codes(user.id, hasher, db)
        assert backup_codes_service.verify_and_consume_backup_code(user.id, codes[0], hasher, db) is True

        assert backup_codes_service.verify_and_consume_backup_code(user.id, codes[0], hasher, db) is False
        assert backup_codes_service.verify_and_consume_backup_code(user.id, codes[1], hasher, db) is True
        db.commit()

        assert [row.details["remaining_codes"] for row in audit_rows_of(db, _ACTION.id)] == [9, 8]
        assert len(used_events) == 2

    def test_a_wrong_code_and_another_users_code_consume_nothing_and_write_nothing(self, db, hasher, used_events):
        user, other = make_user(db), make_user(db)
        backup_codes_service.create_backup_codes(user.id, hasher, db)
        theirs = backup_codes_service.create_backup_codes(other.id, hasher, db)

        assert backup_codes_service.verify_and_consume_backup_code(user.id, "WRNG-CODE", hasher, db) is False
        assert backup_codes_service.verify_and_consume_backup_code(user.id, theirs[0], hasher, db) is False
        db.commit()

        assert not any(row.used for row in _stored(db, user.id))
        assert audit_rows_of(db, _ACTION.id) == []
        assert used_events == []

    def test_an_expired_code_is_refused(self, db, hasher):
        user = make_user(db)
        codes = backup_codes_service.create_backup_codes(user.id, hasher, db)
        db.execute(
            sa.update(backup_codes_models.MFABackupCode).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )

        assert backup_codes_service.verify_and_consume_backup_code(user.id, codes[0], hasher, db) is False

    def test_a_user_without_codes_is_refused(self, db, hasher):
        assert backup_codes_service.verify_and_consume_backup_code(make_user(db).id, "AAAA-BBBB", hasher, db) is False

    def test_every_unused_hash_is_verified_whatever_the_position_of_the_match(self, db, hasher):
        user = make_user(db)
        codes = backup_codes_service.create_backup_codes(user.id, hasher, db)
        unused = len(backup_codes_crud.get_user_unused_backup_codes(user.id, db))
        matching, missing = _CountingVerifier(hasher), _CountingVerifier(hasher)

        assert backup_codes_service.verify_and_consume_backup_code(user.id, codes[0], matching, db) is True
        assert backup_codes_service.verify_and_consume_backup_code(user.id, "WRNG-CODE", missing, db) is False

        assert matching.calls == unused
        assert missing.calls == unused - 1

    def test_a_code_consumed_by_a_concurrent_request_is_refused_and_writes_nothing(
        self, committed_sessions, hasher, used_events
    ):
        with committed_sessions() as db:
            user = make_user(db)
            codes = backup_codes_service.create_backup_codes(user.id, hasher, db)
            db.commit()

        class RacingVerifier:
            """Another request consumes the matching code while this one is still verifying."""

            def verify_password(self, candidate: str, password_hash: str) -> bool:
                matched = hasher.verify_password(candidate, password_hash)
                if matched:
                    with committed_sessions() as other:
                        row = other.scalars(
                            sa.select(backup_codes_models.MFABackupCode).where(
                                backup_codes_models.MFABackupCode.code_hash == password_hash
                            )
                        ).one()
                        backup_codes_crud.mark_backup_code_as_used(row.id, user.id, other)
                        other.commit()
                return matched

        with committed_sessions() as db:
            assert backup_codes_service.verify_and_consume_backup_code(user.id, codes[0], RacingVerifier(), db) is False
            db.commit()

        with committed_sessions() as db:
            assert audit_rows_of(db, _ACTION.id) == []
            assert sum(row.used for row in _stored(db, user.id)) == 1
        assert used_events == []
