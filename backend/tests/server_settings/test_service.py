"""Tests for the server-settings write path.

The service is where the tile-URL network policy is enforced: the schema is also
what deserializes settings on every *read*, so a validator there would put a DNS
lookup on the read path of the whole app.
"""

from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.server_settings.service as server_settings_service


def _attributes(**overrides):
    attrs = MagicMock()
    attrs.model_dump.return_value = overrides.pop("changed", {"tileserver_url": True})
    attrs.tileserver_url = overrides.pop("tileserver_url", "https://tiles.example.com/{z}/{x}/{y}.png")
    return attrs


class TestTileServerUrlIsCheckedOnWrite:
    def test_a_url_targeting_a_non_public_address_is_refused(self):
        """The renderer refuses it too, but only later, in a background job.

        By then the admin has seen no error and the bad value is already stored.
        """
        db = MagicMock()
        with (
            patch.object(
                server_settings_service.core_network,
                "url_rejection_reason",
                return_value="resolves to a non-public address",
            ),
            patch.object(server_settings_service.server_settings_crud, "edit_server_settings") as write,
            pytest.raises(core_exceptions.InvalidInputError),
        ):
            server_settings_service.edit_server_settings(_attributes(), db)

        write.assert_not_called()
        db.commit.assert_not_called()

    def test_the_placeholders_are_filled_before_the_check(self):
        """``{z}/{x}/{y}`` is not a parseable URL; the host is what matters."""
        db = MagicMock()
        with (
            patch.object(server_settings_service.core_network, "url_rejection_reason", return_value=None) as check,
            patch.object(server_settings_service.server_settings_crud, "edit_server_settings"),
            patch.object(server_settings_service.server_settings_publishers, "publish_tile_settings_changed"),
        ):
            server_settings_service.edit_server_settings(_attributes(), db)

        assert check.call_args.args[0] == "https://tiles.example.com/0/0/0.png"

    def test_an_untouched_tile_url_is_not_resolved(self):
        """A settings write that does not change it must not pay for a lookup."""
        db = MagicMock()
        with (
            patch.object(server_settings_service.core_network, "url_rejection_reason") as check,
            patch.object(server_settings_service.server_settings_crud, "edit_server_settings"),
        ):
            server_settings_service.edit_server_settings(_attributes(changed={"currency": "euro"}), db)

        check.assert_not_called()
        db.commit.assert_called_once()

    def test_an_unfillable_placeholder_is_a_400_not_a_background_500(self):
        """The renderer resolves the same template before every tile fetch."""
        db = MagicMock()
        with (
            patch.object(server_settings_service.server_settings_crud, "edit_server_settings") as write,
            pytest.raises(core_exceptions.InvalidInputError),
        ):
            server_settings_service.edit_server_settings(
                _attributes(tileserver_url="https://tiles.example.com/{s}/{z}/{x}/{y}.png"), db
            )

        write.assert_not_called()
