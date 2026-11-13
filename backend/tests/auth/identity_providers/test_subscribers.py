"""Tests for the identity-provider token refresh and revocation events."""

import uuid
from unittest.mock import MagicMock, patch

import jasil.publisher as platform_publisher
import pytest
from jasil.events import Event, new_event

import modules.auth.identity_providers.event_publishers as idp_event_publishers
import modules.auth.identity_providers.events as idp_events
import modules.auth.identity_providers.scheduled_jobs as idp_scheduled_jobs
import modules.auth.identity_providers.subscriber_registry as idp_subscriber_registry
import modules.auth.identity_providers.subscribers as idp_subscribers
import modules.auth.sessions.events as sessions_events
from tests._helpers.auth import MOCK_USER_ID

_MODULE = "modules.auth.identity_providers.subscribers"


def _event(user_id: uuid.UUID = MOCK_USER_ID, session_id: str | None = "session-1") -> Event:
    return new_event(
        idp_events.IDP_TOKEN_REFRESH_REQUESTED, {"user_id": user_id, "session_id": session_id}, source="test"
    )


def _revoked_event(user_id: uuid.UUID = MOCK_USER_ID) -> Event:
    return new_event(sessions_events.SESSIONS_REVOKED, {"user_id": user_id, "session_id": "session-1"}, source="test")


class TestPublisher:
    def test_the_event_is_staged_in_the_callers_transaction_with_the_ids_only(self, mock_db):
        with patch.object(platform_publisher, "publish_on_commit") as publish:
            idp_event_publishers.publish_idp_token_refresh_requested(MOCK_USER_ID, "session-1", mock_db)

        assert publish.call_args.args[0] == idp_events.IDP_TOKEN_REFRESH_REQUESTED
        assert publish.call_args.args[1] == {"user_id": str(MOCK_USER_ID), "session_id": "session-1"}
        assert publish.call_args.kwargs["db"] is mock_db


class TestSubscriber:
    def test_the_handler_refreshes_the_sessions_token(self):
        service = MagicMock()
        with (
            patch(f"{_MODULE}.idp_token_service.IdpTokenService", return_value=service),
            patch(f"{_MODULE}.idp_oidc_client.OidcClientService"),
            patch(f"{_MODULE}.platform_runtime.get_state") as get_state,
            patch(f"{_MODULE}.idp_refresh_claim_store.IdpRefreshClaimStore") as claim_store,
        ):
            idp_subscribers.refresh_idp_tokens_for_event(_event(MOCK_USER_ID))

        claim_store.assert_called_once_with(get_state.return_value)
        service.refresh_idp_tokens.assert_called_once_with(MOCK_USER_ID, "session-1", claim_store.return_value)

    def test_an_event_queued_before_tokens_were_per_session_is_dropped(self):
        with (
            patch(f"{_MODULE}.idp_token_service.IdpTokenService") as service,
            patch(f"{_MODULE}.idp_oidc_client.OidcClientService"),
            patch(f"{_MODULE}.platform_runtime.get_state"),
        ):
            idp_subscribers.refresh_idp_tokens_for_event(_event(session_id=None))

        service.return_value.refresh_idp_tokens.assert_not_called()

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

        assert [call.args for call in events.subscribe.call_args_list] == [
            (idp_events.IDP_TOKEN_REFRESH_REQUESTED, idp_subscribers.on_idp_token_refresh_requested),
            (sessions_events.SESSIONS_REVOKED, idp_subscribers.on_sessions_revoked_revoke_idp_tokens),
        ]
        assert [call.args for call in registry.register.call_args_list] == [
            (
                idp_events.IDP_TOKEN_REFRESH_REQUESTED,
                idp_subscribers.IDP_TOKEN_REFRESH_SUBSCRIBER_ID,
                idp_subscribers.refresh_idp_tokens_for_event,
            ),
            (
                sessions_events.SESSIONS_REVOKED,
                idp_subscribers.IDP_TOKEN_REVOKE_SUBSCRIBER_ID,
                idp_subscribers.revoke_session_tokens_for_event,
            ),
        ]


class TestRevocationSubscriber:
    def test_the_handler_revokes_the_events_users_ended_sessions(self):
        with (
            patch(f"{_MODULE}.idp_token_revocation_service.IdpTokenRevocationService") as service,
            patch(f"{_MODULE}.idp_oidc_client.OidcClientService") as oidc,
            patch(f"{_MODULE}.platform_runtime.get_state"),
        ):
            idp_subscribers.revoke_session_tokens_for_event(_revoked_event(MOCK_USER_ID))

        service.assert_called_once_with(oidc.return_value)
        service.return_value.revoke_ended_sessions.assert_called_once_with(user_id=MOCK_USER_ID)

    def test_a_failure_reaches_the_durable_runner_but_not_the_bus(self):
        with (
            patch(f"{_MODULE}.idp_token_revocation_service.IdpTokenRevocationService") as service,
            patch(f"{_MODULE}.idp_oidc_client.OidcClientService"),
            patch(f"{_MODULE}.platform_runtime.get_state"),
        ):
            service.return_value.revoke_ended_sessions.side_effect = RuntimeError("boom")
            with pytest.raises(RuntimeError):
                idp_subscribers.revoke_session_tokens_for_event(_revoked_event())
            idp_subscribers.on_sessions_revoked_revoke_idp_tokens(_revoked_event())  # best effort: must not raise

    def test_the_net_is_the_scheduled_sweep(self):
        nets = {net.subscriber_id: net for net in idp_subscriber_registry.DURABLE_SUBSCRIBER_NETS}

        net = nets[idp_subscribers.IDP_TOKEN_REVOKE_SUBSCRIBER_ID]
        assert net.backfill is idp_scheduled_jobs.revoke_ended_session_tokens
