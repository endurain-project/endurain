"""Concurrent completions of SSO sign-ins that each staged a link, against real PostgreSQL rows and row locks.

Two completions of one session: the session claim is one-shot, so only one applies the link. Two sessions that link
the same provider subject to different accounts: the unique key decides, and the loser signs in nobody.
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import sqlalchemy as sa
from fastapi.testclient import TestClient

import modules.auth.identity_provider_links.models as links_models
import modules.auth.identity_providers.contracts as idp_contracts
import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.events as idp_events
import modules.auth.identity_providers.schema as idp_schema
import modules.auth.sessions.models as sessions_models
from tests.auth.authentication.conftest import WEB, exchange, make_account, make_sso_session, verify

_SUBJECT = "subject-at-the-provider"


def _provider(sessions) -> uuid.UUID:
    """Store a provider that links an account matched by email."""
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
                sync_user_info=False,
                sync_email=False,
            ),
            db,
        )
        db.commit()
        return idp.id


def _staged_link(user, idp_id: uuid.UUID) -> idp_contracts.StagedSignIn:
    return idp_contracts.StagedSignIn(
        user_id=user.id,
        idp_id=idp_id,
        subject=_SUBJECT,
        create_link=True,
        claims=idp_contracts.SyncedClaims(name=None, email=None, email_verified=False),
    )


def _links(sessions) -> list[tuple[uuid.UUID, str]]:
    with sessions() as db:
        rows = db.execute(sa.select(links_models.IdentityLink.user_id, links_models.IdentityLink.idp_subject)).all()
        return [(row.user_id, row.idp_subject) for row in rows]


def _exchanged(sessions, session_id) -> bool:
    with sessions() as db:
        return db.get(sessions_models.UsersSessions, session_id).tokens_exchanged


def _race(requests) -> list:
    """Run the requests at the same moment, each on a client of its own, and return their responses in order."""
    barrier = threading.Barrier(len(requests))

    def run(request):
        barrier.wait(timeout=10)
        return request()

    with ThreadPoolExecutor(max_workers=len(requests)) as pool:
        return list(pool.map(run, requests))


def test_two_sessions_linking_one_subject_to_two_accounts_sign_in_only_the_first_to_commit(
    app, committed_sessions, published
):
    events = published(idp_events.IDP_LINKED)
    idp_id = _provider(committed_sessions)
    users = [make_account(committed_sessions).user for _ in range(2)]
    sessions = [
        make_sso_session(committed_sessions, user, idp_id=idp_id, staged=_staged_link(user, idp_id)) for user in users
    ]

    responses = _race([lambda s=s: exchange(TestClient(app), s, headers=WEB) for s in sessions])

    assert sorted(r.status_code for r in responses) == [200, 404]
    winner = 0 if responses[0].status_code == 200 else 1
    assert _links(committed_sessions) == [(users[winner].id, _SUBJECT)]
    assert _exchanged(committed_sessions, sessions[winner]) is True
    assert _exchanged(committed_sessions, sessions[1 - winner]) is False
    assert [e.payload["user_id"] for e in events] == [str(users[winner].id)]


def test_two_mfa_steps_for_one_session_sign_in_once_and_apply_its_staged_link_once(app, committed_sessions, published):
    events = published(idp_events.IDP_LINKED)
    idp_id = _provider(committed_sessions)
    account = make_account(committed_sessions, mfa=True)
    session_id = make_sso_session(
        committed_sessions, account.user, idp_id=idp_id, staged=_staged_link(account.user, idp_id)
    )
    challenges = [exchange(TestClient(app), session_id, headers=WEB).json()["mfa_challenge"] for _ in range(2)]
    assert _links(committed_sessions) == []

    responses = _race(
        [
            lambda c=c, code=code: verify(TestClient(app), c, code)
            for c, code in zip(challenges, account.mfa.backup_codes[:2], strict=True)
        ]
    )

    assert sorted(r.status_code for r in responses) == [200, 401]
    assert _links(committed_sessions) == [(account.user.id, _SUBJECT)]
    assert _exchanged(committed_sessions, session_id) is True
    assert len(events) == 1
