"""The step-up leg of the provider callback: a fresh, verified sign-in of the linked account becomes a ticket."""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

import httpx2
import jasil.testing as jasil_testing
import pytest
from authlib.integrations.base_client import OAuthError
from jasil.backends.state_memory import MemoryState
from pydantic import ValidationError

import core.attempt_state as core_attempt_state
import core.exceptions as core_exceptions
import modules.auth.identity_providers.callback_service as callback_service
import modules.auth.oauth_state.constants as oauth_state_constants
import modules.auth.oauth_state.schema as oauth_state_schema
from modules.auth.identity_providers.step_up_ticket_store import StepUpTicketStore
from tests._helpers.auth import MOCK_USER_ID, OTHER_USER_ID

IDP_ID = uuid.uuid4()

HOST = "https://app.example.com"
USER_ID = MOCK_USER_ID
SESSION_ID = "11111111-2222-3333-4444-555555555555"
NOW = datetime.now(UTC)


@pytest.fixture
def state():
    return MemoryState()


@pytest.fixture
def oidc():
    client = MagicMock()
    client.decrypt_client_id.return_value = "client-id"
    client.decrypt_client_secret.return_value = "secret"
    client.resolve_token_endpoint.return_value = "https://idp.example.com/token"
    client.get_oidc_configuration.return_value = {
        "issuer": "https://idp.example.com",
        "jwks_uri": "https://idp.example.com/jwks",
    }
    oauth_client = client.create_oauth_client.return_value.__enter__.return_value
    oauth_client.fetch_token.return_value = {"id_token": "header.payload.signature", "access_token": "at"}
    return client


@pytest.fixture(autouse=True)
def active_user_and_session():
    """The user is active and the session that started the step-up is alive and theirs."""
    with (
        patch.object(
            callback_service.users_integration, "get_user", return_value=SimpleNamespace(id=USER_ID, active=True)
        ),
        patch.object(
            callback_service.sessions_integration,
            "lock_live_session",
            return_value=SimpleNamespace(user_id=USER_ID),
        ),
    ):
        yield


@pytest.fixture
def service(oidc, state):
    return callback_service.CallbackService(oidc, MagicMock(), StepUpTicketStore(state), HOST)


def _idp():
    return SimpleNamespace(id=IDP_ID, slug="idp", name="Pocket ID")


def _oauth_state(started_at=NOW, **overrides):
    values = {
        "id": "state-id",
        "purpose": oauth_state_constants.OAuthStatePurpose.STEP_UP,
        "user_id": USER_ID,
        "session_id": SESSION_ID,
        "action": "account_delete",
        "code_challenge": "c" * 43,
        "nonce": "n" * 32,
        "idp_code_verifier": "i" * 86,
        "redirect_path": "/settings/security",
        "client_type": "web",
        "created_at": started_at,
        "expires_at": started_at + timedelta(seconds=oauth_state_constants.STATE_TTL_SECONDS),
        "used": True,
        "security_generation": 0,
    }
    values.update(overrides)
    return oauth_state_schema.StepUpOAuthStateRead(**values)


def _fragment(url: str) -> dict[str, list[str]]:
    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}" == HOST
    assert parts.path == "/settings/security"
    assert parts.query == ""
    return parse_qs(parts.fragment)


def _complete(service, *, claims=None, link_user_id=USER_ID, oauth_state=None):
    claims = {"sub": "subject-1", "auth_time": int(NOW.timestamp())} if claims is None else claims
    link = SimpleNamespace(user_id=link_user_id) if link_user_id is not None else None
    with (
        patch.object(callback_service.id_token_service, "verify_id_token", return_value=claims) as verify,
        patch.object(
            callback_service.identity_provider_links_integration,
            "get_user_identity_provider_by_subject_and_idp_id",
            return_value=link,
        ) as find_link,
    ):
        url = service.complete_step_up_callback(_idp(), "code", oauth_state or _oauth_state(), MagicMock())
    return url, verify, find_link


