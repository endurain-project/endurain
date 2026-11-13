"""Administering a sign-in provider is audited without ever recording a value."""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import jasil.testing as jasil_testing
import pytest

import core.cryptography as core_cryptography
import modules.auth.identity_providers.audit_actions as idp_audit_actions
import modules.auth.identity_providers.contracts as idp_contracts
import modules.auth.identity_providers.provider_service as provider_service
import modules.auth.identity_providers.schema as idp_schema
import modules.auth.schema as auth_schema

STEP_UP = auth_schema.StepUpVerification()
VERIFIER = MagicMock()
IDP_ID = uuid.uuid4()


def _state(**overrides) -> idp_contracts.IdentityProviderState:
    fields = {
        "id": IDP_ID,
        "name": "Pocket",
        "slug": "pocket",
        "provider_type": "oidc",
        "enabled": True,
        "client_id": core_cryptography.encrypt_token_fernet("cid"),
        "client_secret": core_cryptography.encrypt_token_fernet("secret"),
        "issuer_url": None,
        "authorization_endpoint": None,
        "token_endpoint": None,
        "userinfo_endpoint": None,
        "scopes": "openid",
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
    fields.update(overrides)
    return idp_contracts.IdentityProviderState(**fields)


def test_creating_a_provider_is_audited_with_its_type_only(mock_db):
    data = idp_schema.IdentityProviderCreate(
        name="Pocket", slug="pocket", provider_type="oauth2", client_id="cid", client_secret="secret"
    )
    with (
        patch.object(provider_service, "idp_crud") as crud,
        patch.object(provider_service.identity_provider_serializers, "to_read_schema"),
        jasil_testing.capture_audit() as audit,
    ):
        crud.get_identity_provider_by_slug.return_value = None
        crud.create_identity_provider.return_value = _state()
        provider_service.create_identity_provider(data, STEP_UP, VERIFIER, mock_db)

    entry = audit.assert_audited(
        idp_audit_actions.IDENTITY_PROVIDER_CREATE.id, target_type="identity_provider", target_id=str(IDP_ID)
    )
    assert entry.target_owner_id is None
    assert entry.details == {"provider_type": "oidc"}


class TestUpdate:
    def _update(self, mock_db, before, after, data):
        with (
            patch.object(provider_service, "idp_crud") as crud,
            patch.object(provider_service.identity_provider_serializers, "to_read_schema"),
            patch.object(provider_service, "_reject_unsafe_urls"),
            jasil_testing.capture_audit() as audit,
        ):
            crud.get_identity_provider.return_value = before
            crud.get_identity_provider_by_slug.return_value = None
            crud.identity_provider_exists.return_value = True
            crud.update_identity_provider.return_value = after
            provider_service.update_identity_provider(
                IDP_ID, data, STEP_UP, VERIFIER, MagicMock(), mock_db, if_match='"1"'
            )
        return audit

    def test_names_the_fields_that_changed_and_never_their_values(self, mock_db):
        before = _state()
        after = _state(
            name="Renamed",
            client_id=core_cryptography.encrypt_token_fernet("new-cid"),
            client_secret=core_cryptography.encrypt_token_fernet("new-secret"),
        )
        data = idp_schema.IdentityProviderUpdate(
            name="Renamed", slug="pocket", client_id="new-cid", client_secret="new-secret", enabled=True
        )

        audit = self._update(mock_db, before, after, data)

        entry = audit.assert_audited(
            idp_audit_actions.IDENTITY_PROVIDER_UPDATE.id, target_type="identity_provider", target_id=str(IDP_ID)
        )
        assert entry.details == {"changed_fields": ["client_id", "client_secret", "name"], "sessions_ended": 0}

    def test_a_secret_the_administrator_sends_is_a_change_without_reading_the_stored_one(self, mock_db):
        # A stored secret the server can no longer decrypt is what an administrator replaces; that must still work.
        before = _state(client_secret="not-a-fernet-token")
        after = _state(client_secret=core_cryptography.encrypt_token_fernet("secret"))

        audit = self._update(
            mock_db,
            before,
            after,
            idp_schema.IdentityProviderUpdate(name="Pocket", slug="pocket", client_secret="secret"),
        )

        entry = audit.assert_audited(idp_audit_actions.IDENTITY_PROVIDER_UPDATE.id)
        assert entry.details == {"changed_fields": ["client_secret"], "sessions_ended": 0}
        mock_db.commit.assert_called_once()

    def test_disabling_ends_the_providers_sessions_and_audits_only_their_count(self, mock_db):
        with patch.object(
            provider_service.identity_provider_links_integration, "end_all_idp_sessions", return_value=4
        ) as end_all:
            audit = self._update(
                mock_db,
                _state(),
                _state(enabled=False),
                idp_schema.IdentityProviderUpdate(name="Pocket", slug="pocket", enabled=False),
            )

        end_all.assert_called_once_with(IDP_ID, mock_db)
        entry = audit.assert_audited(idp_audit_actions.IDENTITY_PROVIDER_UPDATE.id)
        assert entry.details == {"changed_fields": ["enabled"], "sessions_ended": 4}
        mock_db.commit.assert_called_once()

    def test_a_failure_while_ending_sessions_commits_nothing(self, mock_db):
        with (
            patch.object(
                provider_service.identity_provider_links_integration, "end_all_idp_sessions", side_effect=RuntimeError
            ),
            pytest.raises(RuntimeError),
        ):
            self._update(
                mock_db,
                _state(),
                _state(enabled=False),
                idp_schema.IdentityProviderUpdate(name="Pocket", slug="pocket", enabled=False),
            )

        mock_db.commit.assert_not_called()

    def test_enabling_or_editing_an_enabled_provider_ends_no_session(self, mock_db):
        with patch.object(provider_service.identity_provider_links_integration, "end_all_idp_sessions") as end_all:
            audit = self._update(
                mock_db,
                _state(enabled=False),
                _state(enabled=True),
                idp_schema.IdentityProviderUpdate(name="Pocket", slug="pocket", enabled=True),
            )
            self._update(
                mock_db,
                _state(),
                _state(name="Renamed"),
                idp_schema.IdentityProviderUpdate(name="Renamed", slug="pocket", enabled=True),
            )

        end_all.assert_not_called()
        entry = audit.assert_audited(idp_audit_actions.IDENTITY_PROVIDER_UPDATE.id)
        assert entry.details == {"changed_fields": ["enabled"], "sessions_ended": 0}

    def test_an_update_that_changes_nothing_writes_no_row(self, mock_db):
        before = _state()

        audit = self._update(
            mock_db, before, before, idp_schema.IdentityProviderUpdate(name="Pocket", slug="pocket", enabled=True)
        )

        audit.assert_not_audited(idp_audit_actions.IDENTITY_PROVIDER_UPDATE.id)


def test_deleting_a_provider_is_audited_with_its_type_only(mock_db):
    with (
        patch.object(provider_service, "idp_crud") as crud,
        patch.object(
            provider_service.identity_provider_links_integration, "check_user_identity_providers_by_idp_id"
        ) as linked,
        jasil_testing.capture_audit() as audit,
    ):
        crud.get_identity_provider.return_value = _state(provider_type="oauth2")
        crud.identity_provider_exists.return_value = True
        crud.delete_identity_provider.return_value = True
        linked.return_value = False
        provider_service.delete_identity_provider(
            IDP_ID, MagicMock(), MagicMock(), MagicMock(), MagicMock(), mock_db, if_match='"1"'
        )

    entry = audit.assert_audited(
        idp_audit_actions.IDENTITY_PROVIDER_DELETE.id, target_type="identity_provider", target_id=str(IDP_ID)
    )
    assert entry.details == {"provider_type": "oauth2"}
