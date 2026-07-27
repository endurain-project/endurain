"""Tests for core.network module."""

import ipaddress
import socket
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, Request

import core.network as core_network


class TestIsValidHostname:
    """Tests for _is_valid_hostname function."""

    def test_simple_hostname(self):
        assert core_network._is_valid_hostname("caddy") is True

    def test_dotted_hostname(self):
        assert core_network._is_valid_hostname("proxy.internal") is True

    def test_hyphenated_label(self):
        assert core_network._is_valid_hostname("reverse-proxy") is True

    def test_multi_label(self):
        assert core_network._is_valid_hostname("my.proxy.internal") is True

    def test_numeric_label(self):
        # Labels that look like numbers are valid hostnames.
        assert core_network._is_valid_hostname("proxy1") is True

    def test_url_scheme_rejected(self):
        assert core_network._is_valid_hostname("http://caddy") is False

    def test_port_suffix_rejected(self):
        assert core_network._is_valid_hostname("caddy:8080") is False

    def test_leading_hyphen_rejected(self):
        assert core_network._is_valid_hostname("-proxy") is False

    def test_trailing_hyphen_rejected(self):
        assert core_network._is_valid_hostname("proxy-") is False

    def test_empty_string_rejected(self):
        assert core_network._is_valid_hostname("") is False

    def test_too_long_rejected(self):
        long_host = "a" * 254
        assert core_network._is_valid_hostname(long_host) is False


class TestRefreshTrustedProxyHostnames:
    """Tests for refresh_trusted_proxy_hostnames function."""

    def test_returns_empty_when_no_hostnames(self):
        with patch.object(
            core_network.core_config.settings,
            "TRUSTED_PROXIES",
            ["10.0.0.0/8"],
        ):
            result = core_network.refresh_trusted_proxy_hostnames()
            assert result == {}

    def test_skips_refresh_when_cache_fresh(self):
        with (
            patch.object(
                core_network.core_config.settings,
                "TRUSTED_PROXIES",
                ["proxy.internal"],
            ),
            patch.object(
                core_network,
                "_trusted_proxy_hostname_last_refresh",
                100.0,
            ),
            patch("core.network.time.monotonic", return_value=110.0),
            patch("core.network._resolve_hostname") as mock_resolve,
        ):
            result = core_network.refresh_trusted_proxy_hostnames()
            assert result == {}
            mock_resolve.assert_not_called()

    def test_force_bypasses_ttl(self):
        with (
            patch.object(
                core_network.core_config.settings,
                "TRUSTED_PROXIES",
                ["proxy.internal"],
            ),
            patch.object(
                core_network,
                "_trusted_proxy_hostname_last_refresh",
                100.0,
            ),
            patch("core.network.time.monotonic", return_value=110.0),
            patch(
                "core.network._resolve_hostname",
                return_value=["10.0.0.6"],
            ) as mock_resolve,
        ):
            result = core_network.refresh_trusted_proxy_hostnames(force=True)
            assert result == {"proxy.internal": ["10.0.0.6"]}
            mock_resolve.assert_called_once_with("proxy.internal")

    def test_replaces_old_ips_after_refresh(self):
        with (
            patch.object(
                core_network.core_config.settings,
                "TRUSTED_PROXIES",
                ["proxy.internal"],
            ),
            patch.object(
                core_network.core_config.settings,
                "_resolved_trusted_proxy_ips",
                {"10.0.0.5"},
            ),
            patch.object(
                core_network,
                "_trusted_proxy_hostname_last_refresh",
                1.0,
            ),
            patch("core.network.time.monotonic", return_value=100.0),
            patch(
                "core.network._resolve_hostname",
                return_value=["10.0.0.6"],
            ),
        ):
            core_network.refresh_trusted_proxy_hostnames()
            settings = core_network.core_config.settings
            assert settings._resolved_trusted_proxy_ips == {"10.0.0.6"}


