"""Tests for stage-only identity-provider persistence."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError

import core.etag as core_etag
import core.exceptions as core_exceptions
import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.models as idp_models
import modules.auth.identity_providers.schema as idp_schema
from tests._helpers.db import create_sqlite_session


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
        "scopes": "openid profile email",
        "icon": None,
        "icon_uploaded": False,
        "auto_create_users": True,
        "sync_user_info": True,
        "sync_email": False,
        "link_by_email": False,
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
        issuer_url="https://idp.example.com",
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


def test_update_provider_without_credentials_keeps_the_stored_ones(mock_db):
    row = _row()
    mock_db.execute.return_value.scalar_one_or_none.return_value = row
    data = idp_schema.IdentityProviderUpdate(name="Updated", slug="updated")

    state = idp_crud.update_identity_provider(1, data, mock_db, if_match='"1"')

    assert state.client_id == "encrypted-client-id"
    assert state.client_secret == "encrypted-client-secret"


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
        staged = idp_crud.set_icon_uploaded(1, True, mock_db)

    assert staged == (3, False)
    assert row.icon_uploaded is True
    # Re-flagging forces the UPDATE that bumps the version, which is the icon's entity tag.
    flag_modified.assert_called_once_with(row, "icon_uploaded")
    mock_db.flush.assert_called_once()
    mock_db.commit.assert_not_called()


def test_set_icon_uploaded_on_a_missing_row_is_none(mock_db):
    mock_db.execute.return_value.scalar_one_or_none.return_value = None

    assert idp_crud.set_icon_uploaded(1, True, mock_db) is None


def test_get_ids_with_icon_returns_only_the_given_providers_that_have_an_uploaded_icon():
    db = create_sqlite_session()
    for idp_id, icon_uploaded in ((1, True), (2, False), (3, True)):
        db.add(
            idp_models.IdentityProvider(
                id=idp_id,
                name=f"Provider {idp_id}",
                slug=f"provider-{idp_id}",
                provider_type="oidc",
                icon_uploaded=icon_uploaded,
            )
        )
    db.commit()

    assert idp_crud.get_ids_with_icon([1, 2, 4], db) == {1}
    db.close()


def _db_with_providers():
    db = create_sqlite_session()
    for idp_id, name, enabled in ((1, "Zitadel", True), (2, "Authelia", False), (3, "Keycloak", True)):
        db.add(
            idp_models.IdentityProvider(id=idp_id, name=name, slug=name.lower(), provider_type="oidc", enabled=enabled)
        )
    db.commit()
    return db


def test_providers_page_is_ordered_by_name_and_windowed():
    db = _db_with_providers()

    first = idp_crud.get_identity_providers_page(db, enabled_only=False, limit=2, offset=0)
    second = idp_crud.get_identity_providers_page(db, enabled_only=False, limit=2, offset=2)

    assert [state.name for state in first] == ["Authelia", "Keycloak"]
    assert [state.name for state in second] == ["Zitadel"]
    assert idp_crud.count_identity_providers(db, enabled_only=False) == 3
    db.close()


def test_enabled_providers_page_leaves_out_disabled_providers():
    db = _db_with_providers()

    page = idp_crud.get_identity_providers_page(db, enabled_only=True, limit=25, offset=0)

    assert [state.name for state in page] == ["Keycloak", "Zitadel"]
    assert idp_crud.count_identity_providers(db, enabled_only=True) == 2
    db.close()


def _provider(slug, issuer):
    return idp_schema.IdentityProviderCreate(
        name=slug, slug=slug, client_id="c", client_secret="s", provider_type="oauth2", issuer_url=issuer
    )


@pytest.mark.parametrize("second", ["https://a.example.com", "https://a.example.com/", "https://a.example.com//"])
def test_create_provider_with_a_shared_issuer_raises_issuer_in_use(second):
    db = create_sqlite_session()
    try:
        idp_crud.create_identity_provider(_provider("one", "https://a.example.com/"), db)
        with pytest.raises(core_exceptions.IssuerInUseError):
            idp_crud.create_identity_provider(_provider("two", second), db)
        assert [row.slug for row in db.query(idp_models.IdentityProvider)] == ["one"]
    finally:
        db.close()


def test_update_provider_to_a_shared_issuer_raises_issuer_in_use():
    db = create_sqlite_session()
    try:
        idp_crud.create_identity_provider(_provider("one", "https://a.example.com"), db)
        other = idp_crud.create_identity_provider(_provider("two", "https://b.example.com"), db)
        data = idp_schema.IdentityProviderUpdate(name="two", slug="two", issuer_url="https://a.example.com/")
        with pytest.raises(core_exceptions.IssuerInUseError):
            idp_crud.update_identity_provider(other.id, data, db, if_match=core_etag.format_etag(other.version))
    finally:
        db.close()


def test_providers_without_an_issuer_do_not_conflict():
    db = create_sqlite_session()
    try:
        idp_crud.create_identity_provider(_provider("one", None), db)
        idp_crud.create_identity_provider(_provider("two", None), db)
        assert db.query(idp_models.IdentityProvider).count() == 2
    finally:
        db.close()


def test_another_integrity_error_is_not_reported_as_a_shared_issuer():
    db = create_sqlite_session()
    try:
        idp_crud.create_identity_provider(_provider("one", "https://a.example.com"), db)
        with pytest.raises(IntegrityError):
            idp_crud.create_identity_provider(_provider("one", "https://b.example.com"), db)
    finally:
        db.close()
