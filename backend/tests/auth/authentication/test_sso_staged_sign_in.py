"""An SSO sign-in changes nothing on an existing account until the sign-in completes, after its second factor.

The callback's account match and session creation run for real: it matches the account by its verified email and
creates the session, and the exchange and ``/auth/mfa/verify`` routes finish it. The link, the profile sync and their
audit rows and events appear only when the sign-in completes; an MFA step that is abandoned, fails, or is outdated
leaves the account as it was.
"""

import uuid

import sqlalchemy as sa
from jasil.audit.models import AuditLog

import core.dependencies as core_dependencies
import modules.auth.identity_provider_links.models as links_models
import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.events as idp_events
import modules.auth.identity_providers.schema as idp_schema
import modules.auth.identity_providers.user_provisioning_service as user_provisioning_service
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sessions.models as sessions_models
import modules.users.users.models as users_models
from modules.auth.identity_providers.staged_sign_in_store import StagedSignInStore
from tests.auth.authentication.conftest import (
    WEB,
    WRONG_CODE,
    Account,
    exchange,
    make_sso_session,
    verify,
)

_SUBJECT = "subject-at-the-provider"
_SYNCED_NAME = "Name From The Provider"
_LINK = "auth.identity_link.link"
_EMAIL_CHANGE = "users.email.change"
_LOGIN = "auth.session.login"
_SESSION_ENDED = "urn:endurain:error:session-ended"


def _store() -> StagedSignInStore:
    return StagedSignInStore(core_dependencies.get_platform_state())


def _provider(sessions) -> uuid.UUID:
    """Store a provider that links by email and syncs the name and the email."""
    with sessions() as db:
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
        db.commit()
        return idp.id


def _callback(sessions, account: Account, idp_id: uuid.UUID, *, email: str | None = None) -> uuid.UUID:
    """Run the login callback's account match and session creation for the provider's verified claims."""
    with sessions() as db:
        idp = idp_crud.get_identity_provider(idp_id, db)
        userinfo = {
            "sub": _SUBJECT,
            "email": email or account.user.email,
            "email_verified": True,
            "name": _SYNCED_NAME,
        }
        user, staged = user_provisioning_service.find_or_create_user(idp, _SUBJECT, userinfo, db)
        db.commit()
    return make_sso_session(sessions, user, idp_id=idp_id, staged=staged)


def _account(sessions, account: Account) -> tuple[str, str]:
    with sessions() as db:
        user = db.get(users_models.Users, account.user.id)
        return user.name, user.email


def _links(sessions) -> list[tuple[uuid.UUID, str]]:
    with sessions() as db:
        rows = db.execute(sa.select(links_models.IdentityLink.user_id, links_models.IdentityLink.idp_subject)).all()
        return [(row.user_id, row.idp_subject) for row in rows]


def _rows(sessions, action_id: str) -> list[AuditLog]:
    with sessions() as db:
        return list(db.scalars(sa.select(AuditLog).where(AuditLog.action_id == action_id)))


def _assert_untouched(sessions, account, before, events) -> None:
    assert _account(sessions, account) == before
    assert _links(sessions) == []
    assert _rows(sessions, _LINK) == []
    assert _rows(sessions, _EMAIL_CHANGE) == []
    assert events == []


def _assert_unclaimed(sessions, session_id) -> None:
    with sessions() as db:
        assert db.get(sessions_models.UsersSessions, session_id).tokens_exchanged is False