class TestResolveHostname:
    """Tests for _resolve_hostname function."""

    def test_resolve_hostname_single_ip(self):
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            # Simulate getaddrinfo return format: (family, type, proto, canonname, sockaddr)
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0)),
            ]
            result = core_network._resolve_hostname("proxy.internal")
            assert result == ["10.0.0.5"]
            mock_getaddrinfo.assert_called_once_with("proxy.internal", None)

    def test_resolve_hostname_multiple_ips(self):
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.6", 0)),
            ]
            result = core_network._resolve_hostname("proxy.internal")
            assert set(result) == {"10.0.0.5", "10.0.0.6"}

    def test_resolve_hostname_deduplicates(self):
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0)),
                (socket.AF_INET, socket.SOCK_DGRAM, 17, "", ("10.0.0.5", 0)),
            ]
            result = core_network._resolve_hostname("proxy.internal")
            assert result == ["10.0.0.5"]

    def test_resolve_hostname_dns_failure(self):
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.side_effect = socket.gaierror("Name resolution failed")
            result = core_network._resolve_hostname("nonexistent.hostname")
            assert result == []

    def test_resolve_hostname_ipv6(self):
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2001:db8::1", 0, 0, 0)),
            ]
            result = core_network._resolve_hostname("ipv6proxy.internal")
            assert result == ["2001:db8::1"]

    def test_resolve_hostname_mixed_ipv4_ipv6(self):
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0)),
                (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("2001:db8::1", 0, 0, 0)),
            ]
            result = core_network._resolve_hostname("proxy.internal")
            assert set(result) == {"10.0.0.5", "2001:db8::1"}


class TestIsTrustedPeer:
    """Tests for _is_trusted_peer function."""

    def test_wildcard_trusts_all(self):
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", ["*"]):
            assert core_network._is_trusted_peer("192.168.1.1") is True
            assert core_network._is_trusted_peer("10.0.0.1") is True

    def test_exact_ip_match(self):
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", ["192.168.1.1"]):
            assert core_network._is_trusted_peer("192.168.1.1") is True

    def test_exact_ip_no_match(self):
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", ["10.0.0.1"]):
            assert core_network._is_trusted_peer("192.168.1.1") is False

    def test_cidr_match(self):
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", ["10.0.0.0/8"]):
            assert core_network._is_trusted_peer("10.0.0.1") is True
            assert core_network._is_trusted_peer("10.255.255.255") is True

    def test_cidr_no_match(self):
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", ["10.0.0.0/8"]):
            assert core_network._is_trusted_peer("192.168.1.1") is False

    def test_empty_trusted_proxies(self):
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", []):
            assert core_network._is_trusted_peer("10.0.0.1") is False

    def test_invalid_peer_ip(self):
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", ["10.0.0.0/8"]):
            assert core_network._is_trusted_peer("not-an-ip") is False

    def test_resolved_hostname_ip_match(self):
        """Test that _is_trusted_peer checks resolved hostname IPs."""
        with (
            patch.object(
                core_network.core_config.settings,
                "TRUSTED_PROXIES",
                ["proxy.internal"],
            ),
            patch.object(
                core_network.core_config.settings,
                "_resolved_trusted_proxy_ips",
                {"10.0.0.5"},
            ),
        ):
            assert core_network._is_trusted_peer("10.0.0.5") is True

    def test_resolved_hostname_ip_no_match(self):
        """Test that unresolved IPs don't match."""
        with (
            patch.object(
                core_network.core_config.settings,
                "TRUSTED_PROXIES",
                ["proxy.internal"],
            ),
            patch.object(
                core_network.core_config.settings,
                "_resolved_trusted_proxy_ips",
                {"10.0.0.5"},
            ),
        ):
            assert core_network._is_trusted_peer("10.0.0.6") is False

    def test_resolved_hostname_multiple_ips(self):
        """Test that multiple resolved IPs are all trusted."""
        with (
            patch.object(
                core_network.core_config.settings,
                "TRUSTED_PROXIES",
                ["proxy.internal"],
            ),
            patch.object(
                core_network.core_config.settings,
                "_resolved_trusted_proxy_ips",
                {"10.0.0.5", "10.0.0.6", "2001:db8::1"},
            ),
        ):
            assert core_network._is_trusted_peer("10.0.0.5") is True
            assert core_network._is_trusted_peer("10.0.0.6") is True
            assert core_network._is_trusted_peer("2001:db8::1") is True


