"""Tests for staged identity-provider link persistence."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.exc import IntegrityError

import core.cryptography as core_cryptography
import core.exceptions as core_exceptions
import modules.auth.identity_provider_links.contracts as identity_links_contracts
import modules.auth.identity_provider_links.crud as identity_links_crud
import modules.auth.identity_provider_links.models as identity_links_models
from tests._helpers.db import create_sqlite_session


def _link(**overrides):
    values = {
        "id": uuid.UUID(int=1),
        "user_id": 7,
        "idp_id": 3,
        "idp_subject": "subject-1",
        "linked_at": datetime.now(UTC),
        "last_login": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_get_links_returns_internal_contracts(mock_db):
    row = _link()
    mock_db.execute.return_value.scalars.return_value.all.return_value = [row]
    result = identity_links_crud.get_user_identity_providers_by_user_id(7, mock_db)
    assert result == [identity_links_contracts.IdentityLinkRead.model_validate(row)]


def test_get_link_by_subject_returns_contract(mock_db):
    row = _link()
    mock_db.execute.return_value.scalar_one_or_none.return_value = row
    result = identity_links_crud.get_user_identity_provider_by_subject_and_idp_id(3, "subject-1", mock_db)
    assert result.idp_subject == "subject-1"


def test_check_linked_provider_and_counts(mock_db):
    mock_db.execute.return_value.scalar.return_value = True
    assert identity_links_crud.check_user_identity_providers_by_idp_id(3, mock_db) is True
    mock_db.execute.return_value.all.return_value = [(7, 2)]
    assert identity_links_crud.get_identity_link_counts_for_users([7], mock_db) == {7: 2}


def test_create_link_stages_row_and_translates_unique_race(mock_db):
    row = _link()
    with (
        patch("modules.auth.identity_provider_links.crud.identity_link_models.IdentityLink", return_value=row),
        patch(
            "modules.auth.identity_provider_links.crud.identity_link_serializers.to_read_schema",
            return_value=identity_links_contracts.IdentityLinkRead.model_validate(row),
        ),
    ):
        result = identity_links_crud.create_user_identity_provider(7, 3, "subject-1", mock_db)
    assert result.id == uuid.UUID(int=1)
    assert mock_db.flush.call_count == 2
    mock_db.commit.assert_not_called()

    mock_db.flush.side_effect = [None, IntegrityError("insert", {}, RuntimeError("duplicate"))]
    with pytest.raises(core_exceptions.ConflictError):
        identity_links_crud.create_user_identity_provider(7, 3, "subject-1", mock_db)


def test_update_last_login_stages_the_change(mock_db):
    row = _link()
    mock_db.execute.return_value.scalar_one_or_none.return_value = row
    result = identity_links_crud.update_user_identity_provider_last_login(7, 3, mock_db)
    assert result.last_login is not None
    mock_db.commit.assert_not_called()


def test_update_last_login_of_a_missing_link_returns_none(mock_db):
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    assert identity_links_crud.update_user_identity_provider_last_login(7, 3, mock_db) is None


def test_delete_link_stages_deletion(mock_db):
    mock_db.execute.return_value.rowcount = 1
    assert identity_links_crud.delete_user_identity_provider(7, 3, mock_db) is True
    mock_db.commit.assert_not_called()


SESSION = "11111111-1111-1111-1111-111111111111"


class TestSessionTokens:
    """Each session that signed in through a provider has one row, written and compared by session."""

    @pytest.fixture(autouse=True)
    def _fernet_key(self, monkeypatch):
        monkeypatch.setenv("FERNET_KEY", Fernet.generate_key().decode())

    @staticmethod
    def _db_with_token(refresh_token, session_id=SESSION, *, user_id=7, idp_id=3):
        db = create_sqlite_session()
        identity_links_crud.create_idp_session_token(session_id, user_id, idp_id, refresh_token, None, db)
        db.commit()
        return db

    def _stored(self, db, session_id=SESSION):
        return identity_links_crud.get_idp_session_token(session_id, db)

    def test_a_sign_in_is_stored_with_its_token_and_timestamps(self):
        db = create_sqlite_session()
        expires = datetime(2026, 11, 1, tzinfo=UTC)

        created = identity_links_crud.create_idp_session_token(SESSION, 7, 3, "encrypted", expires, db)
        db.commit()

        stored = self._stored(db)
        assert stored == created
        assert (stored.session_id, stored.user_id, stored.idp_id, stored.refresh_token) == (SESSION, 7, 3, "encrypted")
        # SQLite returns the stored instant without its zone.
        assert stored.access_token_expires_at.replace(tzinfo=UTC) == expires
        assert stored.refresh_token_updated_at is not None
        assert stored.created_at is not None
        db.close()

    def test_a_provider_that_issued_no_token_still_leaves_a_row(self):
        db = self._db_with_token(None)

        stored = self._stored(db)
        assert stored.refresh_token is None
        assert stored.refresh_token_updated_at is None
        db.close()

    def test_a_session_that_signed_in_through_no_provider_has_no_row(self):
        db = self._db_with_token("encrypted")

        assert self._stored(db, "another-session") is None
        db.close()

    def test_the_sessions_of_one_user_and_provider_are_listed(self):
        db = self._db_with_token("a", "s1")
        for session_id, user_id, idp_id in (("s2", 7, 3), ("s3", 7, 4), ("s4", 8, 3)):
            identity_links_crud.create_idp_session_token(session_id, user_id, idp_id, None, None, db)
        db.commit()

        assert sorted(identity_links_crud.get_idp_session_token_ids_by_user_and_idp(7, 3, db)) == ["s1", "s2"]
        db.close()

    def test_a_page_walks_the_rows_in_id_order_and_can_be_one_users(self):
        db = self._db_with_token("a", "s1")
        for session_id, user_id in (("s2", 8), ("s3", 7)):
            identity_links_crud.create_idp_session_token(session_id, user_id, 3, None, None, db)
        db.commit()

        first = identity_links_crud.get_idp_session_tokens_page(None, 2, db)
        second = identity_links_crud.get_idp_session_tokens_page(first[-1].id, 2, db)
        mine = identity_links_crud.get_idp_session_tokens_page(None, 10, db, user_id=7)

        every_row = identity_links_crud.get_idp_session_tokens_page(None, 10, db)
        assert [row.id for row in every_row] == sorted(row.id for row in every_row)
        assert first == every_row[:2]
        assert second == every_row[2:]
        assert [row.session_id for row in mine] == [row.session_id for row in every_row if row.user_id == 7]
        db.close()

    def test_a_replace_over_the_token_read_is_applied(self):
        db = self._db_with_token(core_cryptography.encrypt_token_fernet("old"))
        expires = datetime(2026, 11, 1, tzinfo=UTC)

        assert (
            identity_links_crud.replace_refresh_token_if_unchanged(
                SESSION, core_cryptography.encrypt_token_fernet("old"), "new", expires, db
            )
            is True
        )
        assert self._stored(db).refresh_token == "new"
        assert self._stored(db).access_token_expires_at.replace(tzinfo=UTC) == expires
        db.close()

    def test_the_id_token_is_stored_with_the_sign_in_and_replaced_by_a_refresh_that_returns_one(self):
        db = create_sqlite_session()
        old = core_cryptography.encrypt_token_fernet("old")
        identity_links_crud.create_idp_session_token(SESSION, 7, 3, old, None, db, encrypted_id_token="id-1")
        db.commit()
        assert self._stored(db).id_token == "id-1"

        assert identity_links_crud.replace_refresh_token_if_unchanged(
            SESSION, old, "new", datetime.now(UTC), db, encrypted_id_token="id-2"
        )
        assert self._stored(db).id_token == "id-2"
        db.close()

    def test_a_refresh_that_returns_no_id_token_keeps_the_stored_one(self):
        db = create_sqlite_session()
        old = core_cryptography.encrypt_token_fernet("old")
        identity_links_crud.create_idp_session_token(SESSION, 7, 3, old, None, db, encrypted_id_token="id-1")
        db.commit()

        assert identity_links_crud.replace_refresh_token_if_unchanged(SESSION, old, "new", datetime.now(UTC), db)
        assert self._stored(db).id_token == "id-1"
        db.close()

    def test_a_sign_in_without_an_id_token_stores_none(self):
        db = self._db_with_token("encrypted")

        assert self._stored(db).id_token is None
        db.close()

    def test_a_replace_over_a_token_another_refresh_stored_is_dropped(self):
        db = self._db_with_token("stored-by-another")

        assert (
            identity_links_crud.replace_refresh_token_if_unchanged(SESSION, "old", "new", datetime.now(UTC), db)
            is False
        )
        assert self._stored(db).refresh_token == "stored-by-another"
        db.close()

    def test_a_replace_of_another_sessions_token_changes_nothing(self):
        db = self._db_with_token("mine", "s1")
        identity_links_crud.create_idp_session_token("s2", 7, 3, "theirs", None, db)

        assert identity_links_crud.replace_refresh_token_if_unchanged("s1", "mine", "new", datetime.now(UTC), db)
        assert self._stored(db, "s2").refresh_token == "theirs"
        db.close()

    def test_a_clear_of_the_token_read_is_applied(self):
        db = self._db_with_token(core_cryptography.encrypt_token_fernet("old"))

        assert (
            identity_links_crud.clear_refresh_token_if_unchanged(
                SESSION, core_cryptography.encrypt_token_fernet("old"), db
            )
            is True
        )
        assert self._stored(db).refresh_token is None
        db.close()

    def test_a_clear_never_wipes_a_token_another_refresh_stored(self):
        db = self._db_with_token("stored-by-another")

        assert identity_links_crud.clear_refresh_token_if_unchanged(SESSION, "old", db) is False
        assert self._stored(db).refresh_token == "stored-by-another"
        db.close()

    def test_a_token_no_key_decrypts_is_cleared_by_its_own_ciphertext(self):
        db = self._db_with_token("not-a-fernet-token")

        assert identity_links_crud.clear_refresh_token_if_unchanged(SESSION, "not-a-fernet-token", db) is True
        assert self._stored(db).refresh_token is None
        db.close()

    def test_a_delete_of_the_token_read_removes_the_row(self):
        db = self._db_with_token(core_cryptography.encrypt_token_fernet("old"))

        assert (
            identity_links_crud.delete_idp_session_token_if_unchanged(
                SESSION, core_cryptography.encrypt_token_fernet("old"), db
            )
            is True
        )
        assert self._stored(db) is None
        db.close()

    def test_a_delete_of_a_row_that_holds_no_token_removes_it(self):
        db = self._db_with_token(None)

        assert identity_links_crud.delete_idp_session_token_if_unchanged(SESSION, None, db) is True
        assert self._stored(db) is None
        db.close()

    def test_a_delete_never_removes_a_token_another_refresh_stored(self):
        db = self._db_with_token("stored-by-another")

        assert identity_links_crud.delete_idp_session_token_if_unchanged(SESSION, "old", db) is False
        assert self._stored(db).refresh_token == "stored-by-another"
        db.close()

    def test_a_delete_of_a_missing_row_does_nothing(self):
        db = create_sqlite_session()

        assert identity_links_crud.delete_idp_session_token_if_unchanged(SESSION, None, db) is False
        db.close()


def test_links_page_holds_only_the_users_links_oldest_first_and_windowed():
    db = create_sqlite_session()
    for idp_id, user_id, day in ((1, 7, 3), (2, 7, 1), (3, 8, 2), (4, 7, 2)):
        db.add(
            identity_links_models.IdentityLink(
                user_id=user_id,
                idp_id=idp_id,
                idp_subject=f"subject-{idp_id}",
                linked_at=datetime(2026, 1, day, tzinfo=UTC),
            )
        )
    db.commit()

    first = identity_links_crud.get_identity_links_page(7, db, limit=2, offset=0)
    second = identity_links_crud.get_identity_links_page(7, db, limit=2, offset=2)

    assert [link.idp_id for link in first] == [2, 4]
    assert [link.idp_id for link in second] == [1]
    assert identity_links_crud.count_identity_links(7, db) == 3
    db.close()
