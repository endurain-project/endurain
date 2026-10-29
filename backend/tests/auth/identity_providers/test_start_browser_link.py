"""Tests for starting a browser identity-provider link flow."""

from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import core.hashing as core_hashing
from modules.auth.identity_providers import authorization_service, integration_service

_UNSET = object()


def _start(*, redirect=None, provider=_UNSET, claim=None):
    if provider is _UNSET:
        provider = MagicMock(enabled=True, id=1, name="Test IdP")
    claim = claim or MagicMock(return_value=7)
    db = MagicMock()
    service = authorization_service.AuthorizationService(MagicMock(), "https://app.example")
    service.initiate_link = MagicMock(return_value="https://idp.example.com/auth")
    with (
        patch.object(authorization_service.idp_crud, "get_identity_provider", return_value=provider),
        patch.object(
            integration_service.identity_providers_authorization, "AuthorizationService", return_value=service
        ),
        patch.object(integration_service, "_oidc_client"),
        patch.object(
            authorization_service.oauth_state_integration,
            "create_state_id_and_nonce",
            return_value=("state", "nonce"),
        ),
        patch.object(authorization_service.oauth_state_integration, "create_oauth_state") as create_state,
    ):
        url = integration_service.start_browser_link("token", 1, redirect, "10.0.0.1", claim, db)
    return url, claim, service, create_state


def test_start_browser_link_returns_authorization_url():
    start, claim, service, create_state = _start()
    assert start.authorization_url == "https://idp.example.com/auth"
    claim.assert_called_once_with(link_token="token", idp_id=1, client_ip="10.0.0.1")
    assert create_state.call_args.kwargs["user_id"] == 7
    service.initiate_link.assert_called_once()


def test_the_state_stores_only_a_digest_of_a_fresh_browser_binding():
    """The browser keeps the binding; the row keeps its digest, so the row alone cannot reproduce it."""
    first, _, _, create_state = _start()
    second, _, _, _ = _start()

    assert len(first.browser_binding) >= 43
    assert first.browser_binding != second.browser_binding
    assert create_state.call_args.kwargs["browser_binding_hash"] == core_hashing.sha256_hex(first.browser_binding)


def test_a_link_state_keeps_a_fresh_pkce_verifier_for_the_provider():
    _, _, _, first = _start()
    _, _, _, second = _start()

    verifier = first.call_args.kwargs["idp_code_verifier"]
    assert 43 <= len(verifier) <= 128
    assert verifier != second.call_args.kwargs["idp_code_verifier"]


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
