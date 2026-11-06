"""Administration of identity-provider configuration."""

from unittest.mock import MagicMock, call, patch

import pytest
from sqlalchemy.orm.exc import StaleDataError

import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.auth.identity_providers.models as idp_models
import modules.auth.identity_providers.provider_service as provider_service
import modules.auth.identity_providers.schema as idp_schema
from tests._helpers.db import create_sqlite_session


def test_a_delete_that_races_past_the_version_check_is_a_precondition_failure(mock_db):
    with (
        patch.object(provider_service.idp_crud, "get_identity_provider", return_value=MagicMock()),
        patch.object(
            provider_service.identity_provider_links_integration,
            "check_user_identity_providers_by_idp_id",
            return_value=False,
        ),
        patch.object(provider_service.idp_crud, "delete_identity_provider", side_effect=StaleDataError("moved")),
        patch.object(provider_service.idp_crud, "identity_provider_exists", return_value=True),
        pytest.raises(core_exceptions.PreconditionFailedError),
    ):
        provider_service.delete_identity_provider(3, MagicMock(), MagicMock(), mock_db, if_match='"1"')

    mock_db.commit.assert_not_called()


PUBLIC = [(2, 1, 0, "", ("8.8.8.8", 0))]
PRIVATE = [(2, 1, 0, "", ("10.0.0.5", 0))]


def _network(addresses, allowed=()):
    """Resolve every host to ``addresses`` and set SSRF_ALLOWED_HOSTS."""
    return (
        patch("core.network.socket.getaddrinfo", return_value=addresses),
        patch.object(provider_service.core_network.core_config.settings, "SSRF_ALLOWED_HOSTS", list(allowed)),
    )


def _create_data(**overrides):
    return idp_schema.IdentityProviderCreate(
        name="Pocket", slug="pocket", client_id="cid", client_secret="secret", **overrides
    )


class TestSaveRefusesUnsafeUrls:
    """A provider URL the server would later refuse to dial is refused when it is saved."""

    @pytest.mark.parametrize(
        "field", ["issuer_url", "authorization_endpoint", "token_endpoint", "userinfo_endpoint", "jwks_uri"]
    )
    def test_create_refuses_http_to_a_public_host_and_writes_nothing(self, mock_db, field):
        resolve, allowlist = _network(PUBLIC)
        with (
            resolve,
            allowlist,
            patch.object(provider_service, "idp_crud") as crud,
            pytest.raises(core_exceptions.InvalidInputError) as exc,
        ):
            provider_service.create_identity_provider(_create_data(**{field: "http://idp.example.com/x"}), mock_db)
        assert exc.value.status_code == 400
        assert exc.value.detail.startswith(f"{field}: URL must use https")
        crud.create_identity_provider.assert_not_called()
        mock_db.commit.assert_not_called()

    def test_create_allows_http_to_an_allowlisted_host(self, mock_db):
        resolve, allowlist = _network(PRIVATE, ["10.0.0.0/8"])
        with (
            resolve,
            allowlist,
            patch.object(provider_service, "idp_crud") as crud,
            patch.object(provider_service.identity_provider_serializers, "to_read_schema"),
        ):
            crud.get_identity_provider_by_slug.return_value = None
            crud.create_identity_provider.return_value = MagicMock(id=3, provider_type="oidc")
            provider_service.create_identity_provider(_create_data(issuer_url="http://idp.internal"), mock_db)
        crud.create_identity_provider.assert_called_once()
        mock_db.commit.assert_called_once()

    def test_create_accepts_https_and_ignores_empty_urls(self, mock_db):
        resolve, allowlist = _network(PUBLIC)
        with (
            resolve,
            allowlist,
            patch.object(provider_service, "idp_crud") as crud,
            patch.object(provider_service.identity_provider_serializers, "to_read_schema"),
        ):
            crud.get_identity_provider_by_slug.return_value = None
            crud.create_identity_provider.return_value = MagicMock(id=3, provider_type="oidc")
            provider_service.create_identity_provider(
                _create_data(issuer_url="https://idp.example.com", token_endpoint=""), mock_db
            )
        crud.create_identity_provider.assert_called_once()

    def test_update_refuses_http_to_a_public_host_and_writes_nothing(self, mock_db):
        resolve, allowlist = _network(PUBLIC)
        data = idp_schema.IdentityProviderUpdate(name="Pocket", slug="pocket", issuer_url="http://idp.example.com")
        with (
            resolve,
            allowlist,
            patch.object(provider_service, "idp_crud") as crud,
            pytest.raises(core_exceptions.InvalidInputError) as exc,
        ):
            provider_service.update_identity_provider(3, data, MagicMock(), mock_db, if_match='"1"')
        assert exc.value.detail.startswith("issuer_url: URL must use https")
        crud.update_identity_provider.assert_not_called()
        mock_db.commit.assert_not_called()

    def test_update_checks_only_the_fields_in_the_request(self, mock_db):
        resolve, allowlist = _network(PUBLIC)
        data = idp_schema.IdentityProviderUpdate(name="Renamed", slug="pocket", token_endpoint=None)
        oidc = MagicMock()
        with (
            resolve as getaddrinfo,
            allowlist,
            patch.object(provider_service, "idp_crud") as crud,
            patch.object(provider_service.identity_provider_serializers, "to_read_schema"),
        ):
            crud.get_identity_provider.return_value = MagicMock(slug="pocket")
            crud.update_identity_provider.return_value = MagicMock()
            provider_service.update_identity_provider(3, data, oidc, mock_db, if_match='"1"')
        getaddrinfo.assert_not_called()
        crud.update_identity_provider.assert_called_once()


