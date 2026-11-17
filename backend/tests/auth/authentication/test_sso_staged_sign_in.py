"""An SSO sign-in changes nothing on an existing account until the sign-in completes, after its second factor.

The callback runs for real over SQLite: it matches the account by its verified email and creates the session, and
the exchange and ``/auth/mfa/verify`` routes finish it. The link, the profile sync and their audit rows and events
appear only when the sign-in completes; an MFA step that is abandoned, fails, or is outdated leaves the account as it
was.
"""

import uuid
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing
import pytest
from sqlalchemy import select, update

import core.dependencies as core_dependencies
import modules.auth.identity_provider_links.models as links_models
import modules.auth.identity_providers.callback_service as callback_service
import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.event_publishers as idp_event_publishers
import modules.auth.identity_providers.schema as idp_schema
import modules.auth.identity_providers.user_provisioning_service as user_provisioning_service
import modules.auth.oauth_state.constants as oauth_state_constants
import modules.auth.oauth_state.integration_service as oauth_state_integration
import modules.auth.sessions.models as sessions_models
import modules.users.users.models as users_models
from modules.auth.identity_providers.staged_sign_in_store import StagedSignInStore
from tests.auth.authentication.conftest import BACKUP_CODE, SSO_CHALLENGE, SSO_VERIFIER, USER_ID, WEB

_SUBJECT = "subject-at-the-provider"
_SYNCED_NAME = "Name From The Provider"
_LINK = "auth.identity_link.link"
_EMAIL_CHANGE = "users.email.change"
_LOGIN = "auth.session.login"
_SESSION_ENDED = "urn:endurain:error:session-ended"
_NOTICE = "modules.auth.sign_up_tokens.event_publishers.platform_publisher.publish_on_commit"

pytestmark = pytest.mark.usefixtures("aware_session_expiry")


def _store() -> StagedSignInStore:
    return StagedSignInStore(core_dependencies.get_platform_state())


def _provider(stack) -> uuid.UUID:
    """Store a provider that links by email and syncs the name and the email, and verify the account's email."""
    with stack.factory() as db:
        idp = idp_crud.create_identity_provider(
            idp_schema.IdentityProviderCreate(
                name="Keycloak",
                slug="keycloak",
                issuer_url="https://idp.example.com",
                client_id="endurain",
                client_secret="secret",
                enabled=True,
                link_by_email=True,
                sync_user_info=True,
                sync_email=True,
            ),
            db,
        )
        db.execute(update(users_models.Users).where(users_models.Users.id == USER_ID).values(email_verified=True))
        db.commit()
        return idp.id


def _account(stack) -> tuple[str, str]:
    with stack.factory() as db:
        user = db.get(users_models.Users, USER_ID)
        return user.name, user.email


def _links(stack) -> list[tuple[uuid.UUID, str]]:
    with stack.factory() as db:
        rows = db.execute(select(links_models.IdentityLink.user_id, links_models.IdentityLink.idp_subject)).all()
        return [(row.user_id, row.idp_subject) for row in rows]


def _callback(stack, idp_id: uuid.UUID, *, email: str | None = None, subject: str = _SUBJECT) -> uuid.UUID:
    """Run the login callback's account match and session creation for the provider's verified claims."""
    with stack.factory() as db:
        idp = idp_crud.get_identity_provider(idp_id, db)
        account_email = db.get(users_models.Users, USER_ID).email
        userinfo = {"sub": subject, "email": email or account_email, "email_verified": True, "name": _SYNCED_NAME}
        user, staged = user_provisioning_service.find_or_create_user(idp, subject, userinfo, db)
        db.commit()
        state_id, nonce = oauth_state_integration.create_state_id_and_nonce()
        oauth_state_integration.create_oauth_state(
            state_id,
            nonce,
            "web",
            "127.0.0.1",
            db,
            idp_id=idp_id,
            code_challenge=SSO_CHALLENGE,
            code_challenge_method="S256",
            purpose=oauth_state_constants.OAuthStatePurpose.LOGIN,
        )
        state = oauth_state_integration.get_oauth_state_by_id_and_not_used(state_id, db)
        service = callback_service.CallbackService(MagicMock(), MagicMock(), MagicMock(), _store(), "https://app")
        return service.create_callback_session(
            user, "127.0.0.1", "agent", state, idp_id, {}, db, idp_sid=None, staged=staged
        )


