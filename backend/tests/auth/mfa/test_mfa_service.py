"""MFA enrolment, verification and removal on the real database: factors, backup codes, replay and generations."""

import base64
import uuid

import jasil.runtime as jasil_runtime
import pyotp
import pytest

import core.cryptography as core_cryptography
import core.exceptions as core_exceptions
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.mfa.crud as mfa_crud
import modules.auth.mfa.integration_service as mfa_integration
import modules.auth.mfa.service as mfa_service
import modules.auth.mfa.totp_replay_store as mfa_totp_replay_store
import modules.auth.mfa_backup_codes.crud as backup_codes_crud
import modules.auth.security_generation.integration_service as security_generation_integration
from tests._factories.tokens import make_mfa, totp_code
from tests._factories.users import make_user


class _ReplayGuard:
    """Claims TOTP steps in the platform state, as the routes' replay guard does."""

    def claim_totp_step(self, user_id: uuid.UUID, step: int) -> bool:
        return mfa_totp_replay_store.claim_totp_step(jasil_runtime.get_active_platform().state, user_id, step)


@pytest.fixture
def hasher():
    return credentials_integration.get_password_hasher()


def _wrong_code(secret: str) -> str:
    accepted = {totp_code(secret, steps_ahead=offset) for offset in (-1, 0, 1)}
    return next(code for code in (f"{n:06d}" for n in range(1_000_000)) if code not in accepted)


def _generation(db, user_id) -> int:
    return security_generation_integration.current_generation(user_id, db)


def _enrol(db, user, secret: str | None = None, *, code: str | None = None) -> list[str]:
    secret = secret or pyotp.random_base32()
    return mfa_service.enable_user_mfa(
        user.id,
        secret,
        code or totp_code(secret),
        credentials_integration.get_password_hasher(),
        db,
        replay_guard=_ReplayGuard(),
    )


def _verify(db, user, code: str, hasher) -> bool:
    return mfa_service.verify_user_mfa(user.id, code, hasher, db, replay_guard=_ReplayGuard())


class TestSetup:
    def test_setup_offers_a_fresh_secret_and_a_png_qr_code_and_stores_nothing(self, db):
        user = make_user(db)

        setup = mfa_service.setup_user_mfa(user.id, db)

        assert len(setup.secret) == 32 and setup.app_name == "Endurain"
        header, _, payload = setup.qr_code.partition(",")
        assert header == "data:image/png;base64"
        assert base64.b64decode(payload).startswith(b"\x89PNG")
        assert mfa_service.setup_user_mfa(user.id, db).secret != setup.secret
        assert mfa_crud.get_user_factors(user.id, db) == []

    def test_setup_is_refused_for_a_user_who_already_has_mfa_and_for_a_missing_user(self, db):
        user = make_user(db)
        make_mfa(db, user)

        with pytest.raises(core_exceptions.ConflictError):
            mfa_integration.setup_user_mfa(user.id, db)
        with pytest.raises(core_exceptions.NotFoundError):
            mfa_integration.setup_user_mfa(uuid.uuid4(), db)

    def test_the_qr_code_is_a_png_data_uri_that_depends_on_the_app_name(self):
        secret = pyotp.random_base32()

        first = mfa_service.generate_qr_code(secret, "alice")
        second = mfa_service.generate_qr_code(secret, "alice", app_name="Other")

        assert first.startswith("data:image/png;base64,") and first != second


