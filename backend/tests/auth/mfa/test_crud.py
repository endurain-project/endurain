"""Tests for the factor persistence in ``modules.auth.mfa.crud``."""

import pytest

import modules.auth.mfa.crud as auth_mfa_crud
from tests._helpers.auth import MOCK_USER_ID, OTHER_USER_ID
from tests._helpers.db import create_sqlite_session


@pytest.fixture
def db():
    session = create_sqlite_session()
    yield session
    session.close()


class TestTotpFactor:
    def test_a_user_without_one_has_none(self, db):
        assert auth_mfa_crud.get_totp_factor(MOCK_USER_ID, db) is None

    def test_setting_one_stores_it(self, db):
        auth_mfa_crud.set_totp_factor(MOCK_USER_ID, "cipher", db)

        factor = auth_mfa_crud.get_totp_factor(MOCK_USER_ID, db)
        assert factor is not None
        assert (factor.user_id, factor.type, factor.credential) == (MOCK_USER_ID, "totp", "cipher")

    def test_setting_another_replaces_it(self, db):
        auth_mfa_crud.set_totp_factor(MOCK_USER_ID, "first", db)

        auth_mfa_crud.set_totp_factor(MOCK_USER_ID, "second", db)

        assert auth_mfa_crud.get_totp_factor(MOCK_USER_ID, db).credential == "second"

    def test_one_users_factor_is_not_anothers(self, db):
        auth_mfa_crud.set_totp_factor(MOCK_USER_ID, "one", db)
        auth_mfa_crud.set_totp_factor(OTHER_USER_ID, "two", db)

        assert auth_mfa_crud.get_totp_factor(MOCK_USER_ID, db).credential == "one"
        assert auth_mfa_crud.get_totp_factor(OTHER_USER_ID, db).credential == "two"


class TestDeleteUserFactors:
    def test_it_removes_every_factor_of_that_user_only(self, db):
        auth_mfa_crud.set_totp_factor(MOCK_USER_ID, "one", db)
        auth_mfa_crud.set_totp_factor(OTHER_USER_ID, "two", db)

        auth_mfa_crud.delete_user_factors(MOCK_USER_ID, db)

        assert auth_mfa_crud.get_totp_factor(MOCK_USER_ID, db) is None
        assert auth_mfa_crud.get_totp_factor(OTHER_USER_ID, db) is not None


class TestMfaEnabledForUsers:
    def test_no_users_is_an_empty_answer(self, db):
        assert auth_mfa_crud.get_mfa_enabled_for_users([], db) == {}

    def test_only_users_with_a_factor_are_enabled(self, db):
        auth_mfa_crud.set_totp_factor(MOCK_USER_ID, "one", db)

        assert auth_mfa_crud.get_mfa_enabled_for_users([MOCK_USER_ID, OTHER_USER_ID], db) == {MOCK_USER_ID: True}


class TestMarkFactorUsed:
    def test_it_stamps_the_time_of_use(self, db):
        auth_mfa_crud.set_totp_factor(MOCK_USER_ID, "one", db)
        factor = auth_mfa_crud.get_totp_factor(MOCK_USER_ID, db)

        auth_mfa_crud.mark_factor_used(factor.id, db)

        from sqlalchemy import select

        import modules.auth.mfa.models as mfa_models

        assert db.scalar(select(mfa_models.MFAFactor.last_used_at)) is not None