class TestDiscoveryCacheEviction:
    """An admin edit or delete drops the cached discovery document, after the change is committed."""

    def test_update_forgets_the_document_after_the_commit(self, mock_db):
        order = MagicMock()
        order.attach_mock(mock_db.commit, "commit")
        oidc = MagicMock()
        order.attach_mock(oidc.forget_discovery, "forget")
        data = idp_schema.IdentityProviderUpdate(name="Renamed", slug="pocket")
        with (
            patch.object(provider_service, "idp_crud") as crud,
            patch.object(provider_service.identity_provider_serializers, "to_read_schema"),
        ):
            crud.get_identity_provider.return_value = MagicMock(slug="pocket")
            crud.update_identity_provider.return_value = MagicMock()
            provider_service.update_identity_provider(3, data, oidc, mock_db, if_match='"1"')
        assert order.mock_calls == [call.commit(), call.forget(3)]

    def test_update_that_fails_leaves_the_cache_alone(self, mock_db):
        oidc = MagicMock()
        data = idp_schema.IdentityProviderUpdate(name="Renamed", slug="pocket")
        with patch.object(provider_service, "idp_crud") as crud:
            crud.get_identity_provider.return_value = None
            with pytest.raises(core_exceptions.NotFoundError):
                provider_service.update_identity_provider(3, data, oidc, mock_db, if_match='"1"')
        oidc.forget_discovery.assert_not_called()

    def test_delete_forgets_the_document_after_the_commit(self, mock_db):
        order = MagicMock()
        order.attach_mock(mock_db.commit, "commit")
        oidc = MagicMock()
        order.attach_mock(oidc.forget_discovery, "forget")
        with (
            patch.object(provider_service, "idp_crud") as crud,
            patch.object(
                provider_service.identity_provider_links_integration,
                "check_user_identity_providers_by_idp_id",
                return_value=False,
            ),
        ):
            crud.get_identity_provider.return_value = MagicMock(icon_uploaded=False, provider_type="oidc")
            crud.delete_identity_provider.return_value = True
            provider_service.delete_identity_provider(3, MagicMock(), oidc, mock_db, if_match='"1"')
        assert order.mock_calls == [call.commit(), call.forget(3)]