class TestFreshSignIn:
    def test_a_fresh_sign_in_of_the_linked_account_hands_back_a_ticket(self, service, state):
        url, _, _ = _complete(service)

        ticket = _fragment(url)["step_up_ticket"][0]
        issued = StepUpTicketStore(state).read(ticket)
        assert issued.user_id == USER_ID
        assert issued.session_id == SESSION_ID
        assert issued.idp_id == IDP_ID
        assert issued.action == "account_delete"
        assert issued.code_challenge == "c" * 43
        assert issued.security_generation == 0

    def test_the_code_is_redeemed_with_pkce_and_the_id_token_checked_against_the_nonce(self, service, oidc):
        _, verify, _ = _complete(service)

        oauth_client = oidc.create_oauth_client.return_value.__enter__.return_value
        assert oauth_client.fetch_token.call_args.kwargs["code_verifier"] == "i" * 86
        assert verify.call_args.args[1:] == (
            "header.payload.signature",
            "https://idp.example.com/jwks",
            "https://idp.example.com",
            "client-id",
        )
        assert verify.call_args.kwargs["expected_nonce"] == "n" * 32

    def test_nothing_but_the_ticket_changes(self, service, oidc):
        _complete(service)

        oidc.get_userinfo.assert_not_called()
        service._tokens.store_session_tokens.assert_not_called()

    def test_the_link_is_found_by_the_verified_subject(self, service):
        _, _, find_link = _complete(service)

        assert find_link.call_args.args[:2] == (IDP_ID, "subject-1")


class TestStaleFlow:
    """A step-up whose account or session changed after it started issues no ticket."""

    def _assert_refused(self, url, audit, reason):
        assert _fragment(url) == {"step_up_error": ["failed"]}
        entry = audit.assert_audited(
            "auth.step_up.verify",
            outcome="denied",
            target_type="user",
            target_id=str(USER_ID),
            target_owner_id=str(USER_ID),
        )
        assert entry.details == {"method": "identity_provider", "reason": reason}

    def test_a_security_change_after_the_step_up_started_issues_no_ticket(self, service, security_generations):
        started = _oauth_state(security_generation=security_generations.current_generation(USER_ID, MagicMock()))
        security_generations.stage_bump(USER_ID, MagicMock())

        with jasil_testing.capture_audit() as audit:
            url, _, _ = _complete(service, oauth_state=started)

        self._assert_refused(url, audit, "security_changed")

    def test_a_state_without_a_stamp_issues_no_ticket(self, service):
        with jasil_testing.capture_audit() as audit:
            url, _, _ = _complete(service, oauth_state=_oauth_state(security_generation=None))

        self._assert_refused(url, audit, "security_changed")

    @pytest.mark.parametrize("user", [SimpleNamespace(id=USER_ID, active=False), None], ids=["inactive", "deleted"])
    def test_an_inactive_or_missing_user_issues_no_ticket(self, service, user):
        with (
            patch.object(callback_service.users_integration, "get_user", return_value=user),
            jasil_testing.capture_audit() as audit,
        ):
            url, _, _ = _complete(service)

        self._assert_refused(url, audit, "user_inactive")

    @pytest.mark.parametrize("session", [None, SimpleNamespace(user_id=OTHER_USER_ID)], ids=["ended", "another-users"])
    def test_a_session_that_ended_issues_no_ticket(self, service, session):
        with (
            patch.object(callback_service.sessions_integration, "lock_live_session", return_value=session),
            jasil_testing.capture_audit() as audit,
        ):
            url, _, _ = _complete(service)

        self._assert_refused(url, audit, "session_ended")

    def test_the_ticket_is_stamped_with_the_generation_of_the_state(self, service, state, security_generations):
        security_generations.generations[USER_ID] = 9

        url, _, _ = _complete(service, oauth_state=_oauth_state(security_generation=9))

        assert StepUpTicketStore(state).read(_fragment(url)["step_up_ticket"][0]).security_generation == 9


