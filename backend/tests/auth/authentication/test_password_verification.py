"""Sign-in verifies the NFC form of a password, migrates legacy hashes, and commits a rehash on the MFA path."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.auth.authentication.service as authentication_service
import modules.auth.credentials.password_hasher as credentials_password_hasher

_SERVICE = "modules.auth.authentication.service"
_COMPOSED = "café-au-lait-noir"
_DECOMPOSED = "café-au-lait-noir"


@pytest.fixture
def hasher():
    return credentials_password_hasher.get_password_hasher()


def _authenticate(stored_hash: str, typed: str, hasher, mock_db):
    credential = SimpleNamespace(password_hash=stored_hash)
    with (
        patch(f"{_SERVICE}.users_integration.get_user_by_username", return_value=SimpleNamespace(id=7)),
        patch(f"{_SERVICE}.credentials_integration.get_credential", return_value=credential),
        patch(f"{_SERVICE}.credentials_integration.set_local_password_hash") as set_hash,
    ):
        user = authentication_service.authenticate_user("alice", typed, hasher, mock_db)
    return user, set_hash


def test_a_password_set_composed_signs_in_typed_decomposed(hasher, mock_db):
    stored = hasher.hash_password(_COMPOSED)

    user, set_hash = _authenticate(stored, _DECOMPOSED, hasher, mock_db)

    assert user.id == 7
    set_hash.assert_not_called()


def test_a_legacy_raw_hash_signs_in_and_is_replaced_by_the_nfc_hash(hasher, mock_db):
    legacy = hasher.hash_password(_DECOMPOSED)

    user, set_hash = _authenticate(legacy, _DECOMPOSED, hasher, mock_db)

    assert user.id == 7
    new_hash = set_hash.call_args.args[1]
    assert hasher.verify_password(_COMPOSED, new_hash)


def test_a_wrong_password_is_refused(hasher, mock_db):
    stored = hasher.hash_password(_COMPOSED)

    with pytest.raises(core_exceptions.UnauthenticatedError):
        _authenticate(stored, "wrong-password-entirely", hasher, mock_db)


def test_an_mfa_user_whose_hash_was_updated_has_it_committed_before_the_challenge(mock_db):
    hasher = MagicMock()
    hasher.verify_and_update.return_value = (True, "new-hash")
    pending = MagicMock()
    pending.add_pending_login.return_value = "challenge"
    calls = MagicMock()
    mock_db.commit.side_effect = lambda: calls.commit()
    with (
        patch(
            f"{_SERVICE}.users_integration.get_user_by_username",
            return_value=SimpleNamespace(id=7, active=True, access_type="regular"),
        ),
        patch(f"{_SERVICE}.credentials_integration.get_credential", return_value=SimpleNamespace(password_hash="old")),
        patch(
            f"{_SERVICE}.credentials_integration.set_local_password_hash",
            side_effect=lambda *a: calls.set_hash(*a),
        ),
        patch(f"{_SERVICE}.credentials_integration.allows_password_sign_in", return_value=True),
        patch(f"{_SERVICE}.server_settings_integration.get_server_settings"),
        patch(f"{_SERVICE}.mfa_integration.is_mfa_enabled_for_user", return_value=True),
    ):
        failed = MagicMock()
        failed.is_locked_out.return_value = False
        outcome = authentication_service.login_for_access_token(
            "1.2.3.4", "ua", "alice", "pw", "mobile", failed, pending, hasher, MagicMock(), mock_db
        )

    assert outcome is not None
    assert [c[0] for c in calls.mock_calls] == ["set_hash", "commit"]


def test_a_refused_mfa_login_commits_nothing(mock_db):
    hasher = MagicMock()
    hasher.verify_and_update.return_value = (False, None)
    with (
        patch(f"{_SERVICE}.users_integration.get_user_by_username", return_value=SimpleNamespace(id=7)),
        patch(f"{_SERVICE}.credentials_integration.get_credential", return_value=SimpleNamespace(password_hash="old")),
        patch(f"{_SERVICE}.lockout_integration.report_lockout_applied"),
        pytest.raises(core_exceptions.UnauthenticatedError),
    ):
        failed = MagicMock()
        failed.is_locked_out.return_value = False
        authentication_service.login_for_access_token(
            "1.2.3.4", "ua", "alice", "pw", "mobile", failed, MagicMock(), hasher, MagicMock(), mock_db
        )

    mock_db.commit.assert_not_called()
