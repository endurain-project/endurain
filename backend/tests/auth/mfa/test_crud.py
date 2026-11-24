"""Second-factor persistence on PostgreSQL: one TOTP factor per user, its constraints and its use stamp."""

import uuid
from datetime import UTC, datetime

import psycopg.errors
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

import modules.auth.mfa.crud as mfa_crud
import modules.auth.mfa.models as mfa_models
from tests._factories.users import make_user


def _factor_rows(db, user_id) -> list[mfa_models.MFAFactor]:
    return list(db.scalars(sa.select(mfa_models.MFAFactor).where(mfa_models.MFAFactor.user_id == user_id)))


class TestTotpFactor:
    def test_a_user_without_one_has_none(self, db):
        assert mfa_crud.get_totp_factor(make_user(db).id, db) is None

    def test_a_stored_factor_belongs_to_its_user_with_its_enrolment_time_and_no_use(self, db):
        user, other = make_user(db), make_user(db)
        mfa_crud.set_totp_factor(user.id, "cipher", db)

        factor = mfa_crud.get_totp_factor(user.id, db)
        assert factor is not None
        assert (factor.user_id, factor.type, factor.credential, factor.last_used_at) == (
            user.id,
            "totp",
            "cipher",
            None,
        )
        assert isinstance(factor.id, uuid.UUID) and factor.created_at is not None
        assert mfa_crud.get_totp_factor(other.id, db) is None

    def test_setting_another_replaces_the_first_and_leaves_other_users_alone(self, db):
        user, other = make_user(db), make_user(db)
        mfa_crud.set_totp_factor(user.id, "first", db)
        mfa_crud.set_totp_factor(other.id, "theirs", db)

        mfa_crud.set_totp_factor(user.id, "second", db)

        assert [row.credential for row in _factor_rows(db, user.id)] == ["second"]
        assert mfa_crud.get_totp_factor(other.id, db).credential == "theirs"

    def test_a_user_cannot_hold_two_totp_factors(self, db):
        user = make_user(db)
        db.add(mfa_models.MFAFactor(user_id=user.id, type="totp", credential="a"))
        db.flush()

        db.add(mfa_models.MFAFactor(user_id=user.id, type="totp", credential="b"))
        with pytest.raises(IntegrityError) as exc_info:
            db.flush()

        assert isinstance(exc_info.value.orig, psycopg.errors.UniqueViolation)

    def test_the_factor_type_is_limited_to_the_known_factors(self, db):
        db.add(mfa_models.MFAFactor(user_id=make_user(db).id, type="sms", credential="a"))

        with pytest.raises(IntegrityError) as exc_info:
            db.flush()

        assert isinstance(exc_info.value.orig, psycopg.errors.CheckViolation)

    def test_deleting_a_user_deletes_their_factors(self, db):
        user = make_user(db)
        mfa_crud.set_totp_factor(user.id, "cipher", db)

        db.execute(sa.text("DELETE FROM users WHERE id = :id"), {"id": user.id})

        assert _factor_rows(db, user.id) == []


class TestUserFactors:
    def test_a_user_without_one_has_none(self, db):
        assert mfa_crud.get_user_factors(make_user(db).id, db) == []

    def test_a_user_reads_their_own_factors_only(self, db):
        user, other = make_user(db), make_user(db)
        mfa_crud.set_totp_factor(user.id, "one", db)
        mfa_crud.set_totp_factor(other.id, "two", db)

        factors = mfa_crud.get_user_factors(user.id, db)

        assert [(factor.user_id, factor.type, factor.credential) for factor in factors] == [(user.id, "totp", "one")]
        assert factors[0].last_used_at is None

    def test_deleting_removes_every_factor_of_that_user_only(self, db):
        user, other = make_user(db), make_user(db)
        mfa_crud.set_totp_factor(user.id, "one", db)
        mfa_crud.set_totp_factor(other.id, "two", db)

        mfa_crud.delete_user_factors(user.id, db)

        assert mfa_crud.get_totp_factor(user.id, db) is None
        assert mfa_crud.get_totp_factor(other.id, db) is not None


class TestMfaEnabledForUsers:
    def test_no_users_is_an_empty_answer(self, db):
        assert mfa_crud.get_mfa_enabled_for_users([], db) == {}

    def test_only_users_with_a_factor_are_enabled(self, db):
        enrolled, plain = make_user(db), make_user(db)
        mfa_crud.set_totp_factor(enrolled.id, "one", db)

        assert mfa_crud.get_mfa_enabled_for_users([enrolled.id, plain.id], db) == {enrolled.id: True}


class TestMarkFactorUsed:
    def test_it_stamps_the_time_of_use_on_that_factor_only(self, db):
        user, other = make_user(db), make_user(db)
        mfa_crud.set_totp_factor(user.id, "one", db)
        mfa_crud.set_totp_factor(other.id, "two", db)
        factor = mfa_crud.get_totp_factor(user.id, db)
        before = datetime.now(UTC)

        mfa_crud.mark_factor_used(factor.id, db)

        stamped = mfa_crud.get_totp_factor(user.id, db).last_used_at
        assert stamped is not None and before <= stamped <= datetime.now(UTC)
        assert mfa_crud.get_totp_factor(other.id, db).last_used_at is None
