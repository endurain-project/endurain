"""The SSO callback audits the sign-ins it refuses as ``auth.session.login`` rows."""

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing
import pytest

import core.exceptions as core_exceptions
import core.hashing as core_hashing
import modules.auth.identity_providers.callback_service as callback_service
import modules.auth.identity_providers.user_provisioning_service as user_provisioning_service
import modules.auth.oauth_state.constants as oauth_state_constants
from tests._helpers.auth import MOCK_USER_ID, OTHER_USER_ID

IDP_ID = uuid.uuid4()
SESSION_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")
OTHER_IDP_ID = uuid.uuid4()

_LOGIN = "auth.session.login"
_LINK = "auth.identity_link.link"
_STEP_UP = "auth.step_up.verify"
_PURPOSE = oauth_state_constants.OAuthStatePurpose
_HOST = "https://app.example.com"
_STATE_MESSAGE = "Invalid or expired OAuth state"


@pytest.fixture(autouse=True)
def alive_session():
    """The session that started a link or step-up is alive and the user's."""
    with patch.object(
        callback_service.sessions_integration, "lock_live_session", return_value=SimpleNamespace(user_id=MOCK_USER_ID)
    ):
        yield


@pytest.fixture
def service():
    return callback_service.CallbackService(MagicMock(), MagicMock(), MagicMock(), _HOST)


