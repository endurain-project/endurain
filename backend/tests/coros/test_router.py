"""Route-level checks for COROS linking and sync validation."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions
import modules.coros.router as coros_router
import modules.coros.schema as coros_schema


def _call_link(user_id: int = 1):
    with (
        patch.object(coros_router.coros_service, "complete_link") as complete,
        patch.object(coros_router.activity_ingestion_integration, "request_provider_sync") as queue,
    ):
        error = None
        try:
            coros_router.coros_link(
                request=MagicMock(),
                payload=coros_schema.CorosLinkRequest(code="code", state="state"),
                _validate_access_token=None,
                _check_scopes=None,
                token_user_id=user_id,
                db=MagicMock(),
                storage=MagicMock(),
            )
        except core_exceptions.DomainError as err:
            error = err
        return complete, queue, error


def test_link_finishes_the_exchange_then_queues_the_initial_sync():
    complete, queue, error = _call_link()

    assert error is None
    complete.assert_called_once()
    queue.assert_called_once()


def test_an_invalid_state_does_not_queue_a_sync():
    with (
        patch.object(
            coros_router.coros_service,
            "complete_link",
            side_effect=core_exceptions.InvalidInputError("bad state"),
        ) as complete,
        patch.object(coros_router.activity_ingestion_integration, "request_provider_sync") as queue,
        pytest.raises(core_exceptions.InvalidInputError),
    ):
        coros_router.coros_link(
            request=MagicMock(),
            payload=coros_schema.CorosLinkRequest(code="code", state="state"),
            _validate_access_token=None,
            _check_scopes=None,
            token_user_id=1,
            db=MagicMock(),
            storage=MagicMock(),
        )

    complete.assert_called_once()
    queue.assert_not_called()


def test_sync_requires_a_connected_account():
    with (
        patch.object(
            coros_router.coros_service,
            "get_status",
            return_value=SimpleNamespace(linked=False),
        ),
        pytest.raises(core_exceptions.ConflictError),
    ):
        coros_router.coros_sync(
            request=MagicMock(),
            _validate_access_token=None,
            _check_scopes=None,
            token_user_id=1,
            db=MagicMock(),
            storage=MagicMock(),
            start_date=None,
            end_date=None,
        )


def test_sync_rejects_a_reversed_range():
    with (
        patch.object(
            coros_router.coros_service,
            "get_status",
            return_value=SimpleNamespace(linked=True),
        ),
        pytest.raises(core_exceptions.InvalidInputError),
    ):
        coros_router.coros_sync(
            request=MagicMock(),
            _validate_access_token=None,
            _check_scopes=None,
            token_user_id=1,
            db=MagicMock(),
            storage=MagicMock(),
            start_date=date(2026, 2, 1),
            end_date=date(2026, 1, 1),
        )


def test_sync_rejects_an_oversized_backfill():
    with (
        patch.object(
            coros_router.coros_service,
            "get_status",
            return_value=SimpleNamespace(linked=True),
        ),
        pytest.raises(core_exceptions.InvalidInputError),
    ):
        coros_router.coros_sync(
            request=MagicMock(),
            _validate_access_token=None,
            _check_scopes=None,
            token_user_id=1,
            db=MagicMock(),
            storage=MagicMock(),
            start_date=date(2020, 1, 1),
            end_date=date(2026, 1, 1),
        )


def test_unlink_delegates_to_the_service():
    db = MagicMock()
    with patch.object(coros_router.coros_service, "unlink") as unlink:
        coros_router.coros_unlink(
            _validate_access_token=None,
            _check_scopes=None,
            token_user_id=1,
            db=db,
        )

    unlink.assert_called_once_with(1, db)


def test_every_route_requires_authentication():
    for route in coros_router.router.routes:
        dependencies = {dependency.call for dependency in route.dependant.dependencies}
        assert coros_router.auth_dependencies.validate_access_token in dependencies
