"""The ``password_change_required`` flag of a local credential, against real PostgreSQL."""

from sqlalchemy import text

import modules.auth.credentials.integration_service as credentials_integration
from tests._helpers.auth import MOCK_USER_ID
from tests._helpers.db import ensure_user


def test_a_credential_row_without_the_flag_starts_false(pg_factory):
    ensure_user(pg_factory, MOCK_USER_ID)
    with pg_factory() as db:
        db.execute(
            text("INSERT INTO users_local_credentials (user_id, password_hash) VALUES (:u, 'hash')"),
            {"u": MOCK_USER_ID},
        )
        db.commit()

    with pg_factory() as db:
        assert credentials_integration.get_credential(MOCK_USER_ID, db).password_change_required is False


def test_the_flag_follows_each_write_of_the_hash(pg_factory):
    ensure_user(pg_factory, MOCK_USER_ID)
    with pg_factory() as db:
        credentials_integration.set_local_password_hash(MOCK_USER_ID, "set-by-admin", db, change_required=True)
        db.commit()
    with pg_factory() as db:
        assert credentials_integration.get_credential(MOCK_USER_ID, db).password_change_required is True
        credentials_integration.set_local_password_hash(MOCK_USER_ID, "chosen-by-owner", db, change_required=False)
        db.commit()
    with pg_factory() as db:
        credential = credentials_integration.get_credential(MOCK_USER_ID, db)
        assert (credential.password_hash, credential.password_change_required) == ("chosen-by-owner", False)