class TestAnAccountWithMfaMatchedByEmail:
    def test_the_callback_and_the_exchange_write_nothing_to_the_account(
        self, client, committed_sessions, mfa_account, published
    ):
        events = published(idp_events.IDP_LINKED)
        idp_id = _provider(committed_sessions)
        before = _account(committed_sessions, mfa_account)

        session_id = _callback(committed_sessions, mfa_account, idp_id)
        response = exchange(client, session_id, headers=WEB)

        assert response.status_code == 200
        assert response.json()["next_step"] == "mfa"
        _assert_untouched(committed_sessions, mfa_account, before, events)
        assert _store().read(session_id) is not None

    def test_a_wrong_code_leaves_the_account_as_it_was(self, client, committed_sessions, mfa_account, published):
        events = published(idp_events.IDP_LINKED)
        idp_id = _provider(committed_sessions)
        before = _account(committed_sessions, mfa_account)
        session_id = _callback(committed_sessions, mfa_account, idp_id)

        response = verify(client, exchange(client, session_id, headers=WEB).json()["mfa_challenge"], WRONG_CODE)

        assert response.status_code == 400
        _assert_untouched(committed_sessions, mfa_account, before, events)
        _assert_unclaimed(committed_sessions, session_id)

    def test_a_security_change_before_the_code_leaves_the_account_as_it_was(
        self, client, committed_sessions, mfa_account, published
    ):
        events = published(idp_events.IDP_LINKED)
        idp_id = _provider(committed_sessions)
        before = _account(committed_sessions, mfa_account)
        session_id = _callback(committed_sessions, mfa_account, idp_id)
        challenge = exchange(client, session_id, headers=WEB).json()["mfa_challenge"]
        with committed_sessions() as db:
            security_generation_integration.stage_bump(mfa_account.user.id, db)
            db.commit()

        response = verify(client, challenge, mfa_account.backup_code)

        assert response.status_code == 401
        assert response.json()["type"] == _SESSION_ENDED
        _assert_untouched(committed_sessions, mfa_account, before, events)
        _assert_unclaimed(committed_sessions, session_id)

    def test_a_deactivation_before_the_code_leaves_the_account_as_it_was(
        self, client, committed_sessions, mfa_account, published
    ):
        events = published(idp_events.IDP_LINKED)
        idp_id = _provider(committed_sessions)
        before = _account(committed_sessions, mfa_account)
        session_id = _callback(committed_sessions, mfa_account, idp_id)
        challenge = exchange(client, session_id, headers=WEB).json()["mfa_challenge"]
        with committed_sessions() as db:
            # Deactivation bumps the account's security generation in the transaction that deactivates it.
            security_generation_integration.stage_bump(mfa_account.user.id, db)
            db.execute(
                sa.update(users_models.Users).where(users_models.Users.id == mfa_account.user.id).values(active=False)
            )
            db.commit()

        response = verify(client, challenge, mfa_account.backup_code)

        assert response.status_code == 401
        assert _links(committed_sessions) == []
        assert events == []
        assert _account(committed_sessions, mfa_account) == before
        _assert_unclaimed(committed_sessions, session_id)

    def test_the_right_code_links_and_syncs_the_account_as_the_user_when_the_sign_in_completes(
        self, client, committed_sessions, mfa_account, published
    ):
        events = published(idp_events.IDP_LINKED)
        idp_id = _provider(committed_sessions)
        _, email = _account(committed_sessions, mfa_account)
        session_id = _callback(committed_sessions, mfa_account, idp_id)

        response = verify(
            client, exchange(client, session_id, headers=WEB).json()["mfa_challenge"], mfa_account.backup_code
        )

        assert response.status_code == 200
        assert _links(committed_sessions) == [(mfa_account.user.id, _SUBJECT)]
        assert _account(committed_sessions, mfa_account) == (_SYNCED_NAME, email)
        (link,) = _rows(committed_sessions, _LINK)
        assert (link.outcome, link.target_id) == ("success", str(mfa_account.user.id))
        assert link.details == {"idp_id": str(idp_id), "reason": None}
        assert (link.actor_type, link.actor_id) == ("user", str(mfa_account.user.id))
        (login_row,) = _rows(committed_sessions, _LOGIN)
        assert (login_row.outcome, login_row.target_id) == ("success", str(mfa_account.user.id))
        assert [(e.payload["user_id"], e.payload["idp_id"]) for e in events] == [
            (str(mfa_account.user.id), str(idp_id))
        ]
        assert _store().read(session_id) is None

    def test_a_staged_record_lost_before_the_code_fails_closed(
        self, client, committed_sessions, mfa_account, published
    ):
        events = published(idp_events.IDP_LINKED)
        idp_id = _provider(committed_sessions)
        before = _account(committed_sessions, mfa_account)
        session_id = _callback(committed_sessions, mfa_account, idp_id)
        challenge = exchange(client, session_id, headers=WEB).json()["mfa_challenge"]
        _store().discard(session_id)

        response = verify(client, challenge, mfa_account.backup_code)

        assert response.status_code == 401
        assert response.json()["type"] == _SESSION_ENDED
        assert "set-cookie" not in response.headers
        _assert_untouched(committed_sessions, mfa_account, before, events)
        _assert_unclaimed(committed_sessions, session_id)
        (row,) = _rows(committed_sessions, _LOGIN)
        assert (row.outcome, row.target_id) == ("failure", str(mfa_account.user.id))
        assert row.details["reason"] == "sso_session_ended"


