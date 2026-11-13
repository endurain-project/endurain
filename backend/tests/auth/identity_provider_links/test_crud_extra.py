"""Additional identity-provider link persistence tests."""

import uuid

import modules.auth.identity_provider_links.crud as identity_links_crud
from tests._helpers.auth import MOCK_USER_ID, OTHER_USER_ID

IDP_ID = uuid.uuid4()


def test_empty_user_list_has_no_link_counts(mock_db):
    assert identity_links_crud.get_identity_link_counts_for_users([], mock_db) == {}
    mock_db.execute.assert_not_called()


def test_missing_link_returns_none(mock_db):
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    assert identity_links_crud.get_user_identity_provider_by_user_id_and_idp_id(MOCK_USER_ID, IDP_ID, mock_db) is None


def test_link_counts_are_grouped_by_user(mock_db):
    mock_db.execute.return_value.all.return_value = [(MOCK_USER_ID, 2)]
    assert identity_links_crud.get_identity_link_counts_for_users([MOCK_USER_ID, OTHER_USER_ID], mock_db) == {
        MOCK_USER_ID: 2
    }