def _exchange(stack, session_id):
    return stack.client.post(f"/auth/sessions/{session_id}/tokens", json={"code_verifier": SSO_VERIFIER}, headers=WEB)


def _verify(stack, challenge, code=BACKUP_CODE):
    return stack.client.post("/auth/mfa/verify", json={"mfa_challenge": challenge, "mfa_code": code}, headers=WEB)


@contextmanager
def _recorded():
    """Capture the audit rows and the ``auth.idp_linked`` events of the requests in the block."""
    with (
        jasil_testing.capture_audit() as audit,
        patch.object(idp_event_publishers, "publish_idp_linked") as linked,
        patch(_NOTICE),
    ):
        yield audit, linked


def _assert_untouched(stack, before, audit, linked) -> None:
    assert _account(stack) == before
    assert _links(stack) == []
    audit.assert_not_audited(_LINK)
    audit.assert_not_audited(_EMAIL_CHANGE)
    linked.assert_not_called()


def _assert_unclaimed(stack, session_id) -> None:
    with stack.factory() as db:
        assert db.get(sessions_models.UsersSessions, session_id).tokens_exchanged is False


class TestAnAccountWithMfaMatchedByEmail:
    def test_the_callback_and_the_exchange_write_nothing_to_the_account(self, mfa_plain_signin):
        stack = mfa_plain_signin
        idp_id = _provider(stack)
        before = _account(stack)

        with _recorded() as (audit, linked):
            session_id = _callback(stack, idp_id)
            response = _exchange(stack, session_id)

        assert response.status_code == 200, response.text
        assert response.json()["next_step"] == "mfa"
        _assert_untouched(stack, before, audit, linked)
        assert _store().read(session_id) is not None

    def test_a_wrong_code_leaves_the_account_as_it_was(self, mfa_plain_signin):
        stack = mfa_plain_signin
        idp_id = _provider(stack)
        before = _account(stack)

        with _recorded() as (audit, linked):
            session_id = _callback(stack, idp_id)
            response = _verify(stack, _exchange(stack, session_id).json()["mfa_challenge"], code="ZZZZ-ZZZZ")

        assert response.status_code == 400
        _assert_untouched(stack, before, audit, linked)
        _assert_unclaimed(stack, session_id)

    def test_a_security_change_before_the_code_leaves_the_account_as_it_was(
        self, mfa_plain_signin, security_generations
    ):
        stack = mfa_plain_signin
        idp_id = _provider(stack)
        before = _account(stack)

        with _recorded() as (audit, linked):
            session_id = _callback(stack, idp_id)
            challenge = _exchange(stack, session_id).json()["mfa_challenge"]
            security_generations.stage_bump(USER_ID, None)
            response = _verify(stack, challenge)

        assert response.status_code == 401
        assert response.json()["type"] == _SESSION_ENDED
        _assert_untouched(stack, before, audit, linked)
        _assert_unclaimed(stack, session_id)

    def test_a_deactivation_before_the_code_leaves_the_account_as_it_was(self, mfa_plain_signin, security_generations):
        stack = mfa_plain_signin
        idp_id = _provider(stack)
        before = _account(stack)

        with _recorded() as (audit, linked):
            session_id = _callback(stack, idp_id)
            challenge = _exchange(stack, session_id).json()["mfa_challenge"]
            # Deactivation bumps the account's security generation in the transaction that deactivates it.
            security_generations.stage_bump(USER_ID, None)
            with stack.factory() as db:
                db.execute(update(users_models.Users).where(users_models.Users.id == USER_ID).values(active=False))
                db.commit()
            response = _verify(stack, challenge)

        assert response.status_code == 401
        _assert_untouched(stack, before, audit, linked)
        _assert_unclaimed(stack, session_id)

    def test_the_right_code_links_and_syncs_the_account_as_the_user_when_the_sign_in_completes(self, mfa_plain_signin):
        stack = mfa_plain_signin
        idp_id = _provider(stack)
        _, email = _account(stack)

        with _recorded() as (audit, linked):
            session_id = _callback(stack, idp_id)
            response = _verify(stack, _exchange(stack, session_id).json()["mfa_challenge"])

        assert response.status_code == 200, response.text
        assert _links(stack) == [(USER_ID, _SUBJECT)]
        assert _account(stack) == (_SYNCED_NAME, email)
        entry = audit.assert_audited(_LINK, outcome="success", target_id=str(USER_ID))
        assert entry.details == {"idp_id": str(idp_id), "reason": None}
        assert (entry.actor_type, entry.actor_id) == ("user", str(USER_ID))
        audit.assert_audited(_LOGIN, outcome="success", target_id=str(USER_ID))
        linked.assert_called_once()
        assert linked.call_args.args[:2] == (USER_ID, idp_id)
        assert _store().read(session_id) is None

    def test_a_staged_record_lost_before_the_code_fails_closed(self, mfa_plain_signin):
        stack = mfa_plain_signin
        idp_id = _provider(stack)
        before = _account(stack)

        with _recorded() as (audit, linked):
            session_id = _callback(stack, idp_id)
            challenge = _exchange(stack, session_id).json()["mfa_challenge"]
            _store().discard(session_id)
            response = _verify(stack, challenge)

        assert response.status_code == 401
        assert response.json()["type"] == _SESSION_ENDED
        assert "set-cookie" not in response.headers
        _assert_untouched(stack, before, audit, linked)
        _assert_unclaimed(stack, session_id)
        entry = audit.assert_audited(_LOGIN, outcome="failure", target_id=str(USER_ID))
        assert entry.details["reason"] == "sso_session_ended"