def _idp(**overrides):
    values = {
        "id": IDP_ID,
        "slug": "test",
        "name": "Test",
        "enabled": True,
        "provider_type": "oauth2",
        "scopes": "profile email",
        "issuer_url": None,
        "userinfo_endpoint": "https://x/userinfo",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _state(**overrides):
    values = {
        "id": "state-id",
        "idp_id": IDP_ID,
        "client_type": "web",
        "user_id": None,
        "browser_binding_hash": core_hashing.sha256_hex("binding"),
        "purpose": _PURPOSE.LOGIN,
        "nonce": "n",
        "redirect_path": None,
        "idp_code_verifier": None,
        "session_id": SESSION_ID,
        "ends_other_sessions": False,
        "security_generation": 0,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _assert_refusal(audit, *, outcome, reason, user_id=None):
    target = {"target_type": "user", "target_id": str(user_id), "target_owner_id": str(user_id)} if user_id else {}
    entry = audit.assert_audited(_LOGIN, outcome=outcome, **target)
    assert entry.details == {"method": "identity_provider", "mfa": False, "reason": reason, "new_device": False}
    if not user_id:
        assert entry.target_id is None


def _assert_no_actor(entry):
    """The row names no user as the actor: outside a request the actor is the system, never the claimed user."""
    assert entry.actor_type != "user"
    assert entry.actor_id is None
    assert entry.credential_type is None


def _assert_link_row(audit, *, outcome, reason, user_id=MOCK_USER_ID):
    entry = audit.assert_audited(
        _LINK, outcome=outcome, target_type="user", target_id=str(user_id), target_owner_id=str(user_id)
    )
    assert entry.details == {"idp_id": str(IDP_ID), "reason": reason}
    return entry


def _assert_step_up_row(audit, *, outcome, reason, user_id=MOCK_USER_ID):
    entry = audit.assert_audited(
        _STEP_UP, outcome=outcome, target_type="user", target_id=str(user_id), target_owner_id=str(user_id)
    )
    assert entry.details == {"method": "identity_provider", "reason": reason}
    return entry


class TestStateRefusals:
    def _prepare(self, service, *, idp, oauth_state, claimed=True):
        with (
            patch.object(callback_service.idp_crud, "get_identity_provider_by_slug", return_value=idp),
            patch.object(service, "get_unused_oauth_state", return_value=oauth_state),
            patch.object(service, "claim_oauth_state", return_value=claimed),
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.InvalidInputError, match=_STATE_MESSAGE),
        ):
            service.prepare_callback("test", "state-id", "binding", MagicMock())
        return audit

    def test_an_unknown_state_is_audited(self, service):
        audit = self._prepare(service, idp=_idp(), oauth_state=None)

        _assert_refusal(audit, outcome="failure", reason="invalid_state")

    def test_a_state_of_another_provider_is_audited(self, service):
        audit = self._prepare(service, idp=_idp(id=IDP_ID), oauth_state=_state(idp_id=OTHER_IDP_ID))

        _assert_refusal(audit, outcome="failure", reason="invalid_state")

    def test_a_replayed_state_is_audited(self, service):
        audit = self._prepare(service, idp=_idp(), oauth_state=_state(), claimed=False)

        _assert_refusal(audit, outcome="failure", reason="invalid_state")

    def test_a_refused_link_state_is_a_link_refusal_not_a_sign_in(self, service):
        audit = self._prepare(
            service,
            idp=_idp(id=IDP_ID),
            oauth_state=_state(idp_id=OTHER_IDP_ID, purpose=_PURPOSE.LINK, user_id=MOCK_USER_ID),
        )

        audit.assert_not_audited(_LOGIN)
        entry = _assert_link_row(audit, outcome="failure", reason="invalid_state")
        _assert_no_actor(entry)

    def test_a_replayed_link_state_names_the_user_without_acting_as_them(self, service):
        oauth_state = _state(
            purpose=_PURPOSE.LINK, user_id=MOCK_USER_ID, browser_binding_hash=core_hashing.sha256_hex("binding")
        )
        with (
            patch.object(callback_service.idp_crud, "get_identity_provider_by_slug", return_value=_idp()),
            patch.object(service, "get_unused_oauth_state", return_value=oauth_state),
            patch.object(service, "claim_oauth_state", return_value=False),
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.InvalidInputError, match=_STATE_MESSAGE),
        ):
            service.prepare_callback("test", "state-id", "binding", MagicMock())

        _assert_no_actor(_assert_link_row(audit, outcome="failure", reason="invalid_state"))

    def test_a_refused_step_up_state_is_audited_as_a_step_up(self, service):
        audit = self._prepare(
            service,
            idp=_idp(id=IDP_ID),
            oauth_state=_state(idp_id=OTHER_IDP_ID, purpose=_PURPOSE.STEP_UP, user_id=MOCK_USER_ID),
        )

        audit.assert_not_audited(_LOGIN)
        entry = _assert_step_up_row(audit, outcome="failure", reason="invalid_state")
        _assert_no_actor(entry)

    @pytest.mark.parametrize("purpose", [_PURPOSE.LINK, _PURPOSE.STEP_UP])
    @pytest.mark.parametrize("browser_binding", [None, "another-browser"])
    def test_a_callback_from_another_browser_is_denied_without_naming_the_user_as_actor(
        self, service, purpose, browser_binding
    ):
        oauth_state = _state(
            purpose=purpose, user_id=MOCK_USER_ID, browser_binding_hash=core_hashing.sha256_hex("binding")
        )
        with (
            patch.object(callback_service.idp_crud, "get_identity_provider_by_slug", return_value=_idp()),
            patch.object(service, "get_unused_oauth_state", return_value=oauth_state),
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.InvalidInputError, match=_STATE_MESSAGE),
        ):
            service.prepare_callback("test", "state-id", browser_binding, MagicMock())

        if purpose == _PURPOSE.LINK:
            entry = _assert_link_row(audit, outcome="denied", reason="browser_mismatch")
        else:
            entry = _assert_step_up_row(audit, outcome="denied", reason="browser_mismatch")
        _assert_no_actor(entry)
        audit.assert_not_audited(_LOGIN)

    @pytest.mark.parametrize("browser_binding", [None, "another-browser"])
    def test_a_login_callback_from_another_browser_is_denied_anonymously(self, service, browser_binding):
        with (
            patch.object(callback_service.idp_crud, "get_identity_provider_by_slug", return_value=_idp()),
            patch.object(service, "get_unused_oauth_state", return_value=_state()),
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.InvalidInputError, match=_STATE_MESSAGE),
        ):
            service.prepare_callback("test", "state-id", browser_binding, MagicMock())

        entry = audit.assert_audited(_LOGIN, outcome="denied")
        assert entry.details == {
            "method": "identity_provider",
            "mfa": False,
            "reason": "browser_mismatch",
            "new_device": False,
        }
        _assert_no_actor(entry)
        audit.assert_not_audited(_LINK)
        audit.assert_not_audited(_STEP_UP)

    def test_a_missing_provider_is_not_audited(self, service):
        with (
            patch.object(callback_service.idp_crud, "get_identity_provider_by_slug", return_value=None),
            jasil_testing.capture_audit() as audit,
            pytest.raises(core_exceptions.NotFoundError),
        ):
            service.prepare_callback("test", "state-id", None, MagicMock())

        audit.assert_not_audited(_LOGIN)


