"""Tests for the infra.redis capability module."""

from unittest.mock import MagicMock, patch

import pytest
from redis import RedisError

import infra.redis as platform_redis


class TestLazyRedisAttrs:
    """The redis exception/client classes are exposed lazily via __getattr__."""

    def test_exposes_redis_error(self):
        assert platform_redis.RedisError is RedisError

    def test_exposes_response_error(self):
        from redis.exceptions import ResponseError

        assert platform_redis.ResponseError is ResponseError

    def test_unknown_attribute_raises(self):
        with pytest.raises(AttributeError):
            _ = platform_redis.not_a_real_attribute


class TestDeleteMatchingKeys:
    """Tests for delete_matching_keys function."""

    def test_no_keys(self):
        redis_client = MagicMock()
        redis_client.scan_iter.return_value = iter([])
        result = platform_redis.delete_matching_keys(redis_client, "pattern:*")
        assert result == 0
        redis_client.delete.assert_not_called()

    def test_single_batch(self):
        redis_client = MagicMock()
        redis_client.scan_iter.return_value = iter(["key:1", "key:2"])
        redis_client.delete.return_value = 2
        result = platform_redis.delete_matching_keys(redis_client, "pattern:*", scan_count=10)
        assert result == 2
        redis_client.delete.assert_called_once_with("key:1", "key:2")

    def test_multiple_batches(self):
        redis_client = MagicMock()
        redis_client.scan_iter.return_value = iter(["k1", "k2", "k3", "k4", "k5"])
        redis_client.delete.side_effect = [3, 2]
        result = platform_redis.delete_matching_keys(redis_client, "p:*", scan_count=3)
        assert result == 5
        assert redis_client.delete.call_count == 2
        redis_client.delete.assert_any_call("k1", "k2", "k3")
        redis_client.delete.assert_any_call("k4", "k5")


class TestCreateRedisClient:
    """Tests for create_redis_client function."""

    def test_success(self):
        mock_client = MagicMock()
        with patch("redis.Redis.from_url", return_value=mock_client) as mock_from_url:
            result = platform_redis.create_redis_client("redis://localhost", "cache")

        mock_from_url.assert_called_once()
        mock_client.ping.assert_called_once()
        assert result is mock_client

    def test_redis_error_raises_runtime_error(self):
        with (
            patch("redis.Redis.from_url", side_effect=RedisError("fail")),
            pytest.raises(RuntimeError, match="Unable to initialize Redis storage"),
        ):
            platform_redis.create_redis_client("redis://localhost", "cache")

    def test_value_error_raises_runtime_error(self):
        with (
            patch("redis.Redis.from_url", side_effect=ValueError("bad uri")),
            pytest.raises(RuntimeError, match="Unable to initialize Redis storage"),
        ):
            platform_redis.create_redis_client("bad://uri", "cache")


class TestGetSharedClient:
    """Tests for the memoized shared-client factory."""

    def teardown_method(self):
        platform_redis.reset_shared_clients()

    def test_creates_client_once_per_config(self):
        made = [MagicMock(), MagicMock()]
        with patch.object(platform_redis, "create_redis_client", side_effect=made) as make:
            first = platform_redis.get_shared_client("redis://localhost", purpose="cache")
            second = platform_redis.get_shared_client("redis://localhost", purpose="cache")
        assert first is second is made[0]
        make.assert_called_once()

    def test_distinct_decode_responses_get_distinct_clients(self):
        made = [MagicMock(), MagicMock()]
        with patch.object(platform_redis, "create_redis_client", side_effect=made) as make:
            text_client = platform_redis.get_shared_client("redis://localhost", purpose="cache")
            byte_client = platform_redis.get_shared_client("redis://localhost", purpose="cache", decode_responses=False)
        assert text_client is not byte_client
        assert make.call_count == 2

    def test_reset_shared_clients_forces_rebuild(self):
        with patch.object(platform_redis, "create_redis_client", side_effect=[MagicMock(), MagicMock()]) as make:
            platform_redis.get_shared_client("redis://localhost", purpose="cache")
            platform_redis.reset_shared_clients()
            platform_redis.get_shared_client("redis://localhost", purpose="cache")
        assert make.call_count == 2
