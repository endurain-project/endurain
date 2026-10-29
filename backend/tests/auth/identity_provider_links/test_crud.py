"""Tests for staged identity-provider link persistence."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError

import core.exceptions as core_exceptions
import modules.auth.identity_provider_links.contracts as identity_links_contracts
import modules.auth.identity_provider_links.crud as identity_links_crud


def _link(**overrides):
    values = {
        "id": 1,
        "user_id": 7,
        "idp_id": 3,
        "idp_subject": "subject-1",
        "linked_at": datetime.now(UTC),
        "last_login": None,
        "idp_refresh_token": None,
        "idp_access_token_expires_at": None,
        "idp_refresh_token_updated_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_get_links_returns_internal_contracts(mock_db):
    row = _link()
    mock_db.execute.return_value.scalars.return_value.all.return_value = [row]
    result = identity_links_crud.get_user_identity_providers_by_user_id(7, mock_db)
    assert result == [identity_links_contracts.IdentityLinkRead.model_validate(row)]


def test_get_link_by_subject_returns_contract(mock_db):
    row = _link()
    mock_db.execute.return_value.scalar_one_or_none.return_value = row
    result = identity_links_crud.get_user_identity_provider_by_subject_and_idp_id(3, "subject-1", mock_db)
    assert result.idp_subject == "subject-1"


def test_check_linked_provider_and_counts(mock_db):
    mock_db.execute.return_value.scalar.return_value = True
    assert identity_links_crud.check_user_identity_providers_by_idp_id(3, mock_db) is True
    mock_db.execute.return_value.all.return_value = [SimpleNamespace(user_id=7, count=2)]
    assert identity_links_crud.get_identity_link_counts_for_users([7], mock_db) == {7: 2}


def test_create_link_stages_row_and_translates_unique_race(mock_db):
    row = _link()
    with (
        patch("modules.auth.identity_provider_links.crud.identity_link_models.IdentityLink", return_value=row),
        patch(
            "modules.auth.identity_provider_links.crud.identity_link_serializers.to_read_schema",
            return_value=identity_links_contracts.IdentityLinkRead.model_validate(row),
        ),
    ):
        result = identity_links_crud.create_user_identity_provider(7, 3, "subject-1", mock_db)
    assert result.id == 1
    assert mock_db.flush.call_count == 2
    mock_db.commit.assert_not_called()

    mock_db.flush.side_effect = [None, IntegrityError("insert", {}, RuntimeError("duplicate"))]
    with pytest.raises(core_exceptions.ConflictError):
        identity_links_crud.create_user_identity_provider(7, 3, "subject-1", mock_db)


def test_update_and_clear_provider_tokens_stage_changes(mock_db):
    row = _link()
    mock_db.execute.return_value.scalar_one_or_none.return_value = row
    result = identity_links_crud.update_user_identity_provider_last_login(7, 3, mock_db)
    assert result.last_login is not None
    assert identity_links_crud.clear_user_identity_provider_refresh_token_by_user_id_and_idp_id(7, 3, mock_db)
    mock_db.commit.assert_not_called()


def test_missing_token_metadata_link_returns_none_or_false(mock_db):
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    assert (
        identity_links_crud.store_user_identity_provider_tokens(7, 3, "encrypted", datetime.now(UTC), mock_db) is None
    )
    assert identity_links_crud.clear_user_identity_provider_refresh_token_by_user_id_and_idp_id(7, 3, mock_db) is False


def test_delete_link_stages_deletion(mock_db):
    mock_db.execute.return_value.rowcount = 1
    assert identity_links_crud.delete_user_identity_provider(7, 3, mock_db) is True
    mock_db.commit.assert_not_called()