class TestCompleteLoginRefusals:
    def _complete(self, service, *, userinfo=None, find_error=None, user=None, session_error=None):
        oauth_client = MagicMock()
        oauth_client.fetch_token.return_value = {"access_token": "at"}
        get_userinfo = {"side_effect": userinfo} if isinstance(userinfo, Exception) else {"return_value": {"sub": "s"}}
        with (
            patch.object(service._oidc, "decrypt_client_id", return_value="cid"),
            patch.object(service._oidc, "decrypt_client_secret", return_value="secret"),
            patch.object(service._oidc, "resolve_token_endpoint", return_value="https://x/token"),
            patch.object(service._oidc, "create_oauth_client", return_value=oauth_client),
            patch.object(service._oidc, "get_userinfo", **get_userinfo),
            patch.object(
                callback_service.user_provisioning_service,
                "find_or_create_user",
                side_effect=find_error,
                return_value=user,
            ),
            patch.object(callback_service.users_integration, "require_active_user", side_effect=session_error),
            patch.object(callback_service.sessions_integration, "create_session"),
            jasil_testing.capture_audit() as audit,
        ):
            url = service.complete_callback(
                _idp(), "code", None, "state", _state(), "10.0.0.1", "agent", MagicMock(), MagicMock()
            )
        return url, audit

    def test_an_invalid_id_token_is_audited(self, service):
        url, audit = self._complete(service, userinfo=core_exceptions.UnauthenticatedError("ID token has expired"))

        assert url == f"{_HOST}/login?error=sso_failed"
        _assert_refusal(audit, outcome="failure", reason="invalid_id_token")

    def test_a_refused_provisioning_is_audited_and_keeps_its_login_error(self, service):
        error = user_provisioning_service.SsoSignInRefusedError("no email", login_error="sso_email_missing")

        url, audit = self._complete(service, find_error=error)

        assert url == f"{_HOST}/login?error=sso_email_missing"
        _assert_refusal(audit, outcome="denied", reason="provisioning_refused")

    def test_a_provisioning_policy_refusal_is_audited(self, service):
        error = core_exceptions.PermissionDeniedError("User account creation is disabled")

        url, audit = self._complete(service, find_error=error)

        assert url == f"{_HOST}/login?error=sso_failed"
        _assert_refusal(audit, outcome="denied", reason="provisioning_refused")

    def test_an_inactive_user_is_audited_with_the_account(self, service):
        user = SimpleNamespace(id=OTHER_USER_ID, username="bob", active=False)

        url, audit = self._complete(
            service, user=user, session_error=core_exceptions.PermissionDeniedError("Inactive user")
        )

        assert url == f"{_HOST}/login?error=sso_failed"
        _assert_refusal(audit, outcome="denied", reason="inactive", user_id=OTHER_USER_ID)

    def test_a_refused_link_is_not_a_login_refusal(self, service):
        error = core_exceptions.NotFoundError("User not found")
        with (
            patch.object(service, "handle_callback", side_effect=error),
            jasil_testing.capture_audit() as audit,
        ):
            service.complete_callback(
                _idp(),
                "code",
                None,
                "state",
                _state(purpose=_PURPOSE.LINK, user_id=MOCK_USER_ID),
                "ip",
                "agent",
                MagicMock(),
                MagicMock(),
            )

        audit.assert_not_audited(_LOGIN)

    def test_a_provider_error_without_a_code_is_audited(self, service):
        with jasil_testing.capture_audit() as audit:
            url = service.complete_callback(
                _idp(), None, "access_denied", "state", _state(), "ip", "agent", MagicMock(), MagicMock()
            )

        assert url == f"{_HOST}/login?error=sso_failed"
        _assert_refusal(audit, outcome="failure", reason="provider_error")

    @pytest.mark.parametrize(
        "error",
        [
            core_exceptions.UpstreamError("down"),
            callback_service.oidc_client_service.UpstreamTimeoutError("slow"),
            core_exceptions.ProcessingError("malformed"),
        ],
        ids=lambda error: type(error).__name__,
    )
    def test_a_failed_token_exchange_is_audited(self, service, error):
        oauth_client = MagicMock()
        oauth_client.fetch_token.side_effect = error
        with (
            patch.object(service._oidc, "decrypt_client_id", return_value="cid"),
            patch.object(service._oidc, "decrypt_client_secret", return_value="secret"),
            patch.object(service._oidc, "resolve_token_endpoint", return_value="https://x/token"),
            patch.object(service._oidc, "create_oauth_client", return_value=oauth_client),
            jasil_testing.capture_audit() as audit,
        ):
            url = service.complete_callback(
                _idp(), "code", None, "state", _state(), "ip", "agent", MagicMock(), MagicMock()
            )

        assert url == f"{_HOST}/login?error=sso_failed"
        _assert_refusal(audit, outcome="failure", reason="token_exchange_failed")

    @pytest.mark.parametrize("userinfo", [{}, {"sub": ""}])
    def test_a_provider_that_names_no_subject_is_audited(self, service, userinfo):
        oauth_client = MagicMock()
        oauth_client.fetch_token.return_value = {"access_token": "at"}
        with (
            patch.object(service._oidc, "decrypt_client_id", return_value="cid"),
            patch.object(service._oidc, "decrypt_client_secret", return_value="secret"),
            patch.object(service._oidc, "resolve_token_endpoint", return_value="https://x/token"),
            patch.object(service._oidc, "create_oauth_client", return_value=oauth_client),
            patch.object(service._oidc, "get_userinfo", return_value=userinfo),
            jasil_testing.capture_audit() as audit,
        ):
            url = service.complete_callback(
                _idp(), "code", None, "state", _state(), "ip", "agent", MagicMock(), MagicMock()
            )

        assert url == f"{_HOST}/login?error=sso_failed"
        _assert_refusal(audit, outcome="failure", reason="no_subject")


