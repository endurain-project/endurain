"""A token the caller got wrong is a refusal to log quietly, not a server fault with a traceback."""

import logging
from datetime import timedelta

import pytest

import core.exceptions as core_exceptions
import modules.auth.access_tokens.integration_service as access_tokens_integration


@pytest.mark.parametrize("token", ["garbage", "a.b.c", ""])
def test_a_token_that_cannot_be_decoded_logs_a_warning_without_a_traceback(token_manager, caplog, token):
    with caplog.at_level(logging.DEBUG), pytest.raises(core_exceptions.UnauthenticatedError):
        token_manager.decode_token(token)

    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert all(record.exc_info is None for record in caplog.records if record.levelno >= logging.WARNING)


def _forged_tokens(token_manager, sample_user_read):
    import base64

    from joserfc import jwt
    from joserfc.jwk import OctKey

    def segment(raw):
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    _, genuine = token_manager.create_token(
        "session-1", sample_user_read, access_tokens_integration.TokenType.ACCESS, timedelta(minutes=5)
    )
    other_key = OctKey.import_key("another-secret-key-of-enough-length-0123456789")
    return {
        "wrong-signature": jwt.encode({"alg": "HS256"}, {"sub": "1"}, other_key),
        "tampered-signature": genuine[:-4] + "AAAA",
        "alg-none": f"{segment(b'{"alg":"none"}')}.{segment(b'{"sub":"1"}')}.",
        "unsupported-alg": f"{segment(b'{"alg":"RS256"}')}.{segment(b'{"sub":"1"}')}.{segment(b'x')}",
        "missing-alg": f"{segment(b'{}')}.{segment(b'{"sub":"1"}')}.{segment(b'x')}",
    }


@pytest.mark.parametrize(
    "kind", ["wrong-signature", "tampered-signature", "alg-none", "unsupported-alg", "missing-alg"]
)
def test_a_forged_token_is_a_warning_without_a_traceback(token_manager, sample_user_read, caplog, kind):
    token = _forged_tokens(token_manager, sample_user_read)[kind]

    with caplog.at_level(logging.DEBUG), pytest.raises(core_exceptions.UnauthenticatedError):
        token_manager.validate_token_expiration(token, access_tokens_integration.TokenType.ACCESS)

    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert any(record.levelno == logging.WARNING for record in caplog.records)
    assert all(record.exc_info is None for record in caplog.records if record.levelno >= logging.WARNING)


def test_a_forged_token_claim_lookup_is_not_an_error(token_manager, sample_user_read, caplog):
    token = _forged_tokens(token_manager, sample_user_read)["wrong-signature"]

    with caplog.at_level(logging.DEBUG), pytest.raises(core_exceptions.UnauthenticatedError):
        token_manager.get_token_claim(token, "sid")

    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


def test_a_missing_claim_is_a_warning_without_a_traceback(token_manager, sample_user_read, caplog):
    _, token = token_manager.create_token(
        "session-1", sample_user_read, access_tokens_integration.TokenType.ACCESS, timedelta(minutes=5)
    )

    with caplog.at_level(logging.DEBUG), pytest.raises(core_exceptions.UnauthenticatedError):
        token_manager.get_token_claim(token, "no-such-claim")

    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


class TestFailedLoginIsLogged:
    """A refused sign-in is what an operator looks for when someone is guessing, and it must not name the account."""

    @staticmethod
    def _authenticate(username, user, credential, caplog):
        from unittest.mock import MagicMock, patch

        import modules.auth.authentication.service as auth_service

        hasher = MagicMock()
        hasher.verify_and_update.return_value = (False, None)
        with (
            caplog.at_level(logging.DEBUG),
            patch.object(auth_service.users_integration, "get_user_by_username", return_value=user),
            patch.object(auth_service.credentials_integration, "get_credential", return_value=credential),
            pytest.raises(core_exceptions.UnauthenticatedError),
        ):
            auth_service.authenticate_user(username, "wrong", hasher, MagicMock())

    @pytest.mark.parametrize(
        ("user", "credential"),
        [
            (None, None),
            ("user", None),
            ("user", "credential"),
        ],
        ids=["unknown-user", "no-local-password", "wrong-password"],
    )
    def test_each_refusal_logs_one_warning_without_the_raw_username(self, caplog, user, credential):
        from types import SimpleNamespace

        user_obj = SimpleNamespace(id=1) if user else None
        credential_obj = SimpleNamespace(password_hash="hash") if credential else None

        self._authenticate("alice-the-user", user_obj, credential_obj, caplog)

        warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "alice-the-user" not in warnings[0].getMessage()
        assert "alice-the-user" not in str(getattr(warnings[0], "__dict__", {}))


def test_a_refused_access_token_is_logged_below_error(token_manager, caplog):
    with caplog.at_level(logging.DEBUG), pytest.raises(core_exceptions.UnauthenticatedError):
        token_manager.validate_access_expiration_logged("garbage")

    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert all(record.exc_info is None for record in caplog.records if record.levelno >= logging.WARNING)


class TestRefusedCredentialsAreLogged:
    """A guessed or stale credential is a security refusal: the service says so at WARNING."""

    def test_an_unknown_api_key_is_a_warning(self, caplog):
        from unittest.mock import MagicMock, patch

        import modules.auth.authentication.principal_service as principal_service

        with (
            caplog.at_level(logging.DEBUG),
            patch.object(principal_service.api_keys_integration, "hash_api_key", return_value="0" * 64),
            patch.object(principal_service.api_keys_integration, "get_api_key_by_hash", return_value=None),
            pytest.raises(core_exceptions.UnauthenticatedError),
        ):
            principal_service.resolve_from_api_key("endu_unknown", "/api/v1/x", "203.0.113.9", MagicMock())

        warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "endu_unknown" not in warnings[0].getMessage()
        assert "endu_unknown" not in str(warnings[0].__dict__)