class TestRefusals:
    @pytest.mark.parametrize(
        "claims",
        [
            {"sub": "subject-1"},
            {"sub": "subject-1", "auth_time": True},
            {"sub": "subject-1", "auth_time": "now"},
            {"sub": "subject-1", "auth_time": int((NOW - timedelta(seconds=61)).timestamp()) - 1},
            {"sub": "subject-1", "auth_time": int((NOW + timedelta(days=1)).timestamp())},
        ],
        ids=["missing", "boolean", "string", "before-the-step-up", "in-the-future"],
    )
    def test_a_sign_in_that_is_not_fresh_is_refused_as_such(self, service, state, claims):
        url, _, _ = _complete(service, claims=claims)

        assert _fragment(url) == {"step_up_error": ["not_fresh"]}

    def test_a_sign_in_within_the_tolerance_before_the_start_passes(self, service):
        claims = {"sub": "subject-1", "auth_time": int((NOW - timedelta(seconds=59)).timestamp())}

        url, _, _ = _complete(service, claims=claims)

        assert "step_up_ticket" in _fragment(url)

    def test_a_naive_expiry_from_the_database_is_read_as_utc(self, service):
        naive = _oauth_state()
        naive.expires_at = naive.expires_at.astimezone(UTC).replace(tzinfo=None)

        url, _, _ = _complete(service, oauth_state=naive)

        assert "step_up_ticket" in _fragment(url)

    @pytest.mark.parametrize("link_user_id", [None, OTHER_USER_ID], ids=["not-linked", "linked-to-someone-else"])
    def test_a_provider_account_not_linked_to_the_user_is_refused(self, service, state, link_user_id):
        url, _, _ = _complete(service, link_user_id=link_user_id)

        assert _fragment(url) == {"step_up_error": ["failed"]}

    def test_an_integer_subject_finds_the_link_by_its_decimal_string(self, service):
        _, _, find_link = _complete(service, claims={"sub": 12345, "auth_time": int(NOW.timestamp())})

        assert find_link.call_args.args[:2] == (IDP_ID, "12345")

    @pytest.mark.parametrize("sub", [None, "", "   ", True], ids=["missing", "empty", "blank", "bool"])
    def test_an_id_token_without_a_subject_is_refused(self, service, sub):
        claims = {"auth_time": int(NOW.timestamp())} | ({"sub": sub} if sub is not None else {})

        url, _, _ = _complete(service, claims=claims)

        assert _fragment(url) == {"step_up_error": ["failed"]}

    @pytest.mark.parametrize(
        "config",
        [None, {"issuer": "https://idp.example.com"}, {"jwks_uri": "https://idp.example.com/jwks"}],
        ids=["discovery-failed", "no-jwks", "no-issuer"],
    )
    def test_a_provider_without_signing_keys_is_refused_without_redeeming_the_code(self, service, oidc, config):
        oidc.get_oidc_configuration.return_value = config

        url, verify, _ = _complete(service)

        assert _fragment(url) == {"step_up_error": ["failed"]}
        oidc.create_oauth_client.assert_not_called()
        verify.assert_not_called()

    @pytest.mark.parametrize("iss", [None, "https://evil.example.com"], ids=["missing", "mismatching"])
    def test_an_iss_parameter_the_provider_promises_but_gets_wrong_is_refused_without_redeeming_the_code(
        self, service, oidc, iss
    ):
        oidc.get_oidc_configuration.return_value |= {"authorization_response_iss_parameter_supported": True}

        with patch.object(callback_service.id_token_service, "verify_id_token") as verify:
            url = service.complete_step_up_callback(_idp(), "code", _oauth_state(), MagicMock(), iss=iss)

        assert _fragment(url) == {"step_up_error": ["failed"]}
        oidc.create_oauth_client.assert_not_called()
        verify.assert_not_called()

    def test_the_access_token_is_given_to_the_id_token_verification(self, service):
        _, verify, _ = _complete(service)

        assert verify.call_args.kwargs["access_token"] == "at"

    def test_a_token_response_without_an_id_token_is_refused(self, service, oidc):
        oauth_client = oidc.create_oauth_client.return_value.__enter__.return_value
        oauth_client.fetch_token.return_value = {"access_token": "at"}

        url, verify, _ = _complete(service)

        assert _fragment(url) == {"step_up_error": ["failed"]}
        verify.assert_not_called()

    def test_an_id_token_that_does_not_verify_is_refused(self, service, caplog):
        with (
            caplog.at_level(logging.DEBUG, logger=callback_service.logger.name),
            patch.object(
                callback_service.id_token_service,
                "verify_id_token",
                side_effect=core_exceptions.UnauthenticatedError("bad signature"),
            ),
        ):
            url = service.complete_step_up_callback(_idp(), "code", _oauth_state(), MagicMock())

        assert _fragment(url) == {"step_up_error": ["failed"]}
        assert [record.levelno for record in caplog.records] == [logging.WARNING]

    def test_an_unreachable_ticket_store_is_refused(self, oidc, caplog):
        failing = MagicMock()
        failing.issue.side_effect = core_attempt_state.StateUnavailableError()
        service = callback_service.CallbackService(oidc, MagicMock(), failing, HOST)

        with caplog.at_level(logging.DEBUG, logger=callback_service.logger.name):
            url, _, _ = _complete(service)

        assert _fragment(url) == {"step_up_error": ["failed"]}
        assert [record.levelno for record in caplog.records] == [logging.WARNING]

    def test_an_unexpected_error_is_logged_as_an_error_and_still_refused(self, oidc, caplog):
        failing = MagicMock()
        failing.issue.side_effect = RuntimeError("bug")
        service = callback_service.CallbackService(oidc, MagicMock(), failing, HOST)

        with caplog.at_level(logging.DEBUG, logger=callback_service.logger.name):
            url, _, _ = _complete(service)

        assert _fragment(url) == {"step_up_error": ["failed"]}
        assert [record.levelno for record in caplog.records] == [logging.ERROR]
        assert caplog.records[0].exc_info is not None

    @pytest.mark.parametrize(
        "error",
        [
            httpx2.ReadTimeout("slow"),
            httpx2.HTTPStatusError("bad", request=MagicMock(), response=MagicMock(status_code=400)),
            httpx2.ConnectError("refused"),
            OAuthError("invalid_grant", "code expired"),
            ValueError("expires_in is not a number"),
            TypeError("expires_in is a list"),
            OverflowError("expires_in out of range"),
            httpx2.InvalidURL("non-printable character"),
        ],
        ids=lambda error: type(error).__name__,
    )
    def test_a_failed_code_exchange_is_a_refusal_without_a_ticket(self, service, oidc, caplog, error):
        oauth_client = oidc.create_oauth_client.return_value.__enter__.return_value
        oauth_client.fetch_token.side_effect = error

        with caplog.at_level(logging.WARNING, logger=callback_service.logger.name):
            url, verify, _ = _complete(service)

        assert _fragment(url) == {"step_up_error": ["failed"]}
        verify.assert_not_called()
        assert logging.ERROR not in [record.levelno for record in caplog.records]