class TestAnAccountWithMfaLinkedBySubject:
    def test_the_email_sync_waits_for_the_code(self, client, committed_sessions, mfa_account):
        idp_id = _provider(committed_sessions)
        with committed_sessions() as db:
            db.add(links_models.IdentityLink(user_id=mfa_account.user.id, idp_id=idp_id, idp_subject=_SUBJECT))
            db.commit()
        before = _account(committed_sessions, mfa_account)
        session_id = _callback(committed_sessions, mfa_account, idp_id, email="synced@example.com")
        challenge = exchange(client, session_id, headers=WEB).json()["mfa_challenge"]
        assert _account(committed_sessions, mfa_account) == before
        assert _rows(committed_sessions, _EMAIL_CHANGE) == []

        response = verify(client, challenge, mfa_account.backup_code)

        assert response.status_code == 200
        assert _account(committed_sessions, mfa_account) == (_SYNCED_NAME, "synced@example.com")
        (change,) = _rows(committed_sessions, _EMAIL_CHANGE)
        assert change.target_id == str(mfa_account.user.id)
        assert _rows(committed_sessions, _LINK) == []


class TestAnAccountWithoutMfaMatchedByEmail:
    def test_the_exchange_links_and_syncs_the_account(self, client, committed_sessions, account, published):
        events = published(idp_events.IDP_LINKED)
        idp_id = _provider(committed_sessions)
        session_id = _callback(committed_sessions, account, idp_id)
        assert _links(committed_sessions) == []

        response = exchange(client, session_id, headers=WEB)

        assert response.status_code == 200
        assert "access_token" in response.json()
        assert _links(committed_sessions) == [(account.user.id, _SUBJECT)]
        assert _account(committed_sessions, account)[0] == _SYNCED_NAME
        (link,) = _rows(committed_sessions, _LINK)
        assert (link.outcome, link.target_id) == ("success", str(account.user.id))
        assert len(events) == 1

    def test_a_lost_staged_record_is_answered_like_a_session_that_cannot_be_exchanged(
        self, client, committed_sessions, account, published
    ):
        events = published(idp_events.IDP_LINKED)
        idp_id = _provider(committed_sessions)
        before = _account(committed_sessions, account)
        session_id = _callback(committed_sessions, account, idp_id)
        _store().discard(session_id)

        response = exchange(client, session_id, headers=WEB)

        assert response.status_code == 404
        _assert_untouched(committed_sessions, account, before, events)
        _assert_unclaimed(committed_sessions, session_id)
        (row,) = _rows(committed_sessions, _LOGIN)
        assert (row.outcome, row.target_id, row.details["reason"]) == (
            "failure",
            str(account.user.id),
            "sso_session_ended",
        )