class TestListProviders:
    """The admin and public lists are pages of the stored providers."""

    @staticmethod
    def _db():
        db = create_sqlite_session()
        for idp_id, name, enabled in ((1, "Zitadel", True), (2, "Authelia", False), (3, "Keycloak", True)):
            db.add(
                idp_models.IdentityProvider(
                    id=idp_id, name=name, slug=name.lower(), provider_type="oidc", enabled=enabled
                )
            )
        db.commit()
        return db

    def test_the_admin_list_pages_every_provider(self):
        db = self._db()

        page = provider_service.list_identity_providers(core_pagination.PageParams(1, 2), db)

        assert [provider.slug for provider in page.items] == ["authelia", "keycloak"]
        assert (page.total, page.next) == (3, 2)
        db.close()

    def test_the_public_list_pages_only_enabled_providers_and_their_public_fields(self):
        db = self._db()

        page = provider_service.get_enabled_identity_providers(core_pagination.PageParams(2, 1), db)

        assert page.items == [idp_schema.IdentityProviderPublicRead(id=1, name="Zitadel", slug="zitadel")]
        assert (page.total, page.page, page.next) == (2, 2, None)
        db.close()


class TestGetIdpTemplates:
    """Test suite for get_idp_templates function."""

    def test_get_idp_templates_returns_list(self):
        """Test get_idp_templates returns a list.

        Asserts:
            - Returns a list of idp_schema.IdentityProviderTemplateRead objects
        """
        # Act
        templates = provider_service.get_idp_templates()

        # Assert
        assert isinstance(templates, list)
        assert len(templates) > 0
        assert all(isinstance(t, idp_schema.IdentityProviderTemplateRead) for t in templates)

    def test_get_idp_templates_contains_expected_providers(self):
        """Test get_idp_templates contains expected providers.

        Asserts:
            - List contains Keycloak, Authentik, Authelia, Casdoor, Pocket ID
        """
        # Act
        templates = provider_service.get_idp_templates()

        # Assert
        template_ids = [t.template_id for t in templates]
        assert "keycloak" in template_ids
        assert "authentik" in template_ids
        assert "authelia" in template_ids
        assert "casdoor" in template_ids
        assert "pocketid" in template_ids

    def test_get_idp_templates_structure(self):
        """Test each template has required structure.

        Asserts:
            - Each template has required fields
        """
        # Act
        templates = provider_service.get_idp_templates()

        # Assert
        for template in templates:
            assert hasattr(template, "template_id")
            assert hasattr(template, "name")
            assert hasattr(template, "provider_type")
            assert hasattr(template, "scopes")
            assert hasattr(template, "description")

    def test_get_idp_templates_all_oidc(self):
        """Test all templates are OIDC providers.

        Asserts:
            - All templates have provider_type 'oidc'
        """
        # Act
        templates = provider_service.get_idp_templates()

        # Assert
        for template in templates:
            assert template.provider_type == "oidc"

    def test_get_idp_templates_has_user_mapping(self):
        """Test templates include user mapping configuration.

        Asserts:
            - Each template has user_mapping with username and email
        """
        # Act
        templates = provider_service.get_idp_templates()

        # Assert
        for template in templates:
            assert template.user_mapping is not None
            assert "username" in template.user_mapping
            assert "email" in template.user_mapping


class TestGetIdentityProvider:
    def test_returns_the_provider_as_its_read_schema(self, mock_db):
        state = MagicMock()
        with (
            patch.object(provider_service.idp_crud, "get_identity_provider", return_value=state),
            patch.object(provider_service.identity_provider_serializers, "to_read_schema") as to_read,
        ):
            result = provider_service.get_identity_provider(3, mock_db)

        assert result is to_read.return_value
        to_read.assert_called_once_with(state)

    def test_a_missing_provider_is_not_found(self, mock_db):
        with (
            patch.object(provider_service.idp_crud, "get_identity_provider", return_value=None),
            pytest.raises(core_exceptions.NotFoundError),
        ):
            provider_service.get_identity_provider(3, mock_db)
