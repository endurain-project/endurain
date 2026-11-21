"""Two unlinks of one account's providers run one after the other, against real PostgreSQL rows and row locks."""

import threading

import pytest

from tests._factories.identity_links import make_identity_link
from tests._factories.users import PASSWORD, make_admin, make_user
from tests.auth.identity_providers.conftest import API
from tests.auth.identity_providers.sso_helpers import audit, links_of

STEP_UP = {"step_up": {"current_password": PASSWORD}}


@pytest.fixture
def setup(app, committed_sessions, sign_in, make_provider, provider, other_provider):
    """An administrator signed in twice, and a user without a password linked to two enabled providers."""
    first = make_provider("first")
    second = make_provider("second", issuer_url=other_provider.issuer)
    with committed_sessions() as db:
        admin = make_admin(db, timezone="UTC")
        member = make_user(db, with_password=False)
        make_identity_link(db, member.id, first, "subject-first")
        make_identity_link(db, member.id, second, "subject-second")
        db.commit()
    return {
        "admins": (sign_in(admin).client, sign_in(admin).client),
        "member": member,
        "providers": (first, second),
    }


def _unlink(client, user_id, idp_id):
    return client.post(f"{API}/users/{user_id}/identity-providers/{idp_id}/unlink", json=STEP_UP)


def test_a_concurrent_unlink_of_the_other_provider_is_refused_once_the_first_commits(setup, committed_sessions):
    results = []
    barrier = threading.Barrier(2)

    def unlink(client, idp_id):
        barrier.wait()
        results.append(_unlink(client, setup["member"].id, idp_id))

    threads = [
        threading.Thread(target=unlink, args=(client, idp))
        for client, idp in zip(setup["admins"], setup["providers"], strict=True)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert sorted(response.status_code for response in results) == [204, 409]
    refused = next(response for response in results if response.status_code == 409)
    assert refused.json()["type"].endswith("last-sign-in-method")
    assert len(links_of(committed_sessions)) == 1
    assert len(audit(committed_sessions, "auth.identity_link.unlink")) == 1


def test_a_provider_is_unlinked_while_another_stays(setup, committed_sessions):
    first, second = setup["providers"]

    response = _unlink(setup["admins"][0], setup["member"].id, first)

    assert response.status_code == 204, response.text
    assert [link.idp_id for link in links_of(committed_sessions)] == [second]


def test_the_last_provider_of_an_account_without_a_password_stays(setup, committed_sessions):
    first, second = setup["providers"]
    assert _unlink(setup["admins"][0], setup["member"].id, first).status_code == 204

    response = _unlink(setup["admins"][0], setup["member"].id, second)

    assert response.status_code == 409
    assert [link.idp_id for link in links_of(committed_sessions)] == [second]


def test_a_link_to_a_disabled_provider_does_not_count_as_a_way_to_sign_in(setup, committed_sessions):
    import sqlalchemy as sa

    import modules.auth.identity_providers.models as idp_models

    first, second = setup["providers"]
    with committed_sessions() as db:
        db.execute(
            sa.update(idp_models.IdentityProvider).where(idp_models.IdentityProvider.id == second).values(enabled=False)
        )
        db.commit()

    response = _unlink(setup["admins"][0], setup["member"].id, first)

    assert response.status_code == 409
