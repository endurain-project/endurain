"""Tests for the identity-provider token refresh event."""

from unittest.mock import MagicMock, patch

import jasil.publisher as platform_publisher
import pytest
from jasil.events import Event, new_event

import modules.auth.identity_providers.event_publishers as idp_event_publishers
import modules.auth.identity_providers.events as idp_events
import modules.auth.identity_providers.subscriber_registry as idp_subscriber_registry
import modules.auth.identity_providers.subscribers as idp_subscribers

_MODULE = "modules.auth.identity_providers.subscribers"


def _event(user_id: int = 7) -> Event:
    return new_event(idp_events.IDP_TOKEN_REFRESH_REQUESTED, {"user_id": user_id}, source="test")


class TestPublisher:
    def test_the_event_is_staged_in_the_callers_transaction_with_the_user_id_only(self, mock_db):
        with patch.object(platform_publisher, "publish_on_commit") as publish:
            idp_event_publishers.publish_idp_token_refresh_requested(7, mock_db)

        assert publish.call_args.args[0] == idp_events.IDP_TOKEN_REFRESH_REQUESTED
        assert publish.call_args.args[1] == {"user_id": 7}
        assert publish.call_args.kwargs["db"] is mock_db


class TestSubscriber:
    def test_the_handler_refreshes_the_users_tokens(self):
        service = MagicMock()
        with (
            patch(f"{_MODULE}.idp_token_service.IdpTokenService", return_value=service),
            patch(f"{_MODULE}.idp_oidc_client.OidcClientService"),
            patch(f"{_MODULE}.platform_runtime.get_state") as get_state,
            patch(f"{_MODULE}.idp_refresh_claim_store.IdpRefreshClaimStore") as claim_store,
        ):
            idp_subscribers.refresh_idp_tokens_for_event(_event(7))

        claim_store.assert_called_once_with(get_state.return_value)
        service.refresh_idp_tokens.assert_called_once_with(7, claim_store.return_value)

    def test_a_failure_reaches_the_durable_runner_but_not_the_bus(self):
        service = MagicMock()
        service.refresh_idp_tokens.side_effect = RuntimeError("boom")
        with (
            patch(f"{_MODULE}.idp_token_service.IdpTokenService", return_value=service),
            patch(f"{_MODULE}.idp_oidc_client.OidcClientService"),
            patch(f"{_MODULE}.platform_runtime.get_state"),
        ):
            with pytest.raises(RuntimeError):
                idp_subscribers.refresh_idp_tokens_for_event(_event())
            idp_subscribers.on_idp_token_refresh_requested(_event())  # best effort: must not raise

    def test_the_handler_is_registered_on_the_bus_and_durably(self):
        events = MagicMock()
        registry = MagicMock()

        idp_subscriber_registry.register_bus_subscribers(events)
        idp_subscriber_registry.register_durable_handlers(registry)

        events.subscribe.assert_called_once_with(
            idp_events.IDP_TOKEN_REFRESH_REQUESTED, idp_subscribers.on_idp_token_refresh_requested
        )
        registry.register.assert_called_once_with(
            idp_events.IDP_TOKEN_REFRESH_REQUESTED,
            idp_subscribers.IDP_TOKEN_REFRESH_SUBSCRIBER_ID,
            idp_subscribers.refresh_idp_tokens_for_event,
        )
