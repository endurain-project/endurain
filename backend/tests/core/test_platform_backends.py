"""Tests for the local-profile platform backends."""

import time
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from redis.exceptions import RedisError, ResponseError

import core.platform.events as platform_events
import core.platform.providers as platform_providers
from core.platform.backends import events_redis, state_redis, storage_s3
from core.platform.backends.clock_system import SystemClock
from core.platform.backends.events_inprocess import InProcessEventBus
from core.platform.backends.lock_noop import NoopLock
from core.platform.backends.state_memory import MemoryState
from core.platform.backends.storage_local import LocalStorage


class TestMemoryState:
    def test_set_get_delete(self):
        state = MemoryState()
        assert state.get("k") is None
        state.set("k", b"v")
        assert state.get("k") == b"v"
        state.delete("k")
        assert state.get("k") is None

    def test_delete_missing_is_noop(self):
        MemoryState().delete("missing")

    def test_incr_from_zero_and_amount(self):
        state = MemoryState()
        assert state.incr("c") == 1
        assert state.incr("c") == 2
        assert state.incr("c", amount=5) == 7
        assert state.get("c") == b"7"

    def test_ttl_expiry(self):
        state = MemoryState()
        with patch("core.platform.backends.state_memory.time.monotonic") as clock:
            clock.return_value = 1000.0
            state.set("k", b"v", ttl_seconds=10)
            clock.return_value = 1009.0
            assert state.get("k") == b"v"
            clock.return_value = 1010.0
            assert state.get("k") is None

    def test_incr_sets_then_preserves_ttl(self):
        state = MemoryState()
        with patch("core.platform.backends.state_memory.time.monotonic") as clock:
            clock.return_value = 100.0
            assert state.incr("c", ttl_seconds=5) == 1
            clock.return_value = 103.0
            assert state.incr("c") == 2
            clock.return_value = 106.0
            assert state.get("c") is None

    def test_set_if_absent(self):
        state = MemoryState()
        assert state.set_if_absent("k", b"first") is True
        assert state.set_if_absent("k", b"second") is False
        assert state.get("k") == b"first"

    def test_set_if_absent_after_expiry(self):
        state = MemoryState()
        with patch("core.platform.backends.state_memory.time.monotonic") as clock:
            clock.return_value = 0.0
            assert state.set_if_absent("k", b"v", ttl_seconds=10) is True
            clock.return_value = 11.0
            assert state.set_if_absent("k", b"v2") is True

    def test_get_and_delete(self):
        state = MemoryState()
        state.set("k", b"v")
        assert state.get_and_delete("k") == b"v"
        assert state.get("k") is None
        assert state.get_and_delete("missing") is None

    def test_delete_prefix(self):
        state = MemoryState()
        state.set("p:1", b"a")
        state.set("p:2", b"b")
        state.set("other", b"c")
        assert state.delete_prefix("p:") == 2
        assert state.get("p:1") is None
        assert state.get("other") == b"c"

    def test_iter_keys(self):
        state = MemoryState()
        state.set("p:1", b"a")
        state.set("p:2", b"b")
        state.set("other", b"c")
        assert sorted(state.iter_keys("p:")) == ["p:1", "p:2"]

    def test_record_tiered_failure_increments_then_locks(self):
        state = MemoryState()
        tiers = ((3, 300), (5, 1800))
        first = state.record_tiered_failure("count", "gate", tiers, 3600)
        assert first == platform_providers.TieredFailureOutcome(1, None, False)
        state.record_tiered_failure("count", "gate", tiers, 3600)
        third = state.record_tiered_failure("count", "gate", tiers, 3600)
        assert third.count == 3
        assert third.newly_locked is True
        assert third.locked_until_epoch is not None

    def test_record_tiered_failure_locked_does_not_increment(self):
        state = MemoryState()
        tiers = ((1, 300),)
        locked = state.record_tiered_failure("count", "gate", tiers, 3600)
        assert locked.newly_locked is True
        again = state.record_tiered_failure("count", "gate", tiers, 3600)
        assert again.count == 1
        assert again.newly_locked is False
        assert again.locked_until_epoch == locked.locked_until_epoch

    def test_record_tiered_failure_reopens_after_gate_expires(self):
        state = MemoryState()
        tiers = ((1, 300),)
        with (
            patch("core.platform.backends.state_memory.time.time", return_value=1000),
            patch("core.platform.backends.state_memory.time.monotonic", return_value=0.0),
        ):
            state.record_tiered_failure("count", "gate", tiers, 3600)
        with (
            patch("core.platform.backends.state_memory.time.time", return_value=2000),
            patch("core.platform.backends.state_memory.time.monotonic", return_value=0.0),
        ):
            reopened = state.record_tiered_failure("count", "gate", tiers, 3600)
        assert reopened.count == 2
        assert reopened.newly_locked is True

    def test_satisfies_state_provider(self):
        assert isinstance(MemoryState(), platform_providers.StateProvider)


