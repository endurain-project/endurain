"""A token the caller got wrong is a refusal to log quietly, not a server fault with a traceback."""

import logging
import uuid
from datetime import timedelta

import pytest

import core.exceptions as core_exceptions
import modules.auth.access_tokens.integration_service as access_tokens_integration
from modules.auth.constants import ClientType
from tests._factories.users import make_user

_USER_ID = uuid.UUID(int=1)
_SESSION_ID = uuid.UUID(int=0x5E55)
LOGIN = "/api/v1/auth/login"


@pytest.mark.parametrize("token", ["garbage", "a.b.c", ""])
def test_a_token_that_cannot_be_decoded_logs_a_warning_without_a_traceback(token_manager, caplog, token):
    with caplog.at_level(logging.DEBUG), pytest.raises(core_exceptions.UnauthenticatedError):
        token_manager.decode_token(token, access_tokens_integration.TokenType.ACCESS)

    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert all(record.exc_info is None for record in caplog.records if record.levelno >= logging.WARNING)


def _forged_tokens(token_manager, sample_user_read):
    import base64

    from joserfc import jwt
    from joserfc.jwk import OctKey

    def segment(raw):
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    _, genuine = token_manager.create_token(
        _SESSION_ID, sample_user_read, ClientType.WEB, access_tokens_integration.TokenType.ACCESS, timedelta(minutes=5)
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
        token_manager.get_token_claim(token, "sid", access_tokens_integration.TokenType.ACCESS)

    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


def test_a_missing_claim_is_a_warning_without_a_traceback(token_manager, sample_user_read, caplog):
    _, token = token_manager.create_token(
        _SESSION_ID, sample_user_read, ClientType.WEB, access_tokens_integration.TokenType.ACCESS, timedelta(minutes=5)
    )

    with caplog.at_level(logging.DEBUG), pytest.raises(core_exceptions.UnauthenticatedError):
        token_manager.get_token_claim(token, "no-such-claim", access_tokens_integration.TokenType.ACCESS)

    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]


class TestFailedLoginIsLogged:
    """A refused sign-in is what an operator looks for when someone is guessing, and it must not name the account."""

    @pytest.mark.parametrize("case", ["unknown-user", "no-local-password", "wrong-password"])
    def test_each_refusal_logs_one_warning_without_the_raw_username(self, client, committed_sessions, caplog, case):
        with committed_sessions() as db:
            user = make_user(db, with_password=case != "no-local-password", username="alice-the-user")
            db.commit()
        username = "alice-the-user" if case != "unknown-user" else "alice-the-ghost"

        with caplog.at_level(logging.DEBUG):
            response = client.post(
                LOGIN, data={"username": username, "password": "wrong"}, headers={"X-Client-Type": "web"}
            )

        assert response.status_code == 401
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING and "Sign-in refused" in r.getMessage()]
        assert len(warnings) == 1
        assert username not in warnings[0].getMessage()
        assert username not in str(getattr(warnings[0], "__dict__", {}))
        assert user.username == "alice-the-user"


def test_a_refused_access_token_is_logged_below_error(token_manager, caplog):
    with caplog.at_level(logging.DEBUG), pytest.raises(core_exceptions.UnauthenticatedError):
        token_manager.validate_access_expiration_logged("garbage")

    assert not [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert all(record.exc_info is None for record in caplog.records if record.levelno >= logging.WARNING)


class TestRefusedCredentialsAreLogged:
    """A guessed or stale credential is a security refusal: the service says so at WARNING."""

    def test_an_unknown_api_key_is_a_warning(self, client, caplog):
        with caplog.at_level(logging.DEBUG):
            response = client.get("/api/v1/health/weight", headers={"X-API-Key": "endu_unknown"})

        assert response.status_code == 401
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING and "API key refused" in r.getMessage()]
        assert len(warnings) == 1
        assert "endu_unknown" not in warnings[0].getMessage()
        assert "endu_unknown" not in str(warnings[0].__dict__)
