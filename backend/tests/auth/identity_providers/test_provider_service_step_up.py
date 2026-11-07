"""An administrator's step-up comes before anything is checked or written when a provider is created or edited."""

from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.auth.identity_providers.constants as idp_constants
import modules.auth.identity_providers.provider_service as provider_service
import modules.auth.identity_providers.schema as idp_schema
import modules.auth.schema as auth_schema

_STEP_UP = auth_schema.StepUpVerification(current_password="admin-password")


def _create_data() -> idp_schema.IdentityProviderCreate:
    return idp_schema.IdentityProviderCreate(name="Pocket", slug="pocket", client_id="cid", client_secret="secret")


def _refusing() -> MagicMock:
    return MagicMock(side_effect=core_exceptions.StepUpFailedError())


class TestCreate:
    def test_the_step_up_is_verified_for_the_create_action_before_anything_else(self, mock_db):
        verifier = MagicMock()
        order = MagicMock()
        order.attach_mock(verifier, "step_up")
        with (
            patch.object(provider_service, "_reject_unsafe_urls") as urls,
            patch.object(provider_service, "idp_crud") as crud,
            patch.object(provider_service.identity_provider_serializers, "to_read_schema"),
        ):
            order.attach_mock(urls, "urls")
            order.attach_mock(crud.create_identity_provider, "insert")
            crud.get_identity_provider_by_slug.return_value = None
            crud.create_identity_provider.return_value = MagicMock(id=3, provider_type="oidc")
            provider_service.create_identity_provider(_create_data(), _STEP_UP, verifier, mock_db)

        assert [call[0] for call in order.mock_calls][:2] == ["step_up", "urls"]
        verifier.assert_called_once_with(_STEP_UP, idp_constants.StepUpAction.ADMIN_IDP_CREATE)

    def test_a_refused_step_up_validates_and_writes_nothing(self, mock_db):
        with (
            patch.object(provider_service, "_reject_unsafe_urls") as urls,
            patch.object(provider_service, "idp_crud") as crud,
            pytest.raises(core_exceptions.StepUpFailedError),
        ):
            provider_service.create_identity_provider(_create_data(), _STEP_UP, _refusing(), mock_db)

        urls.assert_not_called()
        crud.get_identity_provider_by_slug.assert_not_called()
        crud.create_identity_provider.assert_not_called()
        mock_db.commit.assert_not_called()


class TestUpdate:
    def _data(self) -> idp_schema.IdentityProviderUpdate:
        return idp_schema.IdentityProviderUpdate(name="Renamed", slug="pocket")

    def test_the_step_up_is_verified_for_the_edit_action_before_anything_else(self, mock_db):
        verifier = MagicMock()
        order = MagicMock()
        order.attach_mock(verifier, "step_up")
        with (
            patch.object(provider_service, "_reject_unsafe_urls") as urls,
            patch.object(provider_service, "idp_crud") as crud,
            patch.object(provider_service.identity_provider_serializers, "to_read_schema"),
        ):
            order.attach_mock(urls, "urls")
            crud.get_identity_provider.return_value = MagicMock(slug="pocket")
            crud.identity_provider_exists.return_value = True
            crud.update_identity_provider.return_value = MagicMock()
            provider_service.update_identity_provider(
                3, self._data(), _STEP_UP, verifier, MagicMock(), mock_db, if_match='"1"'
            )

        assert [call[0] for call in order.mock_calls][:2] == ["step_up", "urls"]
        verifier.assert_called_once_with(_STEP_UP, idp_constants.StepUpAction.ADMIN_IDP_EDIT)

    def test_a_refused_step_up_validates_and_writes_nothing(self, mock_db):
        oidc = MagicMock()
        with (
            patch.object(provider_service, "_reject_unsafe_urls") as urls,
            patch.object(provider_service, "idp_crud") as crud,
            pytest.raises(core_exceptions.StepUpFailedError),
        ):
            provider_service.update_identity_provider(
                3, self._data(), _STEP_UP, _refusing(), oidc, mock_db, if_match='"1"'
            )

        urls.assert_not_called()
        crud.get_identity_provider.assert_not_called()
        crud.update_identity_provider.assert_not_called()
        mock_db.commit.assert_not_called()
        oidc.forget_discovery.assert_not_called()
