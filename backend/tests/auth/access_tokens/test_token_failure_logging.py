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