class TestGetIpAddress:
    """Tests for get_ip_address function."""

    def test_no_client_returns_unknown(self):
        request = MagicMock(spec=Request)
        request.client = None
        result = core_network.get_ip_address(request)
        assert result == "unknown"

    def test_untrusted_peer_uses_direct_ip(self):
        request = MagicMock(spec=Request)
        request.client.host = "203.0.113.5"
        request.headers = {"X-Forwarded-For": "1.2.3.4"}
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", ["10.0.0.0/8"]):
            result = core_network.get_ip_address(request)
            assert result == "203.0.113.5"

    def test_trusted_proxy_x_forwarded_for(self):
        request = MagicMock(spec=Request)
        request.client.host = "10.0.0.1"
        request.headers = {"X-Forwarded-For": "1.2.3.4, 10.0.0.1"}
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", ["10.0.0.0/8"]):
            result = core_network.get_ip_address(request)
            assert result == "1.2.3.4"

    def test_trusted_proxy_x_real_ip(self):
        request = MagicMock(spec=Request)
        request.client.host = "10.0.0.1"
        request.headers = {"X-Real-IP": "5.6.7.8"}
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", ["10.0.0.0/8"]):
            result = core_network.get_ip_address(request)
            assert result == "5.6.7.8"

    def test_trusted_proxy_prefers_x_forwarded_for(self):
        request = MagicMock(spec=Request)
        request.client.host = "10.0.0.1"
        request.headers = {"X-Forwarded-For": "1.2.3.4", "X-Real-IP": "5.6.7.8"}
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", ["*"]):
            result = core_network.get_ip_address(request)
            assert result == "1.2.3.4"

    def test_trusted_proxy_no_headers_returns_direct_ip(self):
        request = MagicMock(spec=Request)
        request.client.host = "10.0.0.1"
        request.headers = {}
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", ["10.0.0.0/8"]):
            result = core_network.get_ip_address(request)
            assert result == "10.0.0.1"


class TestIsPrivateOrReserved:
    """Tests for _is_private_or_reserved function."""

    def test_private_ip(self):
        addr = ipaddress.ip_address("10.0.0.1")
        assert core_network._is_private_or_reserved(addr) is True

    def test_loopback(self):
        addr = ipaddress.ip_address("127.0.0.1")
        assert core_network._is_private_or_reserved(addr) is True

    def test_public_ip(self):
        addr = ipaddress.ip_address("8.8.8.8")
        assert core_network._is_private_or_reserved(addr) is False

    def test_link_local(self):
        addr = ipaddress.ip_address("169.254.1.1")
        assert core_network._is_private_or_reserved(addr) is True

    def test_multicast(self):
        addr = ipaddress.ip_address("224.0.0.1")
        assert core_network._is_private_or_reserved(addr) is True

    def test_unspecified(self):
        addr = ipaddress.ip_address("0.0.0.0")  # noqa: S104
        assert core_network._is_private_or_reserved(addr) is True

    def test_ipv6_private(self):
        addr = ipaddress.ip_address("fc00::1")
        assert core_network._is_private_or_reserved(addr) is True

    def test_ipv6_loopback(self):
        addr = ipaddress.ip_address("::1")
        assert core_network._is_private_or_reserved(addr) is True


class TestLoadSsrfAllowlist:
    """Tests for _load_ssrf_allowlist function."""

    def test_hostname_entries(self):
        with patch.object(core_network.core_config.settings, "SSRF_ALLOWED_HOSTS", ["example.com", "test.example.org"]):
            hosts, networks = core_network._load_ssrf_allowlist()
            assert "example.com" in hosts
            assert "test.example.org" in hosts
            assert not networks

    def test_cidr_entries(self):
        with patch.object(core_network.core_config.settings, "SSRF_ALLOWED_HOSTS", ["10.0.0.0/8", "192.168.0.0/16"]):
            hosts, networks = core_network._load_ssrf_allowlist()
            assert not hosts
            assert len(networks) == 2

    def test_mixed_entries(self):
        with patch.object(core_network.core_config.settings, "SSRF_ALLOWED_HOSTS", ["example.com", "10.0.0.0/8"]):
            hosts, networks = core_network._load_ssrf_allowlist()
            assert "example.com" in hosts
            assert len(networks) == 1

    def test_empty_allowlist(self):
        with patch.object(core_network.core_config.settings, "SSRF_ALLOWED_HOSTS", []):
            hosts, networks = core_network._load_ssrf_allowlist()
            assert not hosts
            assert not networks


