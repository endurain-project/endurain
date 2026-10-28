"""Tests for starting a browser identity-provider link flow."""

from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
from modules.auth.identity_providers import integration_service
from modules.auth.identity_providers import service as idp_service

_UNSET = object()


def _start(*, redirect=None, provider=_UNSET, claim=None):
    if provider is _UNSET:
        provider = MagicMock(enabled=True, id=1, name="Test IdP")
    claim = claim or MagicMock(return_value=7)
    db = MagicMock()
    request = MagicMock()
    service = idp_service.IdentityProviderService(MagicMock(), "https://app.example", "test")
    service.initiate_link = MagicMock(return_value="https://idp.example.com/auth")
    with (
        patch.object(integration_service.core_network, "get_ip_address", return_value="10.0.0.1"),
        patch.object(idp_service.idp_crud, "get_identity_provider", return_value=provider),
        patch.object(integration_service, "_service", return_value=service),
        patch.object(
            idp_service.oauth_state_integration,
            "create_state_id_and_nonce",
            return_value=("state", "nonce"),
        ),
        patch.object(idp_service.oauth_state_crud, "create_oauth_state") as create_state,
    ):
        url = integration_service.start_browser_link("token", 1, redirect, request, claim, db)
    return url, claim, service, create_state


def test_start_browser_link_returns_authorization_url():
    url, claim, service, create_state = _start()
    assert url == "https://idp.example.com/auth"
    claim.assert_called_once_with(link_token="token", idp_id=1, client_ip="10.0.0.1")
    assert create_state.call_args.kwargs["user_id"] == 7
    service.initiate_link.assert_called_once()


def test_start_browser_link_preserves_redirect_and_client_type():
    _, _, _, create_state = _start(redirect="/settings/security")
    assert create_state.call_args.kwargs["redirect_path"] == "/settings/security"
    assert create_state.call_args.kwargs["client_type"] == "web"


def test_bad_redirect_is_rejected_before_token_claim():
    claim = MagicMock()
    with pytest.raises(core_exceptions.DomainError) as exc:
        _start(redirect="https://evil.example.com", claim=claim)
    assert exc.value.status_code == 400
    claim.assert_not_called()


def test_missing_or_disabled_provider_is_not_found():
    for provider in (None, MagicMock(enabled=False)):
        with pytest.raises(core_exceptions.DomainError) as exc:
            _start(provider=provider)
        assert getattr(exc.value, "status_code", None) == 404
