"""Tests for activity_ingestion.window_service: the failure policy of a provider's activity window."""

import pytest

import core.exceptions as core_exceptions
import modules.activities.activity_ingestion.contracts as activity_ingestion_contracts
import modules.activities.activity_ingestion.window_service as window_service


def _run(items, process, **kwargs):
    return window_service.run_window(
        items, process, provider="acme", user_id=7, describe=lambda item: {"item": item}, **kwargs
    )


def test_every_activity_is_processed_and_the_results_returned_in_order():
    assert _run([1, 2, 3], lambda item: item * 10) == [10, 20, 30]


def test_a_failing_activity_does_not_stop_the_rest_but_its_failure_is_raised_after():
    seen = []

    def process(item):
        seen.append(item)
        if item == 2:
            raise ValueError("bad activity")
        return item

    with pytest.raises(ValueError, match="bad activity"):
        _run([1, 2, 3], process)

    assert seen == [1, 2, 3]


def test_the_first_failure_is_the_one_raised():
    def process(item):
        raise ValueError(f"failed {item}")

    with pytest.raises(ValueError, match="failed 1"):
        _run([1, 2], process)


def test_a_propagated_failure_ends_the_window_at_once():
    seen = []

    def process(item):
        seen.append(item)
        raise core_exceptions.TooManyRequestsError("slow down")

    with pytest.raises(core_exceptions.TooManyRequestsError):
        _run([1, 2, 3], process, propagate=(core_exceptions.TooManyRequestsError,))

    assert seen == [1]


def test_a_failure_not_named_as_propagating_is_isolated():
    def process(item):
        raise core_exceptions.TooManyRequestsError("slow down")

    # Without ``propagate`` even a rate limit is just a failed activity.
    with pytest.raises(core_exceptions.TooManyRequestsError):
        _run([1, 2], process)


def test_a_stopped_window_keeps_what_was_processed_and_raises_nothing():
    def process(item):
        if item == 3:
            raise activity_ingestion_contracts.WindowStoppedError
        return item

    assert _run([1, 2, 3, 4], process) == [1, 2]


def test_a_stopped_window_still_raises_an_earlier_failure():
    def process(item):
        if item == 1:
            raise ValueError("bad activity")
        raise activity_ingestion_contracts.WindowStoppedError

    with pytest.raises(ValueError, match="bad activity"):
        _run([1, 2, 3], process)


def test_a_skipped_activity_is_logged_with_its_description_as_a_warning(caplog):
    def process(item):
        raise ValueError("bad activity")

    with caplog.at_level("WARNING"), pytest.raises(ValueError):
        _run([42], process)

    assert "could not be processed" in caplog.text
    assert "Some activities of the window were not processed" in caplog.text