class TestIsSsrfAllowlisted:
    """Tests for _is_ssrf_allowlisted function."""

    def test_hostname_match(self):
        with patch.object(core_network.core_config.settings, "SSRF_ALLOWED_HOSTS", ["internal.example.com"]):
            assert core_network._is_ssrf_allowlisted("internal.example.com", ipaddress.ip_address("10.0.0.1")) is True

    def test_hostname_case_insensitive(self):
        with patch.object(core_network.core_config.settings, "SSRF_ALLOWED_HOSTS", ["Internal.Example.Com"]):
            assert core_network._is_ssrf_allowlisted("internal.example.com", ipaddress.ip_address("10.0.0.1")) is True

    def test_network_match(self):
        with patch.object(core_network.core_config.settings, "SSRF_ALLOWED_HOSTS", ["10.0.0.0/8"]):
            assert core_network._is_ssrf_allowlisted("anyhost", ipaddress.ip_address("10.10.10.10")) is True

    def test_no_match(self):
        with patch.object(core_network.core_config.settings, "SSRF_ALLOWED_HOSTS", ["example.com"]):
            assert core_network._is_ssrf_allowlisted("other.com", ipaddress.ip_address("10.0.0.1")) is False


class TestRejectPrivateUrl:
    """Tests for reject_private_url function."""

    def test_bad_scheme_raises(self):
        with pytest.raises(HTTPException) as exc:
            core_network.reject_private_url("file:///etc/passwd")
        assert exc.value.status_code == 400
        assert "scheme" in exc.value.detail.lower()

    def test_malformed_url_raises(self):
        with pytest.raises(HTTPException) as exc:
            core_network.reject_private_url(":::not-a-url:::")
        assert exc.value.status_code == 400

    def test_no_hostname_raises(self):
        with pytest.raises(HTTPException) as exc:
            core_network.reject_private_url("http:///path")
        assert exc.value.status_code == 400
        assert "hostname" in exc.value.detail.lower()

    def test_unresolvable_hostname_raises(self):
        with patch("core.network.socket.getaddrinfo") as mock_gai:
            mock_gai.side_effect = socket.gaierror("Name or service not known")
            with pytest.raises(HTTPException) as exc:
                core_network.reject_private_url("http://nonexistent.example.com")
            assert exc.value.status_code == 400
            assert "resolve" in exc.value.detail.lower()

    def test_unparseable_address_raises(self):
        with patch("core.network.socket.getaddrinfo") as mock_gai:
            mock_gai.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("not-an-ip", 0))]
            with pytest.raises(HTTPException) as exc:
                core_network.reject_private_url("http://example.com")
            assert exc.value.status_code == 400
            assert "unparseable" in exc.value.detail.lower()

    def test_private_ip_ssrf_raises(self):
        with patch("core.network.socket.getaddrinfo") as mock_gai:
            mock_gai.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.1", 0))]
            with patch.object(core_network.core_config.settings, "SSRF_ALLOWED_HOSTS", []):
                with pytest.raises(HTTPException) as exc:
                    core_network.reject_private_url("http://internal.example.com")
                assert exc.value.status_code == 400
                assert "non-public" in exc.value.detail.lower()

    def test_private_ip_allowlisted_ok(self):
        with patch("core.network.socket.getaddrinfo") as mock_gai:
            mock_gai.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.1", 0))]
            with patch.object(core_network.core_config.settings, "SSRF_ALLOWED_HOSTS", ["10.0.0.0/8"]):
                core_network.reject_private_url("http://internal.example.com")

    def test_public_ip_success(self):
        with patch("core.network.socket.getaddrinfo") as mock_gai:
            mock_gai.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("8.8.8.8", 0))]
            core_network.reject_private_url("http://google.com")

    def test_allowlisted_private_url_logs(self):
        with (
            patch("core.network.socket.getaddrinfo") as mock_gai,
            patch.object(core_network.core_config.settings, "SSRF_ALLOWED_HOSTS", ["10.0.0.0/8"]),
            patch.object(core_network, "logger") as mock_log,
        ):
            mock_gai.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.1", 0))]
            core_network.reject_private_url("http://internal.example.com", purpose="test")
            mock_log.info.assert_called_once()
            assert "SSRF allowlist hit" in mock_log.info.call_args[0][0]


