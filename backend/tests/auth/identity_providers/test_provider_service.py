"""Administration of identity-provider configuration."""

from unittest.mock import MagicMock, call, patch

import pytest
from sqlalchemy.orm.exc import StaleDataError

import core.exceptions as core_exceptions
import modules.auth.identity_providers.provider_service as provider_service
import modules.auth.identity_providers.schema as idp_schema


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
            crud.get_identity_provider.return_value = MagicMock(icon_uploaded=False)
            crud.delete_identity_provider.return_value = True
            provider_service.delete_identity_provider(3, MagicMock(), oidc, mock_db, if_match='"1"')
        assert order.mock_calls == [call.commit(), call.forget(3)]
