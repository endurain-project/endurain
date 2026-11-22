"""Two unlinks of one account's providers run one after the other, against real PostgreSQL rows."""

import threading
import time

import pytest
from sqlalchemy import text

import core.exceptions as core_exceptions
import modules.auth.account_security.identity_link_service as identity_link_service
import modules.auth.identity_provider_links.integration_service as identity_provider_links_integration
import modules.auth.identity_providers.schema as idp_schema
from modules.auth.identity_providers import crud as idp_crud
from tests._helpers.auth import MOCK_USER_ID
from tests._helpers.db import ensure_user


@pytest.fixture
def two_linked_providers(pg_factory):
    """A user with no password, linked to two enabled providers; returns the two provider ids."""
    ensure_user(pg_factory, MOCK_USER_ID)
    ids = []
    with pg_factory() as db:
        for slug in ("first", "second"):
            state = idp_crud.create_identity_provider(
                idp_schema.IdentityProviderCreate(
                    name=slug,
                    slug=slug,
                    issuer_url=f"https://{slug}.example.com",
                    client_id="endurain",
                    client_secret="secret",
                    enabled=True,
                ),
                db,
            )
            identity_provider_links_integration.create_user_identity_provider(
                MOCK_USER_ID, state.id, f"subject-{slug}", db
            )
            ids.append(state.id)
        db.commit()
    return ids


def _links(factory) -> int:
    with factory() as db:
        return db.execute(text("SELECT count(*) FROM users_identity_providers")).scalar_one()


def test_a_concurrent_unlink_of_the_other_provider_is_refused_once_the_first_commits(pg_factory, two_linked_providers):
    first, second = two_linked_providers
    outcome: list[BaseException | None] = []

    def unlink_second() -> None:
        try:
            with pg_factory() as db:
                identity_link_service.admin_delete_identity_provider_link(MOCK_USER_ID, second, db)
                db.commit()
            outcome.append(None)
        except core_exceptions.LastSignInMethodError as err:
            outcome.append(err)

    with pg_factory() as db:
        identity_link_service.admin_delete_identity_provider_link(MOCK_USER_ID, first, db)
        racer = threading.Thread(target=unlink_second)
        racer.start()
        # The racer must wait for the security-generation lock this transaction holds; without it the racer would
        # read both links still present and finish before the commit.
        time.sleep(0.5)
        assert outcome == []
        db.commit()
    racer.join(timeout=10)

    assert len(outcome) == 1
    assert isinstance(outcome[0], core_exceptions.LastSignInMethodError)
    assert _links(pg_factory) == 1