class TestEnable:
    def test_a_valid_code_stores_the_encrypted_secret_creates_ten_backup_codes_and_bumps_the_generation(self, db):
        user = make_user(db)
        secret = pyotp.random_base32()
        generation = _generation(db, user.id)

        codes = _enrol(db, user, secret)

        (factor,) = mfa_crud.get_user_factors(user.id, db)
        assert (factor.type, factor.last_used_at) == ("totp", None)
        assert factor.credential != secret
        assert core_cryptography.decrypt_token_fernet(factor.credential) == secret
        assert len(codes) == len(set(codes)) == 10
        assert len(backup_codes_crud.get_user_unused_backup_codes(user.id, db)) == 10
        assert _generation(db, user.id) == generation + 1
        assert mfa_service.is_mfa_enabled_for_user(user.id, db) is True

    def test_a_wrong_code_enrols_nothing_and_does_not_bump(self, db):
        user = make_user(db)
        secret = pyotp.random_base32()
        generation = _generation(db, user.id)

        with pytest.raises(core_exceptions.InvalidMfaCodeError):
            _enrol(db, user, secret, code=_wrong_code(secret))

        assert mfa_crud.get_user_factors(user.id, db) == []
        assert backup_codes_crud.get_user_backup_codes(user.id, db) == []
        assert _generation(db, user.id) == generation

    def test_an_enrolment_code_cannot_be_used_twice(self, db):
        user, other = make_user(db), make_user(db)
        secret = pyotp.random_base32()
        code = totp_code(secret)
        _enrol(db, user, secret, code=code)
        mfa_service.disable_user_mfa(user.id, db)

        with pytest.raises(core_exceptions.InvalidMfaCodeError):
            _enrol(db, user, secret, code=code)
        _enrol(db, other, secret, code=totp_code(secret, steps_ahead=1))

    def test_enabling_twice_and_for_a_missing_user_is_refused_without_a_bump(self, db):
        user = make_user(db)
        make_mfa(db, user)
        generation = _generation(db, user.id)

        with pytest.raises(core_exceptions.ConflictError):
            _enrol(db, user)
        with pytest.raises(core_exceptions.NotFoundError):
            mfa_integration.enable_user_mfa(
                uuid.uuid4(),
                "x",
                "000000",
                credentials_integration.get_password_hasher(),
                db,
                replay_guard=_ReplayGuard(),
            )

        assert _generation(db, user.id) == generation


class TestDisable:
    def test_disabling_removes_the_factor_and_the_backup_codes_and_bumps_the_generation(self, db):
        user, other = make_user(db), make_user(db)
        make_mfa(db, user)
        make_mfa(db, other)
        generation = _generation(db, user.id)

        mfa_integration.disable_user_mfa(user.id, db)

        assert mfa_service.is_mfa_enabled_for_user(user.id, db) is False
        assert backup_codes_crud.get_user_backup_codes(user.id, db) == []
        assert _generation(db, user.id) == generation + 1
        assert mfa_service.is_mfa_enabled_for_user(other.id, db) is True
        assert len(backup_codes_crud.get_user_backup_codes(other.id, db)) == 10

    def test_disabling_without_mfa_and_for_a_missing_user_is_refused_without_a_bump(self, db):
        user = make_user(db)
        generation = _generation(db, user.id)

        with pytest.raises(core_exceptions.ConflictError):
            mfa_service.disable_user_mfa(user.id, db)
        with pytest.raises(core_exceptions.NotFoundError):
            mfa_service.disable_user_mfa(uuid.uuid4(), db)

        assert _generation(db, user.id) == generation