class TestCompleteLinkRefusals:
    def _complete(self, service, *, code="code", fetch_error=None, userinfo=None, user="alice", existing_link=None):
        oauth_client = MagicMock()
        oauth_client.fetch_token.side_effect = fetch_error
        oauth_client.fetch_token.return_value = {"access_token": "at"}
        with (
            patch.object(service._oidc, "decrypt_client_id", return_value="cid"),
            patch.object(service._oidc, "decrypt_client_secret", return_value="secret"),
            patch.object(service._oidc, "resolve_token_endpoint", return_value="https://x/token"),
            patch.object(service._oidc, "create_oauth_client", return_value=oauth_client),
            patch.object(service._oidc, "get_userinfo", return_value={"sub": "s"} if userinfo is None else userinfo),
            patch.object(
                callback_service.users_integration,
                "get_user",
                return_value=SimpleNamespace(id=MOCK_USER_ID, username="alice", active=True) if user else None,
            ),
            patch.object(
                callback_service.identity_provider_links_integration,
                "get_user_identity_provider_by_subject_and_idp_id",
                return_value=existing_link,
            ),
            jasil_testing.capture_audit() as audit,
        ):
            url = service.complete_callback(
                _idp(),
                code,
                None if code else "access_denied",
                "state",
                _state(purpose=_PURPOSE.LINK, user_id=MOCK_USER_ID, redirect_path="/settings"),
                "ip",
                "agent",
                MagicMock(),
                MagicMock(),
            )
        return url, audit

    def test_a_provider_error_is_audited_with_the_proven_user_as_actor(self, service):
        _, audit = self._complete(service, code=None)

        entry = _assert_link_row(audit, outcome="failure", reason="provider_error")
        assert (entry.actor_type, entry.actor_id, entry.credential_type) == ("user", str(MOCK_USER_ID), "oauth")
        audit.assert_not_audited(_LOGIN)

    def test_a_failed_token_exchange_is_audited(self, service):
        _, audit = self._complete(service, fetch_error=core_exceptions.UpstreamError("down"))

        entry = _assert_link_row(audit, outcome="failure", reason="token_exchange_failed")
        assert (entry.actor_type, entry.actor_id, entry.credential_type) == ("user", str(MOCK_USER_ID), "oauth")

    def test_a_provider_that_names_no_subject_is_audited(self, service):
        _, audit = self._complete(service, userinfo={})

        entry = _assert_link_row(audit, outcome="failure", reason="no_subject")
        assert entry.actor_id == str(MOCK_USER_ID)

    def test_a_user_that_no_longer_exists_is_audited_without_an_actor(self, service):
        _, audit = self._complete(service, user=None)

        entry = _assert_link_row(audit, outcome="failure", reason="user_not_found")
        _assert_no_actor(entry)

    def test_an_identity_already_linked_to_this_account_is_denied(self, service):
        _, audit = self._complete(service, existing_link=SimpleNamespace(user_id=MOCK_USER_ID))

        entry = _assert_link_row(audit, outcome="denied", reason="already_linked_to_this_account")
        assert (entry.actor_type, entry.actor_id) == ("user", str(MOCK_USER_ID))

    def test_an_identity_linked_to_another_account_is_denied_with_the_actor(self, service):
        _, audit = self._complete(service, existing_link=SimpleNamespace(user_id=OTHER_USER_ID))

        entry = _assert_link_row(audit, outcome="denied", reason="linked_to_another_account")
        assert (entry.actor_type, entry.actor_id, entry.credential_type) == ("user", str(MOCK_USER_ID), "oauth")


