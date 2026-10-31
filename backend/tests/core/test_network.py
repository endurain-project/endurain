"""Tests for core.network module."""

import asyncio
import ipaddress
import socket
import threading
import time
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

    def test_trusted_proxy_ignores_forged_prepended_hop(self):
        request = MagicMock(spec=Request)
        request.client.host = "10.0.0.1"
        request.headers = {"X-Forwarded-For": "198.51.100.1, 203.0.113.9"}
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", ["10.0.0.0/8"]):
            result = core_network.get_ip_address(request)
            assert result == "203.0.113.9"

    def test_trusted_proxy_chain_skips_trusted_hops(self):
        request = MagicMock(spec=Request)
        request.client.host = "10.0.0.2"
        request.headers = {"X-Forwarded-For": "198.51.100.1, 203.0.113.9, 10.0.0.1"}
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", ["10.0.0.0/8"]):
            result = core_network.get_ip_address(request)
            assert result == "203.0.113.9"

    def test_trusted_proxy_all_hops_trusted_returns_leftmost(self):
        request = MagicMock(spec=Request)
        request.client.host = "10.0.0.2"
        request.headers = {"X-Forwarded-For": "10.0.0.3, 10.0.0.1"}
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", ["10.0.0.0/8"]):
            result = core_network.get_ip_address(request)
            assert result == "10.0.0.3"

    def test_wildcard_trusts_every_hop_and_returns_leftmost(self):
        request = MagicMock(spec=Request)
        request.client.host = "10.0.0.1"
        request.headers = {"X-Forwarded-For": "1.2.3.4, 5.6.7.8"}
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", ["*"]):
            result = core_network.get_ip_address(request)
            assert result == "1.2.3.4"

    def test_empty_x_forwarded_for_falls_back_to_x_real_ip(self):
        request = MagicMock(spec=Request)
        request.client.host = "10.0.0.1"
        request.headers = {"X-Forwarded-For": " , ", "X-Real-IP": "5.6.7.8"}
        with patch.object(core_network.core_config.settings, "TRUSTED_PROXIES", ["10.0.0.0/8"]):
            result = core_network.get_ip_address(request)
            assert result == "5.6.7.8"

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


