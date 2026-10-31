"""The step-up leg of the provider callback: a fresh, verified sign-in of the linked account becomes a ticket."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlsplit

import pytest
from jasil.backends.state_memory import MemoryState

import modules.auth.identity_providers.callback_service as callback_service
import modules.auth.oauth_state.constants as oauth_state_constants
from modules.auth.identity_providers.step_up_ticket_store import StepUpTicketStore

HOST = "https://app.example.com"
USER_ID = 7
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
        "jwks_uri": "https://idp.example.com/jwks",
        "issuer": "https://idp.example.com",
    }
    oauth_client = client.create_oauth_client.return_value.__enter__.return_value
    oauth_client.fetch_token.return_value = {"id_token": "header.payload.signature", "access_token": "at"}
    return client


@pytest.fixture
def service(oidc, state):
    return callback_service.CallbackService(oidc, MagicMock(), StepUpTicketStore(state), HOST)


def _idp():
    return SimpleNamespace(id=3, slug="idp", name="Pocket ID")


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
        "expires_at": started_at + timedelta(seconds=oauth_state_constants.STATE_TTL_SECONDS),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


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
        assert issued.idp_id == 3
        assert issued.action == "account_delete"
        assert issued.code_challenge == "c" * 43

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
        service._tokens.store_idp_tokens.assert_not_called()

    def test_the_link_is_found_by_the_verified_subject(self, service):
        _, _, find_link = _complete(service)

        assert find_link.call_args.args[:2] == (3, "subject-1")


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

    @pytest.mark.parametrize("link_user_id", [None, USER_ID + 1], ids=["not-linked", "linked-to-someone-else"])
    def test_a_provider_account_not_linked_to_the_user_is_refused(self, service, state, link_user_id):
        url, _, _ = _complete(service, link_user_id=link_user_id)

        assert _fragment(url) == {"step_up_error": ["failed"]}

    @pytest.mark.parametrize("sub", [None, ""], ids=["missing", "empty"])
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

    def test_a_token_response_without_an_id_token_is_refused(self, service, oidc):
        oauth_client = oidc.create_oauth_client.return_value.__enter__.return_value
        oauth_client.fetch_token.return_value = {"access_token": "at"}

        url, verify, _ = _complete(service)

        assert _fragment(url) == {"step_up_error": ["failed"]}
        verify.assert_not_called()

    def test_an_id_token_that_does_not_verify_is_refused(self, service):
        with patch.object(
            callback_service.id_token_service, "verify_id_token", side_effect=RuntimeError("bad signature")
        ):
            url = service.complete_step_up_callback(_idp(), "code", _oauth_state(), MagicMock())

        assert _fragment(url) == {"step_up_error": ["failed"]}

    def test_an_unreachable_ticket_store_is_refused(self, oidc):
        failing = MagicMock()
        failing.issue.side_effect = RuntimeError("state down")
        service = callback_service.CallbackService(oidc, MagicMock(), failing, HOST)

        url, _, _ = _complete(service)

        assert _fragment(url) == {"step_up_error": ["failed"]}


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