class TestDispatch:
    def test_a_step_up_callback_never_reaches_the_login_or_link_handling(self, service):
        with (
            patch.object(service, "complete_step_up_callback", return_value="step-up-url") as step_up,
            patch.object(service, "handle_callback") as handle,
        ):
            url = service.complete_callback(
                _idp(), "code", None, "state-id", _oauth_state(), "1.2.3.4", "ua", MagicMock(), MagicMock()
            )

        assert url == "step-up-url"
        step_up.assert_called_once()
        handle.assert_not_called()

    def test_a_step_up_state_stored_without_its_session_fails_where_it_is_read(self, service):
        state = oauth_state_schema.OAuthStateRead.model_validate(_oauth_state().model_dump() | {"session_id": None})

        with patch.object(service, "complete_step_up_callback") as step_up, pytest.raises(ValidationError):
            service.complete_callback(
                _idp(), "code", None, "state-id", state, "1.2.3.4", "ua", MagicMock(), MagicMock()
            )

        step_up.assert_not_called()

    @pytest.mark.parametrize(
        ("purpose", "expected"),
        [
            (oauth_state_constants.OAuthStatePurpose.STEP_UP, f"{HOST}/settings/security#step_up_error=failed"),
            (oauth_state_constants.OAuthStatePurpose.LINK, f"{HOST}/settings/security?idp_link=error"),
            (oauth_state_constants.OAuthStatePurpose.LOGIN, f"{HOST}/login?error=sso_failed"),
        ],
    )
    def test_a_provider_error_returns_to_where_the_flow_started(self, service, purpose, expected):
        with patch.object(service, "handle_callback") as handle:
            url = service.complete_callback(
                _idp(),
                None,
                "login_required",
                "state-id",
                _oauth_state(purpose=purpose),
                "1.2.3.4",
                "ua",
                MagicMock(),
                MagicMock(),
            )

        assert url == expected
        handle.assert_not_called()