class TestRejectPrivateUrlAsync:
    """Tests for bounded asynchronous SSRF validation."""

    @pytest.fixture(autouse=True)
    def _isolated_dns_pool(self):
        """Give each test its own two-slot pool and one worker, then stop it."""
        with (
            patch.object(core_network, "_ssrf_dns_slots", threading.BoundedSemaphore(2)),
            patch.object(core_network, "_ssrf_dns_executor", None),
            patch.object(core_network, "_SSRF_DNS_MAX_WORKERS", 1),
        ):
            yield
            core_network.shutdown_ssrf_dns_executor()

    @staticmethod
    def _blocking_guard(release: threading.Event, calls: list[str]):
        """Return a stand-in guard that records its URL and blocks until released."""

        def guard(url, *, purpose=None):
            calls.append(url)
            release.wait(timeout=5)

        return guard

    @staticmethod
    def _wait_for_free_slot(timeout=2.0):
        """Wait until a slot can be taken, then give it back."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if core_network._ssrf_dns_slots.acquire(blocking=False):
                core_network._ssrf_dns_slots.release()
                return True
            time.sleep(0.01)
        return False

    @pytest.mark.asyncio
    async def test_runs_the_guard_on_the_dedicated_pool_with_context(self):
        seen = {}

        def guard(url, *, purpose=None):
            seen["url"] = url
            seen["purpose"] = purpose
            seen["thread"] = threading.current_thread().name

        with patch.object(core_network, "reject_private_url", guard):
            await core_network.reject_private_url_async("https://idp.example.com", purpose="oidc_discovery")

        assert seen == {"url": "https://idp.example.com", "purpose": "oidc_discovery", "thread": seen["thread"]}
        assert seen["thread"].startswith("ssrf-dns")

    @pytest.mark.asyncio
    async def test_timeout_fails_closed_without_exposing_url(self):
        release = threading.Event()
        secret_url = "https://idp.example.com/discovery?client_secret=secret"

        with (
            patch.object(core_network, "reject_private_url", self._blocking_guard(release, [])),
            patch.object(core_network, "_SSRF_DNS_RESOLUTION_TIMEOUT_SECONDS", 0.05),
            pytest.raises(HTTPException) as exc_info,
        ):
            await core_network.reject_private_url_async(secret_url, purpose="oidc_discovery")
        release.set()

        assert exc_info.value.status_code == 504
        assert exc_info.value.detail == "Hostname resolution timed out"
        assert secret_url not in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_guard_http_exception_is_preserved(self):
        blocked = HTTPException(status_code=400, detail="URL resolves to a non-public address")

        def guard(url, *, purpose=None):
            raise blocked

        with (
            patch.object(core_network, "reject_private_url", guard),
            pytest.raises(HTTPException) as exc_info,
        ):
            await core_network.reject_private_url_async("https://internal.example.com")

        assert exc_info.value is blocked

    @pytest.mark.asyncio
    async def test_refuses_with_503_when_every_slot_is_taken(self):
        calls: list[str] = []
        assert core_network._ssrf_dns_slots.acquire(blocking=False)
        assert core_network._ssrf_dns_slots.acquire(blocking=False)

        with (
            patch.object(core_network, "reject_private_url", self._blocking_guard(threading.Event(), calls)),
            pytest.raises(HTTPException) as exc_info,
        ):
            await core_network.reject_private_url_async("https://idp.example.com")

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == "Hostname resolution is busy"
        assert exc_info.value.headers == {"Retry-After": "1"}
        assert calls == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("url", "detail"),
        [
            ("ftp://idp.example.com", "URL scheme is not permitted"),
            ("https://", "URL has no hostname"),
            ("http://[::1", "Malformed URL"),
        ],
    )
    async def test_url_refused_without_dns_gets_its_400_even_when_the_pool_is_full(self, url, detail):
        calls: list[str] = []
        assert core_network._ssrf_dns_slots.acquire(blocking=False)
        assert core_network._ssrf_dns_slots.acquire(blocking=False)

        with (
            patch.object(core_network, "reject_private_url", self._blocking_guard(threading.Event(), calls)),
            pytest.raises(HTTPException) as exc_info,
        ):
            await core_network.reject_private_url_async(url)

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == detail
        assert calls == []

    @pytest.mark.asyncio
    async def test_stuck_lookup_keeps_its_slot_until_it_finishes(self):
        release = threading.Event()
        calls: list[str] = []
        with (
            patch.object(core_network, "reject_private_url", self._blocking_guard(release, calls)),
            patch.object(core_network, "_SSRF_DNS_RESOLUTION_TIMEOUT_SECONDS", 0.05),
            patch.object(core_network, "_ssrf_dns_slots", threading.BoundedSemaphore(1)),
        ):
            with pytest.raises(HTTPException) as first:
                await core_network.reject_private_url_async("https://stuck.example.com")
            assert first.value.status_code == 504

            # The caller gave up, but the lookup is still running: nothing may queue behind it.
            with pytest.raises(HTTPException) as second:
                await core_network.reject_private_url_async("https://other.example.com")
            assert second.value.status_code == 503
            assert calls == ["https://stuck.example.com"]

            release.set()
            assert self._wait_for_free_slot()
            await core_network.reject_private_url_async("https://other.example.com")
            assert calls == ["https://stuck.example.com", "https://other.example.com"]

    @pytest.mark.asyncio
    async def test_queued_lookup_is_cancelled_when_its_caller_times_out(self):
        release = threading.Event()
        calls: list[str] = []
        with (
            patch.object(core_network, "reject_private_url", self._blocking_guard(release, calls)),
            patch.object(core_network, "_SSRF_DNS_RESOLUTION_TIMEOUT_SECONDS", 0.05),
        ):
            # One worker: the first lookup runs and blocks, the second waits in the queue.
            for url in ("https://stuck.example.com", "https://queued.example.com"):
                with pytest.raises(HTTPException) as exc_info:
                    await core_network.reject_private_url_async(url)
                assert exc_info.value.status_code == 504

            # The single worker takes work in order, so once this later lookup has
            # run, anything queued before it has either run or been cancelled.
            release.set()
            with patch.object(core_network, "_SSRF_DNS_RESOLUTION_TIMEOUT_SECONDS", 5.0):
                await core_network.reject_private_url_async("https://sentinel.example.com")

        assert calls == ["https://stuck.example.com", "https://sentinel.example.com"]

    @pytest.mark.asyncio
    async def test_burst_of_fast_lookups_is_absorbed_with_the_default_sizes(self):
        def fast_guard(url, *, purpose=None):
            time.sleep(0.005)

        with (
            patch.object(core_network, "reject_private_url", fast_guard),
            patch.object(
                core_network, "_ssrf_dns_slots", threading.BoundedSemaphore(core_network._SSRF_DNS_MAX_PENDING)
            ),
            patch.object(core_network, "_SSRF_DNS_MAX_WORKERS", 4),
        ):
            results = await asyncio.gather(
                *(core_network.reject_private_url_async(f"https://h{i}.example.com") for i in range(30)),
                return_exceptions=True,
            )

        assert results == [None] * 30

    @pytest.mark.asyncio
    async def test_shutdown_stops_the_pool_and_the_next_lookup_starts_a_new_one(self):
        with patch.object(core_network, "reject_private_url", lambda url, *, purpose=None: None):
            await core_network.reject_private_url_async("https://idp.example.com")
            first_pool = core_network._ssrf_dns_executor
            assert first_pool is not None

            core_network.shutdown_ssrf_dns_executor()
            assert core_network._ssrf_dns_executor is None
            core_network.shutdown_ssrf_dns_executor()  # already stopped: no-op

            await core_network.reject_private_url_async("https://idp.example.com")
            assert core_network._ssrf_dns_executor is not first_pool


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
