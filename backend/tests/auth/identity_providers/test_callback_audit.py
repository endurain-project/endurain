"""The SSO callback audits a new identity link."""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing
import pytest

import core.exceptions as core_exceptions
import modules.auth.identity_providers.audit_actions as idp_audit_actions
import modules.auth.identity_providers.callback_service as callback_service
import modules.auth.oauth_state.constants as oauth_state_constants
import modules.auth.sessions.audit_actions as sessions_audit_actions
from tests._helpers.auth import MOCK_USER_ID, OTHER_USER_ID

IDP_ID = uuid.uuid4()
SESSION_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")

_SESSION = SimpleNamespace(user_id=MOCK_USER_ID)


def _service():
    return callback_service.CallbackService(MagicMock(), MagicMock(), MagicMock(), "https://app.example.com")


def test_linking_a_provider_is_audited_with_the_provider_id(mock_db):
    service = _service()
    idp = MagicMock(
        id=IDP_ID, slug="idp", provider_type="oauth2", issuer_url=None, userinfo_endpoint="https://x/userinfo"
    )
    idp.name = "GitHub"
    idp.sync_user_info = False
    idp.sync_email = False
    oauth_state = MagicMock(
        user_id=MOCK_USER_ID,
        purpose=oauth_state_constants.OAuthStatePurpose.LINK,
        nonce="n",
        redirect_path="/",
        client_type="web",
        session_id=SESSION_ID,
        ends_other_sessions=False,
        security_generation=0,
    )
    oauth_client = MagicMock()
    oauth_client.fetch_token.return_value = {"access_token": "at"}
    user = MagicMock(id=MOCK_USER_ID, username="alice")
    with (
        patch.object(callback_service.sessions_integration, "lock_live_session", return_value=_SESSION),
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
        jasil_testing.capture_audit() as audit,
    ):
        service.handle_callback(idp, "code", "state", oauth_state, mock_db)

    entry = audit.assert_audited(
        idp_audit_actions.IDENTITY_LINK_LINK.id,
        outcome="success",
        target_type="user",
        target_id=str(MOCK_USER_ID),
        target_owner_id=str(MOCK_USER_ID),
    )
    assert entry.details == {"idp_id": str(IDP_ID), "reason": None}


def test_linking_an_identity_that_belongs_to_another_account_is_denied(mock_db):
    service = _service()
    idp = MagicMock(
        id=IDP_ID, slug="idp", provider_type="oauth2", issuer_url=None, userinfo_endpoint="https://x/userinfo"
    )
    idp.name = "GitHub"
    oauth_state = MagicMock(
        user_id=MOCK_USER_ID,
        purpose=oauth_state_constants.OAuthStatePurpose.LINK,
        nonce="n",
        redirect_path="/",
        client_type="web",
        session_id=SESSION_ID,
        security_generation=0,
    )
    oauth_client = MagicMock()
    oauth_client.fetch_token.return_value = {"access_token": "at"}
    with (
        patch.object(callback_service.sessions_integration, "lock_live_session", return_value=_SESSION),
        patch.object(service._oidc, "decrypt_client_id", return_value="cid"),
        patch.object(service._oidc, "decrypt_client_secret", return_value="secret"),
        patch.object(service._oidc, "resolve_token_endpoint", return_value="https://x/token"),
        patch.object(service._oidc, "create_oauth_client", return_value=oauth_client),
        patch.object(service._oidc, "get_userinfo", return_value={"sub": "s"}),
        patch.object(callback_service.users_integration, "get_user", return_value=MagicMock(id=MOCK_USER_ID)),
        patch.object(
            callback_service.identity_provider_links_integration,
            "get_user_identity_provider_by_subject_and_idp_id",
            return_value=MagicMock(user_id=OTHER_USER_ID),
        ),
        jasil_testing.capture_audit() as audit,
        pytest.raises(core_exceptions.ConflictError),
    ):
        service.handle_callback(idp, "code", "state", oauth_state, mock_db)

    entry = audit.assert_audited(
        idp_audit_actions.IDENTITY_LINK_LINK.id,
        outcome="denied",
        target_type="user",
        target_id=str(MOCK_USER_ID),
        target_owner_id=str(MOCK_USER_ID),
    )
    assert entry.details == {"idp_id": str(IDP_ID), "reason": "linked_to_another_account"}


def _complete_link(mock_db, *, ends_other_sessions, ended=2):
    """Run the callback of a link started from session ``sid``; return the audit and the session deletion."""
    service = _service()
    idp = MagicMock(
        id=IDP_ID, slug="idp", provider_type="oauth2", issuer_url=None, userinfo_endpoint="https://x/userinfo"
    )
    idp.name = "GitHub"
    idp.sync_user_info = False
    idp.sync_email = False
    oauth_state = MagicMock(
        user_id=MOCK_USER_ID,
        purpose=oauth_state_constants.OAuthStatePurpose.LINK,
        nonce="n",
        redirect_path="/",
        client_type="web",
        session_id=SESSION_ID,
        ends_other_sessions=ends_other_sessions,
        security_generation=0,
    )
    oauth_client = MagicMock()
    oauth_client.fetch_token.return_value = {"access_token": "at"}
    user = MagicMock(id=MOCK_USER_ID, username="alice")
    with (
        patch.object(callback_service.sessions_integration, "lock_live_session", return_value=_SESSION),
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
        patch.object(callback_service.sessions_integration, "delete_sessions_by_user", return_value=ended) as delete,
        jasil_testing.capture_audit() as audit,
    ):
        service.handle_callback(idp, "code", "state", oauth_state, mock_db)
    return audit, delete


def test_a_link_ends_the_other_sessions_except_the_one_that_started_it(mock_db):
    audit, delete = _complete_link(mock_db, ends_other_sessions=True)

    delete.assert_called_once_with(MOCK_USER_ID, mock_db, exclude_session_id=SESSION_ID)
    entry = audit.assert_audited(
        sessions_audit_actions.SESSION_REVOKE.id,
        target_type="user",
        target_id=str(MOCK_USER_ID),
        target_owner_id=str(MOCK_USER_ID),
    )
    assert entry.details == {"sessions_revoked": 2}
    mock_db.commit.assert_called_once()


def test_a_link_that_asked_to_keep_every_session_ends_none(mock_db):
    audit, delete = _complete_link(mock_db, ends_other_sessions=False)

    delete.assert_not_called()
    audit.assert_not_audited(sessions_audit_actions.SESSION_REVOKE.id)


def test_a_link_with_no_other_session_records_no_revocation(mock_db):
    audit, delete = _complete_link(mock_db, ends_other_sessions=True, ended=0)

    delete.assert_called_once()
    audit.assert_not_audited(sessions_audit_actions.SESSION_REVOKE.id)