class TestAnAccountWithMfaLinkedBySubject:
    def test_the_email_sync_waits_for_the_code(self, mfa_plain_signin):
        stack = mfa_plain_signin
        idp_id = _provider(stack)
        with stack.factory() as db:
            db.add(links_models.IdentityLink(user_id=USER_ID, idp_id=idp_id, idp_subject=_SUBJECT))
            db.commit()
        before = _account(stack)

        with _recorded() as (audit, _):
            session_id = _callback(stack, idp_id, email="synced@example.com")
            challenge = _exchange(stack, session_id).json()["mfa_challenge"]
            assert _account(stack) == before
            audit.assert_not_audited(_EMAIL_CHANGE)

            response = _verify(stack, challenge)

        assert response.status_code == 200, response.text
        assert _account(stack) == (_SYNCED_NAME, "synced@example.com")
        audit.assert_audited(_EMAIL_CHANGE, target_id=str(USER_ID))
        audit.assert_not_audited(_LINK)


class TestAnAccountWithoutMfaMatchedByEmail:
    def test_the_exchange_links_and_syncs_the_account(self, plain_signin):
        stack = plain_signin
        idp_id = _provider(stack)

        with _recorded() as (audit, linked):
            session_id = _callback(stack, idp_id)
            assert _links(stack) == []
            response = _exchange(stack, session_id)

        assert response.status_code == 200, response.text
        assert "access_token" in response.json()
        assert _links(stack) == [(USER_ID, _SUBJECT)]
        assert _account(stack)[0] == _SYNCED_NAME
        audit.assert_audited(_LINK, outcome="success", target_id=str(USER_ID))
        linked.assert_called_once()

    def test_a_lost_staged_record_is_answered_like_a_session_that_cannot_be_exchanged(self, plain_signin):
        stack = plain_signin
        idp_id = _provider(stack)
        before = _account(stack)

        with _recorded() as (audit, linked):
            session_id = _callback(stack, idp_id)
            _store().discard(session_id)
            response = _exchange(stack, session_id)

        assert response.status_code == 404
        _assert_untouched(stack, before, audit, linked)
        _assert_unclaimed(stack, session_id)
        entry = audit.assert_audited(_LOGIN, outcome="failure", target_id=str(USER_ID))
        assert entry.details["reason"] == "sso_session_ended"
