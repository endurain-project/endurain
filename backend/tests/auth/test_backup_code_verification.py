"""A backup code completes an MFA sign-in and a step-up, and is consumed by it."""

import pyotp
import pytest
from jasil.backends.state_memory import MemoryState

import core.cryptography as core_cryptography
import modules.auth.account_security.step_up_service as step_up_service
import modules.auth.account_security.step_up_store as step_up_store
import modules.auth.authentication.service as authentication_service
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.login_audit.audit_actions as login_audit_actions
import modules.auth.mfa.crud as mfa_crud
import modules.auth.mfa.pending_login_store as pending_login_store
import modules.auth.mfa_backup_codes.crud as backup_codes_crud
from tests._helpers.db import create_sqlite_session_factory, ensure_user

_USER_ID = 7
_PASSWORD = "correct horse battery staple"
_BACKUP_CODE = "ABCD-EFGH"


@pytest.fixture
def session_factory():
    """A user with a local password, MFA enabled and one unused backup code."""
    factory = create_sqlite_session_factory()
    ensure_user(factory, _USER_ID)
    hasher = credentials_integration.get_password_hasher()
    with factory() as db:
        credentials_integration.set_local_password_hash(
            _USER_ID, hasher.hash_password(_PASSWORD), db, change_required=False
        )
        mfa_crud.set_totp_factor(_USER_ID, core_cryptography.encrypt_token_fernet(pyotp.random_base32()), db)
        backup_codes_crud.create_backup_codes(_USER_ID, [hasher.hash_password(_BACKUP_CODE)], db)
        db.commit()
    yield factory
    factory.kw["bind"].dispose()


def _unused_codes(factory) -> int:
    with factory() as db:
        return len(backup_codes_crud.get_user_unused_backup_codes(_USER_ID, db))


class TestBackupCodeAtSignIn:
    def test_a_backup_code_completes_the_mfa_check_and_is_consumed(self, session_factory):
        with session_factory() as db:
            authentication_service.require_valid_mfa_code(
                f"user{_USER_ID}",
                _USER_ID,
                login_audit_actions.LoginMethod.PASSWORD,
                _BACKUP_CODE.lower(),
                pending_login_store.PendingMFALogin(MemoryState()),
                credentials_integration.get_password_hasher(),
                db,
            )
            db.commit()

        assert _unused_codes(session_factory) == 0


class TestBackupCodeAtStepUp:
    def test_a_backup_code_passes_step_up_with_the_password(self, session_factory):
        store = step_up_store.StepUpAttempts(MemoryState())
        with session_factory() as db:
            step_up_service.verify_step_up_credentials(_USER_ID, _PASSWORD, _BACKUP_CODE, store, db, session_id="sid")
            db.commit()

        assert _unused_codes(session_factory) == 0
