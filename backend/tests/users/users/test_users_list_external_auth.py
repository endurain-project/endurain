"""The external_auth filter of the user list is applied in the query, so every page is full and the filter is exact."""

import uuid
from datetime import UTC, datetime

import pytest
from tests._helpers.db import create_sqlite_session

import modules.auth.identity_provider_links.models as identity_links_models
import modules.auth.identity_providers.models as idp_models
import modules.users.users.models as users_models
import modules.users.users.service as users_service

#: Users 1 to 6; users 2, 4 and 6 have an identity-provider link.
_IDS = {number: uuid.UUID(int=number) for number in range(1, 7)}
_LINKED = {_IDS[2], _IDS[4], _IDS[6]}
_IDP_ID = uuid.UUID(int=1)


@pytest.fixture
def db():
    session = create_sqlite_session()
    session.add(idp_models.IdentityProvider(id=_IDP_ID, name="Idp", slug="idp", provider_type="oidc", enabled=True))
    for number, user_id in _IDS.items():
        session.add(
            users_models.Users(
                id=user_id,
                name=f"User {number}",
                username=f"user{number}",
                email=f"user{number}@example.com",
                preferred_language="en",
                access_type="regular",
            )
        )
    session.flush()
    for user_id in _LINKED:
        session.add(
            identity_links_models.IdentityLink(
                user_id=user_id,
                idp_id=_IDP_ID,
                idp_subject=f"s{user_id.int}",
                linked_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )
    session.commit()
    yield session
    session.close()


@pytest.mark.parametrize(("external_auth", "expected"), [(True, _LINKED), (False, {_IDS[1], _IDS[3], _IDS[5]})])
def test_every_page_is_full_and_the_filter_is_exact(db, external_auth, expected):
    seen: set[uuid.UUID] = set()
    for page_number in range(1, len(expected) + 1):
        page = users_service.list_users(db, page_number=page_number, num_records=1, external_auth=external_auth)

        assert page.total == len(expected)
        assert len(page.items) == 1
        seen.add(page.items[0].id)

    assert seen == expected
    assert (
        users_service.list_users(db, page_number=len(expected) + 1, num_records=1, external_auth=external_auth).items
        == []
    )


def test_without_the_filter_every_user_is_listed(db):
    assert users_service.list_users(db, num_records=10).total == 6