class TestRedisState:
    def _backend(self, client):
        return state_redis.RedisState(client)

    def test_get_returns_client_value(self):
        client = MagicMock()
        client.get.return_value = b"v"
        assert self._backend(client).get("k") == b"v"
        client.get.assert_called_once_with("k")

    def test_set_without_ttl(self):
        client = MagicMock()
        self._backend(client).set("k", b"v")
        client.set.assert_called_once_with("k", b"v")

    def test_set_with_ttl_uses_expiry(self):
        client = MagicMock()
        self._backend(client).set("k", b"v", ttl_seconds=30)
        client.set.assert_called_once_with("k", b"v", ex=30)

    def test_delete(self):
        client = MagicMock()
        self._backend(client).delete("k")
        client.delete.assert_called_once_with("k")

    def test_incr_returns_int_and_skips_expire_without_ttl(self):
        client = MagicMock()
        client.incrby.return_value = 5
        assert self._backend(client).incr("c", amount=2) == 5
        client.incrby.assert_called_once_with("c", 2)
        client.expire.assert_not_called()

    def test_incr_with_ttl_sets_expiry(self):
        client = MagicMock()
        client.incrby.return_value = 1
        self._backend(client).incr("c", ttl_seconds=10)
        client.expire.assert_called_once_with("c", 10)

    def test_set_if_absent_with_ttl(self):
        client = MagicMock()
        client.set.return_value = True
        assert self._backend(client).set_if_absent("k", b"v", ttl_seconds=30) is True
        client.set.assert_called_once_with("k", b"v", ex=30, nx=True)

    def test_set_if_absent_returns_false_on_conflict(self):
        client = MagicMock()
        client.set.return_value = None
        assert self._backend(client).set_if_absent("k", b"v") is False
        client.set.assert_called_once_with("k", b"v", nx=True)

    def test_get_and_delete(self):
        client = MagicMock()
        client.getdel.return_value = b"v"
        assert self._backend(client).get_and_delete("k") == b"v"
        client.getdel.assert_called_once_with("k")

    def test_delete_prefix_delegates_to_scan_delete(self):
        client = MagicMock()
        with patch.object(state_redis.platform_redis, "delete_matching_keys", return_value=3) as mock_del:
            assert self._backend(client).delete_prefix("p:") == 3
        mock_del.assert_called_once_with(client, "p:*")

    def test_iter_keys_decodes_bytes(self):
        client = MagicMock()
        client.scan_iter.return_value = iter([b"p:1", b"p:2"])
        assert list(self._backend(client).iter_keys("p:")) == ["p:1", "p:2"]
        client.scan_iter.assert_called_once_with(match="p:*")

    def test_record_tiered_failure_parses_locked_result(self):
        client = MagicMock()
        script = MagicMock(return_value=[5, 12345, 1])
        client.register_script.return_value = script
        outcome = self._backend(client).record_tiered_failure("count", "gate", ((5, 300),), 3600)
        assert outcome == platform_providers.TieredFailureOutcome(5, 12345, True)
        assert script.call_args.kwargs["keys"] == ["gate", "count"]

    def test_record_tiered_failure_parses_unlocked_result(self):
        client = MagicMock()
        client.register_script.return_value = MagicMock(return_value=[2, 0, 0])
        outcome = self._backend(client).record_tiered_failure("count", "gate", ((5, 300),), 3600)
        assert outcome == platform_providers.TieredFailureOutcome(2, None, False)

    def test_from_uri_requests_bytes_client(self):
        with patch.object(state_redis.platform_redis, "get_shared_client") as make_client:
            backend = state_redis.RedisState.from_uri("redis://localhost:6379/0")
        assert make_client.call_args.kwargs["decode_responses"] is False
        assert backend._client is make_client.return_value

    def test_satisfies_state_provider(self):
        assert isinstance(self._backend(MagicMock()), platform_providers.StateProvider)


