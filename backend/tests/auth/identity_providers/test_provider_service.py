"""Administration of identity-provider configuration."""

from typing import ClassVar
from unittest.mock import MagicMock, call, patch

import pytest
from sqlalchemy.orm.exc import StaleDataError

import core.exceptions as core_exceptions
import core.pagination as core_pagination
import modules.auth.identity_providers.constants as idp_constants
import modules.auth.identity_providers.models as idp_models
import modules.auth.identity_providers.provider_service as provider_service
import modules.auth.identity_providers.schema as idp_schema
import modules.auth.schema as auth_schema
from tests._helpers.db import create_sqlite_session

STEP_UP = auth_schema.StepUpVerification()
VERIFIER = MagicMock()


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
        provider_service.delete_identity_provider(
            3, STEP_UP, VERIFIER, MagicMock(), MagicMock(), mock_db, if_match='"1"'
        )

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
    fields = {"issuer_url": "https://idp.example.com", **overrides}
    return idp_schema.IdentityProviderCreate(
        name="Pocket", slug="pocket", client_id="cid", client_secret="secret", **fields
    )


class TestSaveRefusesUnsafeUrls:
    """A provider URL the server would later refuse to dial is refused when it is saved."""

    @pytest.mark.parametrize("field", ["issuer_url", "authorization_endpoint", "token_endpoint", "userinfo_endpoint"])
    def test_create_refuses_http_to_a_public_host_and_writes_nothing(self, mock_db, field):
        resolve, allowlist = _network(PUBLIC)
        with (
            resolve,
            allowlist,
            patch.object(provider_service, "idp_crud") as crud,
            pytest.raises(core_exceptions.InvalidInputError) as exc,
        ):
            provider_service.create_identity_provider(
                _create_data(**{field: "http://idp.example.com/x"}), STEP_UP, VERIFIER, mock_db
            )
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
            crud.get_identity_provider_by_issuer.return_value = None
            crud.create_identity_provider.return_value = MagicMock(id=3, provider_type="oidc")
            provider_service.create_identity_provider(
                _create_data(issuer_url="http://idp.internal"), STEP_UP, VERIFIER, mock_db
            )
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
            crud.get_identity_provider_by_issuer.return_value = None
            crud.create_identity_provider.return_value = MagicMock(id=3, provider_type="oidc")
            provider_service.create_identity_provider(
                _create_data(issuer_url="https://idp.example.com", token_endpoint=""), STEP_UP, VERIFIER, mock_db
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
            provider_service.update_identity_provider(3, data, STEP_UP, VERIFIER, MagicMock(), mock_db, if_match='"1"')
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
            provider_service.update_identity_provider(3, data, STEP_UP, VERIFIER, oidc, mock_db, if_match='"1"')
        getaddrinfo.assert_not_called()
        crud.update_identity_provider.assert_called_once()


class TestUpdateKeepsOidcRequirements:
    """An update is checked as the merged result of the stored provider and the request, before anything is written."""

    def _update(self, mock_db, stored, **changes):
        data = idp_schema.IdentityProviderUpdate.model_validate({"name": "Pocket", "slug": "pocket", **changes})
        resolve, allowlist = _network(PUBLIC)
        with (
            resolve,
            allowlist,
            patch.object(provider_service, "idp_crud") as crud,
            patch.object(
                provider_service.identity_provider_links_integration,
                "check_user_identity_providers_by_idp_id",
                return_value=False,
            ),
            patch.object(provider_service.identity_provider_serializers, "to_read_schema"),
        ):
            crud.get_identity_provider_by_issuer.return_value = None
            crud.get_identity_provider.return_value = MagicMock(slug="pocket", **stored)
            crud.update_identity_provider.return_value = MagicMock()
            try:
                provider_service.update_identity_provider(
                    3, data, STEP_UP, VERIFIER, MagicMock(), mock_db, if_match='"1"'
                )
            finally:
                self.crud = crud

    OIDC: ClassVar[dict[str, str]] = {
        "provider_type": "oidc",
        "issuer_url": "https://idp.example.com",
        "scopes": "openid profile",
    }

    def test_dropping_openid_from_an_oidc_provider_is_refused(self, mock_db):
        with pytest.raises(core_exceptions.InvalidInputError, match="openid"):
            self._update(mock_db, self.OIDC, scopes="profile email")
        self.crud.update_identity_provider.assert_not_called()
        mock_db.commit.assert_not_called()

    def test_clearing_the_issuer_of_an_oidc_provider_is_refused(self, mock_db):
        with pytest.raises(core_exceptions.InvalidInputError, match="issuer_url"):
            self._update(mock_db, self.OIDC, issuer_url=None)
        self.crud.update_identity_provider.assert_not_called()

    def test_switching_an_oauth2_provider_to_oidc_is_checked_against_the_stored_values(self, mock_db):
        stored = {"provider_type": "oauth2", "issuer_url": None, "scopes": "openid"}
        with pytest.raises(core_exceptions.InvalidInputError, match="issuer_url"):
            self._update(mock_db, stored, provider_type="oidc")
        self.crud.update_identity_provider.assert_not_called()

    def test_a_scopes_only_change_passes_when_the_stored_issuer_satisfies_the_rule(self, mock_db):
        self._update(mock_db, self.OIDC, scopes="openid email")
        self.crud.update_identity_provider.assert_called_once()

    def test_an_oauth2_provider_may_drop_openid_and_the_issuer(self, mock_db):
        stored = {"provider_type": "oauth2", "issuer_url": "https://idp.example.com", "scopes": "openid"}
        self._update(mock_db, stored, scopes="read", issuer_url=None)
        self.crud.update_identity_provider.assert_called_once()

    def test_a_stored_row_that_breaks_the_rule_can_be_renamed(self, mock_db):
        stored = {"provider_type": "oidc", "issuer_url": None, "scopes": "profile"}
        self._update(mock_db, stored, name="Renamed", enabled=False)
        self.crud.update_identity_provider.assert_called_once()

    def test_a_stored_row_that_breaks_the_rule_can_be_toggled_with_the_whole_record_re_sent(self, mock_db):
        stored = {"provider_type": "oidc", "issuer_url": None, "scopes": "profile"}
        self._update(mock_db, stored, enabled=False, **stored)
        self.crud.update_identity_provider.assert_called_once()

    def test_a_stored_row_that_breaks_the_rule_is_still_checked_when_one_field_changes(self, mock_db):
        stored = {"provider_type": "oidc", "issuer_url": None, "scopes": "profile"}
        with pytest.raises(core_exceptions.InvalidInputError, match="issuer_url"):
            self._update(mock_db, stored, **{**stored, "scopes": "openid"})
        self.crud.update_identity_provider.assert_not_called()

    def test_a_stored_row_that_breaks_the_rule_can_be_repaired_in_one_request(self, mock_db):
        stored = {"provider_type": "oidc", "issuer_url": None, "scopes": "profile"}
        self._update(mock_db, stored, issuer_url="https://idp.example.com", scopes="openid profile")
        self.crud.update_identity_provider.assert_called_once()


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
            provider_service.update_identity_provider(3, data, STEP_UP, VERIFIER, oidc, mock_db, if_match='"1"')
        assert order.mock_calls == [call.commit(), call.forget(3)]

    def test_update_that_fails_leaves_the_cache_alone(self, mock_db):
        oidc = MagicMock()
        data = idp_schema.IdentityProviderUpdate(name="Renamed", slug="pocket")
        with patch.object(provider_service, "idp_crud") as crud:
            crud.get_identity_provider.return_value = None
            with pytest.raises(core_exceptions.NotFoundError):
                provider_service.update_identity_provider(3, data, STEP_UP, VERIFIER, oidc, mock_db, if_match='"1"')
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
            provider_service.delete_identity_provider(3, STEP_UP, VERIFIER, MagicMock(), oidc, mock_db, if_match='"1"')
        assert order.mock_calls == [call.commit(), call.forget(3)]


class TestDeleteStepUp:
    """Deleting a provider needs the administrator's step-up, verified before anything is read or written."""

    def test_a_refused_step_up_deletes_nothing(self, mock_db):
        verifier = MagicMock(side_effect=core_exceptions.StepUpFailedError())
        with (
            patch.object(provider_service, "idp_crud") as crud,
            pytest.raises(core_exceptions.StepUpFailedError),
        ):
            provider_service.delete_identity_provider(
                3, STEP_UP, verifier, MagicMock(), MagicMock(), mock_db, if_match='"1"'
            )

        crud.get_identity_provider.assert_not_called()
        crud.delete_identity_provider.assert_not_called()
        mock_db.commit.assert_not_called()

    def test_the_step_up_authorises_the_delete_action(self, mock_db):
        verifier = MagicMock()
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
            provider_service.delete_identity_provider(
                3, STEP_UP, verifier, MagicMock(), MagicMock(), mock_db, if_match='"1"'
            )

        verifier.assert_called_once_with(STEP_UP, idp_constants.StepUpAction.ADMIN_IDP_DELETE)


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


class TestIssuerBinding:
    """A provider's issuer is unique and cannot change while users are linked to it."""

    @staticmethod
    def _update(mock_db, issuer_url, *, current_issuer, links, other=None):
        data = idp_schema.IdentityProviderUpdate(name="Pocket", slug="pocket", issuer_url=issuer_url)
        resolve, allowlist = _network(PUBLIC)
        with (
            resolve,
            allowlist,
            patch.object(provider_service, "idp_crud") as crud,
            patch.object(
                provider_service.identity_provider_links_integration,
                "check_user_identity_providers_by_idp_id",
                return_value=links,
            ),
            patch.object(provider_service.identity_provider_serializers, "to_read_schema"),
        ):
            crud.get_identity_provider.return_value = MagicMock(slug="pocket", issuer_url=current_issuer)
            crud.get_identity_provider_by_issuer.return_value = other
            crud.update_identity_provider.return_value = MagicMock()
            try:
                provider_service.update_identity_provider(
                    3, data, STEP_UP, VERIFIER, MagicMock(), mock_db, if_match='"1"'
                )
            finally:
                TestIssuerBinding.crud = crud

    def test_update_refuses_a_new_issuer_while_users_are_linked(self, mock_db):
        with pytest.raises(core_exceptions.IssuerLockedError) as exc:
            self._update(mock_db, "https://b.example.com", current_issuer="https://a.example.com", links=True)
        assert exc.value.status_code == 409
        assert exc.value.code == "issuer-locked"
        assert exc.value.detail == "The issuer cannot change while users are linked to this provider"
        self.crud.update_identity_provider.assert_not_called()
        mock_db.commit.assert_not_called()

    @pytest.mark.parametrize(
        ("current", "new"),
        [(None, "https://b.example.com"), ("https://a.example.com", None), ("https://a.example.com", "")],
    )
    def test_update_refuses_setting_or_clearing_the_issuer_while_users_are_linked(self, mock_db, current, new):
        with pytest.raises(core_exceptions.IssuerLockedError):
            self._update(mock_db, new, current_issuer=current, links=True)

    @pytest.mark.parametrize(
        ("current", "new"),
        [
            ("https://a.example.com", "https://a.example.com/"),
            ("https://a.example.com/", "https://a.example.com"),
            ("https://a.example.com", "https://a.example.com"),
        ],
    )
    def test_update_allows_a_trailing_slash_change_while_users_are_linked(self, mock_db, current, new):
        self._update(mock_db, new, current_issuer=current, links=True)
        self.crud.update_identity_provider.assert_called_once()

    def test_update_allows_a_new_issuer_without_links(self, mock_db):
        self._update(mock_db, "https://b.example.com", current_issuer="https://a.example.com", links=False)
        self.crud.get_identity_provider_by_issuer.assert_called_once_with(
            "https://b.example.com", mock_db, exclude_id=3
        )
        self.crud.update_identity_provider.assert_called_once()

    def test_update_refuses_an_issuer_another_provider_uses(self, mock_db):
        with pytest.raises(core_exceptions.IssuerInUseError) as exc:
            self._update(mock_db, "https://b.example.com", current_issuer=None, links=False, other=MagicMock())
        assert exc.value.code == "issuer-in-use"
        assert exc.value.detail == "Another identity provider already uses this issuer"
        self.crud.update_identity_provider.assert_not_called()

    def test_update_to_a_null_issuer_is_never_a_conflict(self, mock_db):
        self._update(mock_db, None, current_issuer="https://a.example.com", links=False)
        self.crud.get_identity_provider_by_issuer.assert_not_called()
        self.crud.update_identity_provider.assert_called_once()

    def test_create_refuses_an_issuer_another_provider_uses(self, mock_db):
        resolve, allowlist = _network(PUBLIC)
        with (
            resolve,
            allowlist,
            patch.object(provider_service, "idp_crud") as crud,
            pytest.raises(core_exceptions.IssuerInUseError) as exc,
        ):
            crud.get_identity_provider_by_slug.return_value = None
            crud.get_identity_provider_by_issuer.return_value = MagicMock()
            provider_service.create_identity_provider(
                _create_data(issuer_url="https://a.example.com"), STEP_UP, VERIFIER, mock_db
            )
        assert exc.value.code == "issuer-in-use"
        assert exc.value.detail == "Another identity provider already uses this issuer"
        crud.create_identity_provider.assert_not_called()

    def test_create_without_an_issuer_skips_the_lookup(self, mock_db):
        with (
            patch.object(provider_service, "idp_crud") as crud,
            patch.object(provider_service.identity_provider_serializers, "to_read_schema"),
        ):
            crud.get_identity_provider_by_slug.return_value = None
            crud.create_identity_provider.return_value = MagicMock(id=3, provider_type="oidc")
            provider_service.create_identity_provider(
                _create_data(provider_type="oauth2", issuer_url=None), STEP_UP, VERIFIER, mock_db
            )
        crud.get_identity_provider_by_issuer.assert_not_called()
        crud.create_identity_provider.assert_called_once()

    def test_step_up_is_verified_before_the_issuer_checks(self, mock_db):
        verifier = MagicMock(side_effect=core_exceptions.StepUpFailedError("no"))
        data = idp_schema.IdentityProviderUpdate(name="Pocket", slug="pocket", issuer_url="https://b.example.com")
        with patch.object(provider_service, "idp_crud") as crud, pytest.raises(core_exceptions.StepUpFailedError):
            provider_service.update_identity_provider(3, data, STEP_UP, verifier, MagicMock(), mock_db, if_match='"1"')
        crud.get_identity_provider_by_issuer.assert_not_called()


class TestGetIdentityProviderByIssuer:
    """The issuer lookup is exact apart from trailing slashes and can leave a row out."""

    @staticmethod
    def _seed(db):
        for slug, issuer in (("a", "https://a.example.com/"), ("b", None)):
            db.add(
                idp_models.IdentityProvider(name=slug, slug=slug, client_id="c", client_secret="s", issuer_url=issuer)
            )
        db.flush()

    @pytest.mark.parametrize("lookup", ["https://a.example.com", "https://a.example.com/", "https://a.example.com//"])
    def test_matches_with_or_without_a_trailing_slash(self, lookup):
        db = create_sqlite_session()
        try:
            self._seed(db)
            assert provider_service.idp_crud.get_identity_provider_by_issuer(lookup, db) is not None
        finally:
            db.close()

    def test_does_not_match_another_issuer_or_the_excluded_row(self):
        db = create_sqlite_session()
        try:
            self._seed(db)
            crud = provider_service.idp_crud
            assert crud.get_identity_provider_by_issuer("https://b.example.com", db) is None
            row = crud.get_identity_provider_by_issuer("https://a.example.com", db)
            assert crud.get_identity_provider_by_issuer("https://a.example.com", db, exclude_id=row.id) is None
        finally:
            db.close()
