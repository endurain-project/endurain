"""Tests for stage-only identity-provider persistence."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.schema as idp_schema


def _row(**overrides):
    values = {
        "id": 1,
        "name": "Provider",
        "slug": "provider",
        "provider_type": "oidc",
        "enabled": True,
        "client_id": "encrypted-client-id",
        "client_secret": "encrypted-client-secret",
        "issuer_url": None,
        "authorization_endpoint": None,
        "token_endpoint": None,
        "userinfo_endpoint": None,
        "jwks_uri": None,
        "scopes": "openid profile email",
        "icon": None,
        "icon_uploaded": False,
        "auto_create_users": True,
        "sync_user_info": True,
        "user_mapping": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "version": 1,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_get_provider_returns_internal_contract(mock_db):
    mock_db.execute.return_value.scalar_one_or_none.return_value = _row()

    state = idp_crud.get_identity_provider(1, mock_db)

    assert state.id == 1
    assert state.client_id == "encrypted-client-id"


def test_create_provider_stages_and_returns_encrypted_state(mock_db):
    data = idp_schema.IdentityProviderCreate(
        name="Provider",
        slug="provider",
        client_id="client-id",
        client_secret="client-secret",
    )

    def flush():
        row = mock_db.add.call_args.args[0]
        row.id = 1
        row.created_at = datetime.now(UTC)
        row.updated_at = datetime.now(UTC)
        row.version = 1

    mock_db.flush.side_effect = flush

    state = idp_crud.create_identity_provider(data, mock_db)

    mock_db.add.assert_called_once()
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_not_called()
    assert state.slug == "provider"
    assert state.client_id != "client-id"
    assert state.client_secret != "client-secret"


def test_update_provider_stages_without_committing(mock_db):
    row = _row()
    mock_db.execute.return_value.scalar_one_or_none.return_value = row
    data = idp_schema.IdentityProviderUpdate(
        name="Updated",
        slug="updated",
        client_id="new-client-id",
    )

    state = idp_crud.update_identity_provider(1, data, mock_db, if_match='"1"')

    assert state.name == "Updated"
    assert state.slug == "updated"
    assert state.client_id != "new-client-id"
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_not_called()


def test_update_provider_checks_the_version_before_mutating(mock_db):
    import pytest

    import core.exceptions as core_exceptions

    row = _row(version=2)
    mock_db.execute.return_value.scalar_one_or_none.return_value = row
    data = idp_schema.IdentityProviderUpdate(name="Stale", slug="provider")

    with pytest.raises(core_exceptions.PreconditionFailedError):
        idp_crud.update_identity_provider(1, data, mock_db, if_match='"1"')

    assert row.name == "Provider"
    mock_db.flush.assert_not_called()
    mock_db.commit.assert_not_called()


def test_delete_provider_stages_without_committing(mock_db):
    row = _row()
    mock_db.execute.return_value.scalar_one_or_none.return_value = row

    deleted = idp_crud.delete_identity_provider(1, mock_db, if_match='"1"')

    assert deleted is True
    mock_db.delete.assert_called_once_with(row)
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_not_called()


def test_delete_provider_checks_the_version_before_deleting(mock_db):
    import pytest

    import core.exceptions as core_exceptions

    mock_db.execute.return_value.scalar_one_or_none.return_value = _row(version=2)

    with pytest.raises(core_exceptions.PreconditionFailedError):
        idp_crud.delete_identity_provider(1, mock_db, if_match='"1"')

    mock_db.delete.assert_not_called()


def test_set_icon_uploaded_flags_the_row_and_returns_its_version(mock_db):
    row = _row(icon_uploaded=False, version=3)
    mock_db.execute.return_value.scalar_one_or_none.return_value = row

    with patch.object(idp_crud, "flag_modified") as flag_modified:
        version = idp_crud.set_icon_uploaded(1, True, mock_db)

    assert version == 3
    assert row.icon_uploaded is True
    # Re-flagging forces the UPDATE that bumps the version, which is the icon's entity tag.
    flag_modified.assert_called_once_with(row, "icon_uploaded")
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_not_called()


def test_set_icon_uploaded_on_a_missing_row_is_none(mock_db):
    mock_db.execute.return_value.scalar_one_or_none.return_value = None

    assert idp_crud.set_icon_uploaded(1, True, mock_db) is None
