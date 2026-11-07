"""Tests for uncovered lines in core.network module."""

from unittest.mock import patch

import pytest

import core.exceptions as core_exceptions
import core.network as core_network


class TestIsTrustedPeerEdgeCases:
    """Edge cases for _is_trusted_peer."""

    def test_empty_entry_skipped(self):
        """Empty entry in trusted_proxies is skipped (line 39)."""
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", ["", "10.0.0.0/8"]):
            assert core_network._is_trusted_peer("10.0.0.1") is True

    def test_non_parseable_entry_as_plain_string(self):
        """Non-CIDR entry compared as plain string (lines 44-47)."""
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", ["not-a-cidr"]):
            assert core_network._is_trusted_peer("10.0.0.1") is False


class TestRejectPrivateUrlEdgeCases:
    """Edge cases for reject_private_url."""

    @patch("core.network.urlparse")
    def test_urlparse_raises_value_error(self, mock_urlparse):
        """urlparse ValueError raises 400 (lines 197-198)."""
        mock_urlparse.side_effect = ValueError("Bad URL")
        with pytest.raises(core_exceptions.InvalidInputError) as exc:
            core_network.reject_private_url("http://bad-url")
        assert exc.value.status_code == 400
        assert "Malformed URL" in exc.value.detail