class TestHostRejectionReason:
    """The host-authority SSRF guard, for config-supplied ``host[:port]`` values.

    Shares its address denylist and allowlist with ``reject_private_url``; the
    difference is that it *returns* a reason so a caller can disable an optional
    feature rather than fail a request.
    """

    def _public(self):
        return patch(
            "core.network.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("8.8.8.8", 0))],
        )

    def _resolving_to(self, ip):
        return patch(
            "core.network.socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, 0))],
        )

    def test_accepts_bare_hosts(self):
        with self._public():
            assert core_network.host_rejection_reason("nominatim.openstreetmap.org") is None
            assert core_network.host_rejection_reason("nominatim.local") is None
            assert core_network.host_rejection_reason("nominatim:8080") is None

    def test_rejects_ssrf_shapes_without_resolving(self):
        # A configured value carrying a scheme/path/credentials would be
        # interpolated into a URL by the caller and redirect the request.
        with patch("core.network.socket.getaddrinfo") as mock_gai:
            for value in (None, "", "http://host", "host/reverse", "user@host", "host name", "host:notaport"):
                assert core_network.host_rejection_reason(value) is not None
            mock_gai.assert_not_called()

    def test_private_ip_is_rejected(self):
        with (
            self._resolving_to("10.0.0.1"),
            patch.object(core_network.core_config.settings, "SSRF_ALLOWED_HOSTS", []),
        ):
            assert "non-public" in core_network.host_rejection_reason("nominatim.internal")

    def test_link_local_metadata_is_rejected(self):
        with (
            self._resolving_to("169.254.169.254"),
            patch.object(core_network.core_config.settings, "SSRF_ALLOWED_HOSTS", []),
        ):
            assert "non-public" in core_network.host_rejection_reason("metadata")

    def test_loopback_is_rejected(self):
        with (
            self._resolving_to("127.0.0.1"),
            patch.object(core_network.core_config.settings, "SSRF_ALLOWED_HOSTS", []),
        ):
            assert "non-public" in core_network.host_rejection_reason("localhost:8080")

    def test_unresolvable_host_is_rejected(self):
        with patch("core.network.socket.getaddrinfo", side_effect=socket.gaierror("nxdomain")):
            assert "resolved" in core_network.host_rejection_reason("does.not.exist")

    def test_rejected_when_any_resolved_address_is_private(self):
        # DNS-rebinding shape: a name answering with both a public and a private
        # address must not be treated as public.
        with (
            patch(
                "core.network.socket.getaddrinfo",
                return_value=[
                    (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("8.8.8.8", 0)),
                    (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.1", 0)),
                ],
            ),
            patch.object(core_network.core_config.settings, "SSRF_ALLOWED_HOSTS", []),
        ):
            assert "non-public" in core_network.host_rejection_reason("mixed.example.com")

    def test_allowlisted_private_host_is_permitted(self):
        # A self-hosted service on a private network is a supported deployment;
        # the operator opts in through SSRF_ALLOWED_HOSTS.
        with (
            self._resolving_to("10.0.0.1"),
            patch.object(core_network.core_config.settings, "SSRF_ALLOWED_HOSTS", ["10.0.0.0/8"]),
        ):
            assert core_network.host_rejection_reason("nominatim.internal") is None

    def test_allowlisted_private_host_is_audited(self):
        with (
            self._resolving_to("10.0.0.1"),
            patch.object(core_network.core_config.settings, "SSRF_ALLOWED_HOSTS", ["10.0.0.0/8"]),
            patch.object(core_network, "logger") as mock_log,
        ):
            core_network.host_rejection_reason("nominatim.internal", purpose="reverse_geocoding")
            assert "SSRF allowlist hit" in mock_log.info.call_args[0][0]
            assert "reverse_geocoding" in mock_log.info.call_args[0][0]
