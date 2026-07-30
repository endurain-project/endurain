"""In-process ``StateProvider`` backend."""

import threading
import time
from collections.abc import Iterator

from infra.providers import TieredFailureOutcome


class MemoryState:
    """``StateProvider`` backed by a process-local dict with per-key TTL expiry.

    Correct for the ``local`` profile (single process). Not shared across
    workers/replicas — the deployment fail-fast (F0) rejects using it under a
    distributed or multi-worker profile. Access is guarded by a lock because
    FastAPI runs sync handlers in a threadpool.
    """

    def __init__(self) -> None:
        self._data: dict[str, tuple[bytes, float | None]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _is_expired(expiry: float | None) -> bool:
        return expiry is not None and expiry <= time.monotonic()

    def _live_value(self, key: str) -> bytes | None:
        """Return the unexpired value for *key*, evicting it if it has expired."""
        entry = self._data.get(key)
        if entry is None:
            return None
        value, expiry = entry
        if self._is_expired(expiry):
            del self._data[key]
            return None
        return value

    def get(self, key: str) -> bytes | None:
        with self._lock:
            return self._live_value(key)

    def set(self, key: str, value: bytes, ttl_seconds: int | None = None) -> None:
        with self._lock:
            expiry = time.monotonic() + ttl_seconds if ttl_seconds is not None else None
            self._data[key] = (value, expiry)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def incr(self, key: str, amount: int = 1, ttl_seconds: int | None = None) -> int:
        with self._lock:
            current_bytes = self._live_value(key)
            current = int(current_bytes.decode()) if current_bytes is not None else 0
            new_value = current + amount
            if ttl_seconds is not None:
                expiry: float | None = time.monotonic() + ttl_seconds
            elif current_bytes is not None:
                expiry = self._data[key][1]  # preserve the existing expiry
            else:
                expiry = None
            self._data[key] = (str(new_value).encode(), expiry)
            return new_value

    def set_if_absent(self, key: str, value: bytes, ttl_seconds: int | None = None) -> bool:
        with self._lock:
            if self._live_value(key) is not None:
                return False
            expiry = time.monotonic() + ttl_seconds if ttl_seconds is not None else None
            self._data[key] = (value, expiry)
            return True

    def get_and_delete(self, key: str) -> bytes | None:
        with self._lock:
            value = self._live_value(key)
            if value is not None:
                del self._data[key]
            return value

    def delete_prefix(self, prefix: str) -> int:
        with self._lock:
            matching = [key for key in self._data if key.startswith(prefix)]
            for key in matching:
                del self._data[key]
            return len(matching)

    def iter_keys(self, prefix: str) -> Iterator[str]:
        with self._lock:
            # Snapshot live matching keys under the lock; ``list(self._data)`` guards
            # against the eviction that ``_live_value`` performs while scanning.
            live_keys = [
                key for key in list(self._data) if key.startswith(prefix) and self._live_value(key) is not None
            ]
        return iter(live_keys)

    def record_tiered_failure(
        self,
        counter_key: str,
        gate_key: str,
        tiers: tuple[tuple[int, int], ...],
        counter_ttl_seconds: int,
    ) -> TieredFailureOutcome:
        now = int(time.time())
        with self._lock:
            # Already locked: return the current count without incrementing, so a
            # locked-out caller cannot keep inflating the counter.
            gate_bytes = self._live_value(gate_key)
            if gate_bytes is not None:
                gate_until = int(gate_bytes.decode())
                if gate_until > now:
                    counter_bytes = self._live_value(counter_key)
                    count = int(counter_bytes.decode()) if counter_bytes is not None else 0
                    return TieredFailureOutcome(count, gate_until, False)
                self._data.pop(gate_key, None)  # expired gate

            counter_bytes = self._live_value(counter_key)
            count = (int(counter_bytes.decode()) if counter_bytes is not None else 0) + 1
            self._data[counter_key] = (str(count).encode(), time.monotonic() + counter_ttl_seconds)

            lock_seconds = 0
            for threshold, tier_lock_seconds in tiers:  # ascending; last match wins
                if count >= threshold:
                    lock_seconds = tier_lock_seconds

            if lock_seconds > 0:
                gate_until = now + lock_seconds
                self._data[gate_key] = (str(gate_until).encode(), time.monotonic() + lock_seconds)
                return TieredFailureOutcome(count, gate_until, True)
            return TieredFailureOutcome(count, None, False)
