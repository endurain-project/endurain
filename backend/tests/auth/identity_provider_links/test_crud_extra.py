"""Additional identity-provider link persistence tests."""

from types import SimpleNamespace

import modules.auth.identity_provider_links.crud as identity_links_crud


def test_empty_user_list_has_no_link_counts(mock_db):
    assert identity_links_crud.get_identity_link_counts_for_users([], mock_db) == {}
    mock_db.execute.assert_not_called()


def test_missing_link_returns_none(mock_db):
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    assert identity_links_crud.get_user_identity_provider_by_user_id_and_idp_id(7, 3, mock_db) is None


def test_link_counts_are_grouped_by_user(mock_db):
    mock_db.execute.return_value.all.return_value = [SimpleNamespace(user_id=7, count=2)]
    assert identity_links_crud.get_identity_link_counts_for_users([7, 8], mock_db) == {7: 2}