class TestVerify:
    def test_a_current_code_is_accepted_once_and_stamps_the_factor(self, db, hasher):
        user = make_user(db)
        factors = make_mfa(db, user)
        code = totp_code(factors.secret, steps_ahead=1)

        assert _verify(db, user, code, hasher) is True
        assert mfa_crud.get_totp_factor(user.id, db).last_used_at is not None
        assert _verify(db, user, code, hasher) is False

    def test_a_code_with_surrounding_spaces_is_accepted(self, db, hasher):
        user = make_user(db)
        factors = make_mfa(db, user)

        assert _verify(db, user, f"  {totp_code(factors.secret, steps_ahead=1)} ", hasher) is True

    def test_a_wrong_code_is_refused_without_a_stamp_or_a_claimed_step(self, db, hasher):
        user = make_user(db)
        factors = make_mfa(db, user)

        assert _verify(db, user, _wrong_code(factors.secret), hasher) is False
        assert mfa_crud.get_totp_factor(user.id, db).last_used_at is None
        assert _verify(db, user, totp_code(factors.secret, steps_ahead=1), hasher) is True

    @pytest.mark.parametrize("code", ["12345²", "١٢٣٤٥٦", "12345", "1234567", ""])
    def test_a_code_that_is_not_six_ascii_digits_or_a_backup_code_is_refused(self, db, hasher, code):
        user = make_user(db)
        make_mfa(db, user)

        assert _verify(db, user, code, hasher) is False

    def test_a_backup_code_is_accepted_once_in_any_case_and_a_wrong_one_is_refused(self, db, hasher):
        user = make_user(db)
        factors = make_mfa(db, user)
        backup = factors.backup_codes[0]

        assert _verify(db, user, "WRNG-CODE", hasher) is False
        assert _verify(db, user, backup.lower(), hasher) is True
        assert _verify(db, user, backup, hasher) is False
        assert len(backup_codes_crud.get_user_unused_backup_codes(user.id, db)) == 9

    def test_a_missing_user_has_no_mfa(self, db):
        assert mfa_integration.is_mfa_enabled_for_user(uuid.uuid4(), db) is False

    def test_a_user_without_mfa_is_refused_and_a_missing_user_is_not_found(self, db, hasher):
        user = make_user(db)

        assert _verify(db, user, "123456", hasher) is False
        assert mfa_integration.is_mfa_enabled_for_user(user.id, db) is False
        with pytest.raises(core_exceptions.NotFoundError):
            mfa_integration.verify_user_mfa(uuid.uuid4(), "123456", hasher, db, replay_guard=_ReplayGuard())

    def test_a_secret_that_is_not_base32_is_refused(self, db, hasher):
        user = make_user(db)
        mfa_crud.set_totp_factor(user.id, core_cryptography.encrypt_token_fernet("not base32 !"), db)

        assert _verify(db, user, "123456", hasher) is False

    def test_an_empty_stored_secret_is_refused(self, db, hasher):
        user = make_user(db)
        mfa_crud.set_totp_factor(user.id, core_cryptography.encrypt_token_fernet(""), db)

        assert _verify(db, user, "123456", hasher) is False

    def test_a_stored_secret_that_cannot_be_decrypted_surfaces_as_an_error(self, db, hasher):
        user = make_user(db)
        mfa_crud.set_totp_factor(user.id, "not-a-fernet-token", db)

        with pytest.raises(core_exceptions.UndecryptableError):
            _verify(db, user, "123456", hasher)


class TestFactorsAndMethods:
    def test_a_user_with_totp_answers_with_totp_or_a_backup_code(self, db):
        user = make_user(db)
        make_mfa(db, user)

        assert mfa_integration.get_sign_in_methods(user.id, db) == ["totp", "backup_code"]
        assert [factor.type for factor in mfa_integration.get_user_factors(user.id, db)] == ["totp"]

    def test_a_user_without_a_factor_has_no_method(self, db):
        user = make_user(db)

        assert mfa_integration.get_sign_in_methods(user.id, db) == []

    def test_enabled_users_are_found_in_one_call(self, db):
        enrolled, plain = make_user(db), make_user(db)
        make_mfa(db, enrolled)

        assert mfa_integration.get_mfa_enabled_for_users([enrolled.id, plain.id], db) == {enrolled.id: True}


class TestReencrypt:
    def test_re_encrypting_keeps_the_secret_readable(self, db, hasher):
        user = make_user(db)
        factors = make_mfa(db, user)

        mfa_service.reencrypt_stored_secrets(db)

        assert (
            core_cryptography.decrypt_token_fernet(mfa_crud.get_totp_factor(user.id, db).credential) == factors.secret
        )