class TestLocalStorage:
    def test_save_exists_delete(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        assert storage.exists("thumbs", "42.webp") is False
        assert storage.save("thumbs", "42.webp", b"bytes", "image/webp") == "42.webp"
        assert storage.exists("thumbs", "42.webp") is True
        assert (tmp_path / "thumbs" / "42.webp").read_bytes() == b"bytes"
        storage.delete("thumbs", "42.webp")
        assert storage.exists("thumbs", "42.webp") is False

    def test_delete_missing_is_noop(self, tmp_path):
        LocalStorage(str(tmp_path)).delete("thumbs", "missing.webp")

    def test_save_creates_nested_dirs(self, tmp_path):
        LocalStorage(str(tmp_path)).save("media", "sub/dir/x.webp", b"d")
        assert (tmp_path / "media" / "sub" / "dir" / "x.webp").is_file()

    def test_areas_are_isolated(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        storage.save("thumbs", "42.webp", b"a")
        storage.save("media", "42.webp", b"b")
        assert (tmp_path / "thumbs" / "42.webp").read_bytes() == b"a"
        assert (tmp_path / "media" / "42.webp").read_bytes() == b"b"

    def test_url_includes_area_and_prefix(self, tmp_path):
        assert LocalStorage(str(tmp_path)).url("thumbnails", "42.webp") == "/thumbnails/42.webp"
        assert LocalStorage(str(tmp_path), url_prefix="/media/").url("images", "42.webp") == "/media/images/42.webp"

    def test_traversal_rejected(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        with pytest.raises(ValueError, match="escapes base directory"):
            storage.save("thumbs", "../evil.webp", b"x")

    def test_area_traversal_rejected(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        with pytest.raises(ValueError, match="escapes base directory"):
            storage.save("../evil", "x.webp", b"x")

    def test_url_traversal_rejected(self, tmp_path):
        storage = LocalStorage(str(tmp_path))
        with pytest.raises(ValueError, match="escapes base directory"):
            storage.url("thumbs", "../evil.webp")

    def test_symlink_escape_rejected(self, tmp_path):
        outside = tmp_path / "outside"
        outside.mkdir()
        base = tmp_path / "base"
        base.mkdir()
        (base / "link").symlink_to(outside)
        storage = LocalStorage(str(base))
        with pytest.raises(ValueError, match="escapes base directory"):
            storage.save("link", "evil.webp", b"x")

    def test_satisfies_storage_provider(self, tmp_path):
        assert isinstance(LocalStorage(str(tmp_path)), platform_providers.StorageProvider)


class _RecorderSpy:
    """Fake EventRecorder capturing lifecycle calls in order."""

    def __init__(self):
        self.calls: list[str] = []
        self.worker_id = None
        self.handler_name = None

    def record_published(self, event):
        self.calls.append("published")

    @contextmanager
    def track(self, event, *, worker_id, handler_name):
        self.worker_id = worker_id
        self.handler_name = handler_name
        self.calls.append("processing")
        try:
            yield
        except Exception:
            self.calls.append("failed")
            raise
        self.calls.append("completed")


def _named_handler(event):
    pass


class TestInProcessEventBus:
    def test_publish_calls_subscriber(self):
        bus = InProcessEventBus()
        received: list[platform_events.Event] = []
        bus.subscribe("activity.created", received.append)
        event = platform_events.new_event("activity.created", {"activity_id": 1}, source="test")
        bus.publish(event)
        assert received == [event]

    def test_publish_without_subscriber_is_noop(self):
        InProcessEventBus().publish(platform_events.new_event("x", {}, source="t"))

    def test_multiple_subscribers_called_in_order(self):
        bus = InProcessEventBus()
        order: list[str] = []
        bus.subscribe("t", lambda event: order.append("a"))
        bus.subscribe("t", lambda event: order.append("b"))
        bus.publish(platform_events.new_event("t", {}, source="s"))
        assert order == ["a", "b"]

    def test_only_matching_type_dispatched(self):
        bus = InProcessEventBus()
        received: list[platform_events.Event] = []
        bus.subscribe("a", received.append)
        bus.publish(platform_events.new_event("b", {}, source="s"))
        assert received == []

    def test_handler_exception_propagates(self):
        bus = InProcessEventBus()

        def boom(event):
            raise RuntimeError("boom")

        bus.subscribe("t", boom)
        with pytest.raises(RuntimeError, match="boom"):
            bus.publish(platform_events.new_event("t", {}, source="s"))

    def test_start_stop_are_noops(self):
        bus = InProcessEventBus()
        bus.start()
        bus.stop()

    def test_satisfies_event_bus_provider(self):
        assert isinstance(InProcessEventBus(), platform_providers.EventBusProvider)

    def test_publish_records_lifecycle_when_recorder_present(self):
        recorder = _RecorderSpy()
        bus = InProcessEventBus(recorder=recorder)
        bus.subscribe("activity.created", _named_handler)
        bus.publish(platform_events.new_event("activity.created", {"activity_id": 1}, source="test"))
        assert recorder.calls == ["published", "processing", "completed"]
        assert recorder.worker_id == "inprocess"
        assert recorder.handler_name == "_named_handler"

    def test_publish_records_failure_then_reraises(self):
        recorder = _RecorderSpy()
        bus = InProcessEventBus(recorder=recorder)

        def boom(event):
            raise RuntimeError("boom")

        bus.subscribe("t", boom)
        with pytest.raises(RuntimeError, match="boom"):
            bus.publish(platform_events.new_event("t", {}, source="s"))
        assert recorder.calls == ["published", "processing", "failed"]

    def test_publish_without_handlers_still_records_completed(self):
        recorder = _RecorderSpy()
        bus = InProcessEventBus(recorder=recorder)
        bus.publish(platform_events.new_event("no.subscribers", {}, source="s"))
        assert recorder.calls == ["published", "processing", "completed"]
        assert recorder.handler_name is None


class TestNoopLock:
    def test_always_acquires(self):
        with NoopLock().try_acquire("job") as acquired:
            assert acquired is True

    def test_accepts_ttl(self):
        with NoopLock().try_acquire("job", ttl_seconds=30) as acquired:
            assert acquired is True

    def test_satisfies_lock_provider(self):
        assert isinstance(NoopLock(), platform_providers.LockProvider)


class TestSystemClock:
    def test_now_is_utc_aware(self):
        now = SystemClock().now()
        assert now.tzinfo is not None
        assert now.utcoffset().total_seconds() == 0

    def test_monotonic_non_decreasing(self):
        clock = SystemClock()
        assert clock.monotonic() <= clock.monotonic()

    def test_satisfies_clock_provider(self):
        assert isinstance(SystemClock(), platform_providers.ClockProvider)


class TestS3Storage:
    def _backend(self, client, prefix=""):
        return storage_s3.S3Storage(client, "my-bucket", prefix)

    def test_from_uri_builds_client_with_region_and_prefix(self):
        with patch.object(storage_s3.boto3, "client") as mock_client:
            backend = storage_s3.S3Storage.from_uri("s3://my-bucket/thumbs?region=eu-west-1")
        assert mock_client.call_args.kwargs["region_name"] == "eu-west-1"
        backend.save("images", "42.webp", b"d")
        assert mock_client.return_value.put_object.call_args.kwargs["Key"] == "thumbs/images/42.webp"

    def test_from_uri_requires_bucket(self):
        with pytest.raises(ValueError, match="missing a bucket"):
            storage_s3.S3Storage.from_uri("s3:///no-bucket")

    def test_save_with_prefix_and_content_type(self):
        client = MagicMock()
        assert self._backend(client, "thumbs").save("images", "42.webp", b"data", "image/webp") == "42.webp"
        client.put_object.assert_called_once_with(
            Bucket="my-bucket", Key="thumbs/images/42.webp", Body=b"data", ContentType="image/webp"
        )

    def test_save_without_prefix_or_content_type(self):
        client = MagicMock()
        self._backend(client).save("images", "42.webp", b"data")
        client.put_object.assert_called_once_with(Bucket="my-bucket", Key="images/42.webp", Body=b"data")

    def test_exists_true(self):
        client = MagicMock()
        assert self._backend(client).exists("images", "42.webp") is True
        client.head_object.assert_called_once_with(Bucket="my-bucket", Key="images/42.webp")

    def test_exists_false_on_missing_object(self):
        client = MagicMock()
        client.head_object.side_effect = ClientError({"Error": {"Code": "404"}}, "HeadObject")
        assert self._backend(client).exists("images", "42.webp") is False

    def test_exists_reraises_unexpected_client_error(self):
        client = MagicMock()
        client.head_object.side_effect = ClientError({"Error": {"Code": "403"}}, "HeadObject")
        with pytest.raises(ClientError):
            self._backend(client).exists("images", "42.webp")

    def test_delete_uses_prefixed_key(self):
        client = MagicMock()
        self._backend(client, "thumbs").delete("images", "42.webp")
        client.delete_object.assert_called_once_with(Bucket="my-bucket", Key="thumbs/images/42.webp")

    def test_url_returns_presigned_url(self):
        client = MagicMock()
        client.generate_presigned_url.return_value = "https://signed"
        assert self._backend(client).url("images", "42.webp", expires_in=60) == "https://signed"
        client.generate_presigned_url.assert_called_once_with(
            "get_object", Params={"Bucket": "my-bucket", "Key": "images/42.webp"}, ExpiresIn=60
        )

    def test_satisfies_storage_provider(self):
        assert isinstance(self._backend(MagicMock()), platform_providers.StorageProvider)


class _FakeStreamRedis:
    """Minimal Redis stream stub for the event-bus backend tests."""

    def __init__(self, entries=None, group_exists=False):
        self.added: list = []
        self.groups: list = []
        self.acked: list = []
        self.read_calls = 0
        self._group_exists = group_exists
        self._pending = list(entries or [])

    def xadd(self, stream, fields, **kwargs):
        self.added.append((stream, fields, kwargs))
        return "1-0"

    def xgroup_create(self, stream, group, **kwargs):
        if self._group_exists:
            raise ResponseError("BUSYGROUP Consumer Group name already exists")
        self.groups.append((stream, group))

    def xreadgroup(self, group, consumer, streams, count=None, block=None):
        self.read_calls += 1
        if not self._pending:
            time.sleep(0.005)
            return []
        batch, self._pending = self._pending, []
        return [(next(iter(streams)), batch)]

    def xack(self, stream, group, entry_id):
        self.acked.append((stream, group, entry_id))
        return 1


def _make_event():
    return platform_events.Event(
        event_id="e1",
        event_type="activity.created",
        source="test",
        timestamp="2026-07-07T00:00:00+00:00",
        payload={"activity_id": 42},
        metadata={"user_id": 7},
        retry_count=0,
    )


class TestRedisStreamEventBus:
    def test_serialize_deserialize_round_trip(self):
        event = _make_event()
        fields = events_redis.serialize_event(event)
        assert fields["payload"] == '{"activity_id": 42}'
        assert fields["retry_count"] == "0"
        assert events_redis.deserialize_event(fields) == event

    def test_publish_xadds_serialized_event(self):
        client = _FakeStreamRedis()
        bus = events_redis.RedisStreamEventBus(client, stream="s", group="g")
        bus.publish(_make_event())
        stream, fields, kwargs = client.added[0]
        assert stream == "s"
        assert fields["event_type"] == "activity.created"
        assert kwargs["maxlen"] == events_redis._STREAM_MAXLEN

    def test_poll_dispatches_to_subscriber_and_acks(self):
        client = _FakeStreamRedis(entries=[("5-0", events_redis.serialize_event(_make_event()))])
        bus = events_redis.RedisStreamEventBus(client, stream="s", group="g")
        received: list = []
        bus.subscribe("activity.created", received.append)
        bus._poll_once()
        assert [event.event_id for event in received] == ["e1"]
        assert client.acked == [("s", "g", "5-0")]

    def test_poll_without_entries_is_noop(self):
        client = _FakeStreamRedis(entries=[])
        bus = events_redis.RedisStreamEventBus(client, stream="s", group="g")
        bus._poll_once()
        assert client.acked == []

    def test_only_subscribers_for_event_type_run(self):
        client = _FakeStreamRedis()
        bus = events_redis.RedisStreamEventBus(client, stream="s", group="g")
        other: list = []
        bus.subscribe("other.event", other.append)
        bus._dispatch("1-0", events_redis.serialize_event(_make_event()))
        assert other == []
        assert client.acked == [("s", "g", "1-0")]

    def test_dispatch_does_not_ack_when_handler_raises(self):
        client = _FakeStreamRedis()
        bus = events_redis.RedisStreamEventBus(client, stream="s", group="g")

        def boom(event):
            raise RuntimeError("boom")

        bus.subscribe("activity.created", boom)
        bus._dispatch("9-0", events_redis.serialize_event(_make_event()))
        assert client.acked == []  # failure leaves the entry pending for later recovery

    def test_dispatch_does_not_ack_on_malformed_entry(self):
        client = _FakeStreamRedis()
        bus = events_redis.RedisStreamEventBus(client, stream="s", group="g")
        bus._dispatch("7-0", {"event_type": "activity.created"})  # missing fields -> deserialize raises
        assert client.acked == []

    def test_publish_records_published_before_xadd(self):
        recorder = _RecorderSpy()
        client = _FakeStreamRedis()
        bus = events_redis.RedisStreamEventBus(client, stream="s", group="g", recorder=recorder)
        bus.publish(_make_event())
        assert recorder.calls == ["published"]
        assert len(client.added) == 1

    def test_dispatch_records_lifecycle_and_acks(self):
        recorder = _RecorderSpy()
        client = _FakeStreamRedis()
        bus = events_redis.RedisStreamEventBus(client, stream="s", group="g", recorder=recorder)
        bus.subscribe("activity.created", _named_handler)
        bus._dispatch("1-0", events_redis.serialize_event(_make_event()))
        assert recorder.calls == ["processing", "completed"]
        assert recorder.worker_id == bus._consumer
        assert client.acked == [("s", "g", "1-0")]

    def test_dispatch_records_failure_and_leaves_pending(self):
        recorder = _RecorderSpy()
        client = _FakeStreamRedis()
        bus = events_redis.RedisStreamEventBus(client, stream="s", group="g", recorder=recorder)

        def boom(event):
            raise RuntimeError("boom")

        bus.subscribe("activity.created", boom)
        bus._dispatch("2-0", events_redis.serialize_event(_make_event()))
        assert recorder.calls == ["processing", "failed"]
        assert client.acked == []  # failure stays pending

    def test_ensure_group_swallows_busygroup(self):
        bus = events_redis.RedisStreamEventBus(_FakeStreamRedis(group_exists=True), stream="s", group="g")
        bus._ensure_group()  # must not raise

    def test_ensure_group_reraises_other_response_errors(self):
        client = _FakeStreamRedis()

        def _raise(*args, **kwargs):
            raise ResponseError("NOPERM not a busygroup error")

        client.xgroup_create = _raise
        bus = events_redis.RedisStreamEventBus(client, stream="s", group="g")
        with pytest.raises(ResponseError):
            bus._ensure_group()

    def test_start_creates_group_then_stop_joins(self):
        client = _FakeStreamRedis()
        bus = events_redis.RedisStreamEventBus(client, stream="s", group="g")
        bus.start()
        try:
            assert client.groups == [("s", "g")]
        finally:
            bus.stop()
        assert bus._thread is None

    def test_start_is_idempotent(self):
        bus = events_redis.RedisStreamEventBus(_FakeStreamRedis(), stream="s", group="g")
        bus.start()
        try:
            thread = bus._thread
            bus.start()
            assert bus._thread is thread
        finally:
            bus.stop()

    def test_run_survives_redis_error_then_stops(self):
        client = _FakeStreamRedis()
        bus = events_redis.RedisStreamEventBus(client, stream="s", group="g")

        def _flaky(*args, **kwargs):
            bus._stop.set()
            raise RedisError("redis down")

        client.xreadgroup = _flaky
        bus._run()  # catches RedisError, then exits because stop is already set

    def test_from_uri_builds_client(self):
        with patch.object(events_redis.platform_redis, "get_shared_client") as make_client:
            bus = events_redis.RedisStreamEventBus.from_uri("redis://localhost:6379/0", stream="s", group="g")
        make_client.assert_called_once()
        assert bus._client is make_client.return_value

    def test_satisfies_event_bus_provider(self):
        assert isinstance(events_redis.RedisStreamEventBus(_FakeStreamRedis()), platform_providers.EventBusProvider)


class _FakeConnection:
    """Minimal SQLAlchemy connection stub for the advisory-lock tests."""

    def __init__(self, acquired=True, unlock_error=False):
        self._acquired = acquired
        self._unlock_error = unlock_error
        self.executed: list = []
        self.closed = False
        self.invalidated = False

    def execute(self, statement, params=None):
        self.executed.append((str(statement), params))
        if self._unlock_error and "unlock" in str(statement):
            raise RuntimeError("unlock failed")
        return SimpleNamespace(scalar=lambda: self._acquired)

    def invalidate(self):
        self.invalidated = True

    def close(self):
        self.closed = True


class _FakeEngine:
    def __init__(self, acquired=True, unlock_error=False):
        self.connection = _FakeConnection(acquired, unlock_error)

    def connect(self):
        return self.connection


class TestPgAdvisoryLock:
    def test_advisory_key_deterministic_and_signed_64bit(self):
        from core.platform.backends.lock_pg import advisory_key

        assert advisory_key("thumbnail_backfill") == advisory_key("thumbnail_backfill")
        assert advisory_key("a") != advisory_key("b")
        assert -(2**63) <= advisory_key("x") < 2**63

    def test_acquire_true_locks_then_unlocks_and_closes(self):
        from core.platform.backends.lock_pg import PgAdvisoryLock

        engine = _FakeEngine(acquired=True)
        with PgAdvisoryLock(engine).try_acquire("job") as acquired:
            assert acquired is True
        statements = [sql for sql, _ in engine.connection.executed]
        assert any("pg_try_advisory_lock" in sql for sql in statements)
        assert any("pg_advisory_unlock" in sql for sql in statements)
        assert engine.connection.closed is True

    def test_acquire_false_does_not_unlock_but_closes(self):
        from core.platform.backends.lock_pg import PgAdvisoryLock

        engine = _FakeEngine(acquired=False)
        with PgAdvisoryLock(engine).try_acquire("job") as acquired:
            assert acquired is False
        statements = [sql for sql, _ in engine.connection.executed]
        assert not any("pg_advisory_unlock" in sql for sql in statements)
        assert engine.connection.closed is True

    def test_connection_closed_when_body_raises(self):
        from core.platform.backends.lock_pg import PgAdvisoryLock

        engine = _FakeEngine(acquired=True)
        with pytest.raises(RuntimeError), PgAdvisoryLock(engine).try_acquire("job"):
            raise RuntimeError("boom")
        assert engine.connection.closed is True

    def test_from_main_database_uses_app_engine(self):
        import core.database as core_database
        from core.platform.backends.lock_pg import PgAdvisoryLock

        assert PgAdvisoryLock.from_main_database()._engine is core_database.engine

    def test_satisfies_lock_provider(self):
        from core.platform.backends.lock_pg import PgAdvisoryLock

        assert isinstance(PgAdvisoryLock(_FakeEngine()), platform_providers.LockProvider)

    def test_advisory_sql_casts_key_to_bigint(self):
        from core.platform.backends.lock_pg import PgAdvisoryLock

        engine = _FakeEngine(acquired=True)
        with PgAdvisoryLock(engine).try_acquire("job"):
            pass
        statements = [sql for sql, _ in engine.connection.executed]
        assert statements and all("bigint" in sql.lower() for sql in statements)

    def test_unlock_failure_is_logged_and_connection_invalidated(self):
        from core.platform.backends.lock_pg import PgAdvisoryLock

        engine = _FakeEngine(acquired=True, unlock_error=True)
        with PgAdvisoryLock(engine).try_acquire("job") as acquired:
            assert acquired is True
        assert engine.connection.invalidated is True
        assert engine.connection.closed is True

    def test_unlock_failure_does_not_mask_body_exception(self):
        from core.platform.backends.lock_pg import PgAdvisoryLock

        engine = _FakeEngine(acquired=True, unlock_error=True)
        with pytest.raises(ValueError, match="body"), PgAdvisoryLock(engine).try_acquire("job"):
            raise ValueError("body failed")
        assert engine.connection.invalidated is True
        assert engine.connection.closed is True
