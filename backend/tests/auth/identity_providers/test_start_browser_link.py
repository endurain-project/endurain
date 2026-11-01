"""Tests for staging a browser identity-provider link flow and building its provider URL."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import core.hashing as core_hashing
import modules.auth.identity_providers.contracts as identity_provider_contracts
import modules.auth.oauth_state.constants as oauth_state_constants
from modules.auth.identity_providers import authorization_service, integration_service

_UNSET = object()


def _idp(enabled: bool = True) -> identity_provider_contracts.IdentityProviderState:
    now = datetime.now(UTC)
    return identity_provider_contracts.IdentityProviderState(
        id=1,
        name="Test IdP",
        slug="test",
        provider_type="oidc",
        enabled=enabled,
        client_id=None,
        client_secret=None,
        issuer_url=None,
        authorization_endpoint="https://idp.example.com/auth",
        token_endpoint=None,
        userinfo_endpoint=None,
        jwks_uri=None,
        scopes=None,
        icon=None,
        icon_uploaded=False,
        auto_create_users=False,
        sync_user_info=False,
        user_mapping=None,
        created_at=now,
        updated_at=now,
        version=1,
    )


def _stage(*, redirect=None, provider=_UNSET, claim=None):
    if provider is _UNSET:
        provider = _idp()
    claim = claim or MagicMock(return_value=7)
    db = MagicMock()
    service = authorization_service.AuthorizationService(MagicMock(), "https://app.example")
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
        staged = integration_service.stage_browser_link("token", 1, redirect, "10.0.0.1", claim, db)
    return staged, claim, service, create_state


def test_stage_browser_link_stages_a_link_state_for_the_claimed_user():
    staged, claim, _, create_state = _stage()

    assert staged.purpose == oauth_state_constants.OAuthStatePurpose.LINK
    assert staged.state_id == "state"
    assert staged.nonce == "nonce"
    claim.assert_called_once_with(link_token="token", idp_id=1, client_ip="10.0.0.1")
    assert create_state.call_args.kwargs["user_id"] == 7
    assert create_state.call_args.kwargs["purpose"] == oauth_state_constants.OAuthStatePurpose.LINK


def test_authorization_url_is_built_from_the_staged_flow_without_the_database():
    staged, _, service, _ = _stage()

    with (
        patch.object(
            integration_service.identity_providers_authorization, "AuthorizationService", return_value=service
        ),
        patch.object(integration_service, "_oidc_client"),
        patch.object(service, "_build_authorization_url", return_value="https://idp.example.com/auth?x=1") as build,
    ):
        url = integration_service.authorization_url(staged)

    assert url == "https://idp.example.com/auth?x=1"
    build.assert_called_once_with(staged.idp, "state", "nonce", staged.idp_code_verifier, {})


def test_the_state_stores_only_a_digest_of_a_fresh_browser_binding():
    """The browser keeps the binding; the row keeps its digest, so the row alone cannot reproduce it."""
    first, _, _, create_state = _stage()
    second, _, _, _ = _stage()

    assert len(first.browser_binding) >= 43
    assert first.browser_binding != second.browser_binding
    assert create_state.call_args.kwargs["browser_binding_hash"] == core_hashing.sha256_hex(first.browser_binding)


def test_a_link_state_keeps_a_fresh_pkce_verifier_for_the_provider():
    _, _, _, first = _stage()
    _, _, _, second = _stage()

    verifier = first.call_args.kwargs["idp_code_verifier"]
    assert 43 <= len(verifier) <= 128
    assert verifier != second.call_args.kwargs["idp_code_verifier"]


def test_stage_browser_link_preserves_redirect_and_client_type():
    _, _, _, create_state = _stage(redirect="/settings/security")
    assert create_state.call_args.kwargs["redirect_path"] == "/settings/security"
    assert create_state.call_args.kwargs["client_type"] == "web"


def test_bad_redirect_is_rejected_before_token_claim():
    claim = MagicMock()
    with pytest.raises(core_exceptions.DomainError) as exc:
        _stage(redirect="https://evil.example.com", claim=claim)
    assert exc.value.status_code == 400
    claim.assert_not_called()


def test_missing_or_disabled_provider_is_not_found():
    for provider in (None, _idp(enabled=False)):
        with pytest.raises(core_exceptions.DomainError) as exc:
            _stage(provider=provider)
        assert getattr(exc.value, "status_code", None) == 404
