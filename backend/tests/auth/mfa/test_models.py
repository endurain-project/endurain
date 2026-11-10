"""Tests for ``modules.auth.mfa.models.MFAFactor``: the table, its constraints and its TOTP-per-user index."""

import pytest
from sqlalchemy.exc import IntegrityError

from modules.auth.mfa.models import MFAFactor
from tests._helpers.db import create_sqlite_session


class TestMFAFactorModel:
    def test_tablename(self):
        assert MFAFactor.__tablename__ == "mfa_factors"

    def test_user_id_is_indexed_and_references_users(self):
        column = MFAFactor.__table__.c["user_id"]
        assert not column.nullable
        assert column.index
        assert [fk.target_fullname for fk in column.foreign_keys] == ["users.id"]

    def test_type_and_credential_are_required_and_last_used_at_is_not(self):
        columns = MFAFactor.__table__.c
        assert not columns["type"].nullable
        assert not columns["credential"].nullable
        assert columns["last_used_at"].nullable


class TestFactorRows:
    @pytest.fixture
    def db(self):
        session = create_sqlite_session()
        yield session
        session.close()

    def test_a_user_has_at_most_one_totp_factor(self, db):
        db.add(MFAFactor(user_id=1, type="totp", credential="a"))
        db.flush()

        db.add(MFAFactor(user_id=1, type="totp", credential="b"))
        with pytest.raises(IntegrityError):
            db.flush()

    def test_the_type_is_limited_to_the_known_factors(self, db):
        db.add(MFAFactor(user_id=1, type="sms", credential="a"))

        with pytest.raises(IntegrityError):
            db.flush()

    def test_a_row_records_when_it_was_enrolled(self, db):
        factor = MFAFactor(user_id=1, type="totp", credential="a")
        db.add(factor)
        db.flush()

        assert factor.created_at is not None
        assert factor.last_used_at is None
