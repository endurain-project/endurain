"""Tests for the infra async bridge (dispatch sync code onto the main loop)."""

import asyncio
import threading
from concurrent.futures import Future
from unittest.mock import patch

import pytest

import infra.async_bridge as async_bridge


@pytest.fixture(autouse=True)
def _reset_main_loop():
    """Ensure each test starts and ends with no captured loop."""
    async_bridge.set_main_loop(None)
    yield
    async_bridge.set_main_loop(None)


def _run_loop_in_thread() -> tuple[asyncio.AbstractEventLoop, threading.Thread]:
    """Start a fresh event loop running in a daemon thread and return both."""
    loop = asyncio.new_event_loop()
    ready = threading.Event()

    def _runner() -> None:
        asyncio.set_event_loop(loop)
        loop.call_soon(ready.set)
        loop.run_forever()

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    assert ready.wait(timeout=5)
    return loop, thread


def _stop_loop(loop: asyncio.AbstractEventLoop, thread: threading.Thread) -> None:
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=5)
    loop.close()


class TestSetGetLoop:
    def test_roundtrip(self):
        assert async_bridge.get_main_loop() is None
        loop = asyncio.new_event_loop()
        try:
            async_bridge.set_main_loop(loop)
            assert async_bridge.get_main_loop() is loop
        finally:
            async_bridge.set_main_loop(None)
            loop.close()

    def test_capture_running_loop(self):
        async def _main() -> asyncio.AbstractEventLoop | None:
            async_bridge.capture_running_loop()
            return async_bridge.get_main_loop()

        loop = asyncio.new_event_loop()
        try:
            captured = loop.run_until_complete(_main())
            assert captured is loop
        finally:
            loop.close()


class TestDispatchWithoutLoop:
    @patch("infra.async_bridge.core_logger")
    def test_returns_none_logs_and_closes_coroutine(self, mock_logger):
        state = {"ran": False}

        async def _work() -> None:
            state["ran"] = True

        coro = _work()
        result = async_bridge.dispatch(coro)

        assert result is None
        mock_logger.print_to_log.assert_called_once()
        # The coroutine was closed (never scheduled), not executed.
        assert state["ran"] is False
        assert coro.cr_frame is None

    @patch("infra.async_bridge.core_logger")
    def test_treats_closed_loop_as_no_loop(self, mock_logger):
        loop = asyncio.new_event_loop()
        loop.close()
        async_bridge.set_main_loop(loop)

        async def _work() -> None: ...

        coro = _work()
        assert async_bridge.dispatch(coro) is None
        mock_logger.print_to_log.assert_called_once()
        assert coro.cr_frame is None


class TestDispatchWithLoop:
    def test_runs_coroutine_on_main_loop(self):
        loop, thread = _run_loop_in_thread()
        try:
            async_bridge.set_main_loop(loop)
            captured: dict[str, int | None] = {}

            async def _work() -> int:
                captured["thread"] = threading.current_thread().ident
                return 42

            future = async_bridge.dispatch(_work())

            assert isinstance(future, Future)
            assert future.result(timeout=5) == 42
            # It ran on the loop thread, not the calling (test) thread.
            assert captured["thread"] == thread.ident
        finally:
            async_bridge.set_main_loop(None)
            _stop_loop(loop, thread)

    @patch("infra.async_bridge.core_logger")
    def test_logs_failure_from_coroutine(self, mock_logger):
        loop, thread = _run_loop_in_thread()
        try:
            async_bridge.set_main_loop(loop)

            async def _boom() -> None:
                raise ValueError("kaboom")

            future = async_bridge.dispatch(_boom())

            # A second callback (registered after the bridge's) guarantees the
            # bridge's logging callback has already run when this one fires.
            logged = threading.Event()
            future.add_done_callback(lambda _f: logged.set())

            with pytest.raises(ValueError):
                future.result(timeout=5)
            assert logged.wait(timeout=5)
            mock_logger.print_to_log.assert_called_once()
            assert mock_logger.print_to_log.call_args.args[1] == "error"
        finally:
            async_bridge.set_main_loop(None)
            _stop_loop(loop, thread)