class TestCompleteStepUpRefusals:
    def _complete(
        self, service, *, claims=None, link_user_id=MOCK_USER_ID, verify_error=None, issue_error=None, code="code"
    ):
        claims = {"sub": "s", "auth_time": int(datetime.now(UTC).timestamp())} if claims is None else claims
        service._oidc.get_oidc_configuration.return_value = {"jwks_uri": "https://x/jwks", "issuer": "https://x"}
        oauth_client = service._oidc.create_oauth_client.return_value.__enter__.return_value
        oauth_client.fetch_token.return_value = {"id_token": "a.b.c"}
        service._step_up_tickets.issue.side_effect = issue_error
        started = datetime.now(UTC)
        oauth_state = _state(
            purpose=_PURPOSE.STEP_UP,
            user_id=MOCK_USER_ID,
            session_id=SESSION_ID,
            action="account_delete",
            code_challenge="c" * 43,
            created_at=started,
            used=True,
            redirect_path="/settings",
            expires_at=started + timedelta(seconds=oauth_state_constants.STATE_TTL_SECONDS),
        )
        link = SimpleNamespace(user_id=link_user_id) if link_user_id is not None else None
        with (
            patch.object(
                callback_service.id_token_service, "verify_id_token", return_value=claims, side_effect=verify_error
            ),
            patch.object(
                callback_service.identity_provider_links_integration,
                "get_user_identity_provider_by_subject_and_idp_id",
                return_value=link,
            ),
            patch.object(
                callback_service.users_integration,
                "get_user",
                return_value=SimpleNamespace(id=MOCK_USER_ID, active=True),
            ),
            jasil_testing.capture_audit() as audit,
        ):
            service.complete_callback(
                _idp(),
                code,
                None if code else "access_denied",
                "state",
                oauth_state,
                "ip",
                "agent",
                MagicMock(),
                MagicMock(),
            )
        return audit

    def _assert(self, audit, *, outcome, reason):
        entry = _assert_step_up_row(audit, outcome=outcome, reason=reason)
        assert (entry.actor_type, entry.actor_id, entry.credential_type) == ("user", str(MOCK_USER_ID), "oauth")

    @pytest.mark.parametrize("link_user_id", [None, 8], ids=["not-linked", "linked-to-someone-else"])
    def test_an_account_not_linked_to_the_user_is_denied(self, service, link_user_id):
        self._assert(self._complete(service, link_user_id=link_user_id), outcome="denied", reason="not_linked")

    def test_a_sign_in_that_is_not_fresh_is_a_failure(self, service):
        audit = self._complete(service, claims={"sub": "s"})

        self._assert(audit, outcome="failure", reason="not_fresh")

    def test_a_provider_error_without_a_code_is_a_provider_failure(self, service):
        self._assert(self._complete(service, code=None), outcome="failure", reason="provider_failure")

    def test_an_id_token_without_a_subject_is_a_provider_failure(self, service):
        claims = {"auth_time": int(datetime.now(UTC).timestamp())}

        self._assert(self._complete(service, claims=claims), outcome="failure", reason="provider_failure")

    def test_an_id_token_that_does_not_verify_is_a_provider_failure(self, service):
        audit = self._complete(service, verify_error=core_exceptions.UnauthenticatedError("bad"))

        self._assert(audit, outcome="failure", reason="provider_failure")

    def test_an_unexpected_error_is_a_provider_failure(self, service):
        audit = self._complete(service, issue_error=RuntimeError("bug"))

        self._assert(audit, outcome="failure", reason="provider_failure")

    def test_a_ticket_is_not_a_refusal(self, service):
        audit = self._complete(service)

        audit.assert_not_audited(_STEP_UP)


