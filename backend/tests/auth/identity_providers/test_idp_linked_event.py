"""Tests for the identity-provider linked event and its publisher."""

from unittest.mock import patch

import jasil.publisher as platform_publisher

import modules.auth.identity_providers.event_publishers as idp_event_publishers
import modules.auth.identity_providers.events as idp_events


class TestIdpLinkedPayload:
    def test_carries_ids_only(self):
        payload = idp_events.IdpLinkedPayload(user_id=7, idp_id=3)

        assert payload.model_dump() == {"user_id": 7, "idp_id": 3}
        assert payload.SCHEMA_VERSION == 1


class TestPublishIdpLinked:
    def test_the_event_is_staged_in_the_callers_transaction_with_ids_only(self, mock_db):
        with patch.object(platform_publisher, "publish_on_commit") as publish:
            idp_event_publishers.publish_idp_linked(7, 3, mock_db)

        assert publish.call_args.args[0] == idp_events.IDP_LINKED == "auth.idp_linked"
        assert publish.call_args.args[1] == {"user_id": 7, "idp_id": 3}
        assert publish.call_args.kwargs["db"] is mock_db
        assert publish.call_args.kwargs["schema_version"] == 1
