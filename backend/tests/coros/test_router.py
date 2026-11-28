"""Route-level checks for COROS linking and sync validation."""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.exceptions import RequestValidationError

import core.exceptions as core_exceptions
import modules.auth.dependencies as auth_dependencies
import modules.auth.schema as auth_schema
import modules.coros.router as coros_router
import modules.coros.schema as coros_schema

USER_ID = uuid.uuid4()


def _call_link():
    with (
        patch.object(coros_router.coros_service, "complete_link") as complete,
        patch.object(coros_router.coros_service, "request_initial_sync") as queue,
    ):
        error = None
        try:
            coros_router.coros_link(
                request=MagicMock(),
                payload=coros_schema.CorosLinkRequest(code="code", state="state"),
                token_user_id=USER_ID,
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
        patch.object(coros_router.coros_service, "request_initial_sync") as queue,
        pytest.raises(core_exceptions.InvalidInputError),
    ):
        coros_router.coros_link(
            request=MagicMock(),
            payload=coros_schema.CorosLinkRequest(code="code", state="state"),
            token_user_id=USER_ID,
            db=MagicMock(),
            storage=MagicMock(),
        )

    complete.assert_called_once()
    queue.assert_not_called()


def test_sync_delegates_to_the_service():
    job = SimpleNamespace(id=uuid.uuid4(), kind="activity_refresh")
    with patch.object(coros_router.coros_service, "request_sync", return_value=job) as request_sync:
        response = coros_router.coros_sync(
            request=MagicMock(),
            response=MagicMock(),
            token_user_id=USER_ID,
            db=MagicMock(),
            storage=MagicMock(),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 7),
        )

    assert response is job
    request_sync.assert_called_once()


def test_sync_rejects_a_reversed_range():
    with pytest.raises(RequestValidationError):
        coros_router.coros_sync(
            request=MagicMock(),
            response=MagicMock(),
            token_user_id=USER_ID,
            db=MagicMock(),
            storage=MagicMock(),
            start_date=date(2026, 2, 1),
            end_date=date(2026, 1, 1),
        )


def test_unlink_delegates_to_the_service():
    db = MagicMock()
    body = auth_schema.StepUpRequest(step_up=auth_schema.StepUpVerification(current_password="secret"))
    verify_step_up = MagicMock()
    with patch.object(coros_router.coros_service, "unlink") as unlink:
        coros_router.coros_unlink(
            request=MagicMock(),
            body=body,
            token_user_id=USER_ID,
            verify_step_up=verify_step_up,
            db=db,
        )

    unlink.assert_called_once_with(USER_ID, body.step_up, verify_step_up, db)


def test_every_route_declares_a_scope():
    for route in coros_router.router.routes:
        dependencies = {dependency.call for dependency in route.dependant.dependencies}
        assert auth_dependencies.check_scopes in dependencies