class TestLinkSuccessActor:
    def test_the_link_and_the_ended_sessions_name_the_proven_user_as_actor(self, service):
        oauth_client = MagicMock()
        oauth_client.fetch_token.return_value = {"access_token": "at"}
        idp = _idp(sync_user_info=False, sync_email=False)
        oauth_state = _state(
            purpose=_PURPOSE.LINK, user_id=MOCK_USER_ID, session_id=SESSION_ID, ends_other_sessions=True
        )
        user = SimpleNamespace(id=MOCK_USER_ID, username="alice", active=True)
        with (
            patch.object(service._oidc, "decrypt_client_id", return_value="cid"),
            patch.object(service._oidc, "decrypt_client_secret", return_value="secret"),
            patch.object(service._oidc, "resolve_token_endpoint", return_value="https://x/token"),
            patch.object(service._oidc, "create_oauth_client", return_value=oauth_client),
            patch.object(service._oidc, "get_userinfo", return_value={"sub": "s"}),
            patch.object(callback_service.users_integration, "get_user", return_value=user),
            patch.object(
                callback_service.identity_provider_links_integration,
                "get_user_identity_provider_by_subject_and_idp_id",
                return_value=None,
            ),
            patch.object(callback_service.identity_provider_links_integration, "create_user_identity_provider"),
            patch.object(callback_service.idp_event_publishers, "publish_idp_linked"),
            patch.object(callback_service.sessions_integration, "delete_sessions_by_user", return_value=2),
            patch.object(callback_service.user_provisioning_service, "update_user_from_idp", return_value=user),
            jasil_testing.capture_audit() as audit,
        ):
            service.handle_callback(idp, "code", "state", oauth_state, MagicMock())

        for action_id in (_LINK, "auth.session.revoke"):
            entry = audit.matching(action_id)[0]
            assert (entry.actor_type, entry.actor_id, entry.credential_type) == ("user", str(MOCK_USER_ID), "oauth")
