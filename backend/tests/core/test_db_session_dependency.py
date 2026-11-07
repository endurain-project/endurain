"""Tests for the request database session dependency's lifetime."""

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

import core.database as core_database
import core.dependencies as core_dependencies


def test_the_session_is_closed_before_a_streamed_body_is_sent():
    """A streamed download must not pin the request's pooled connection while the client reads it."""
    session = MagicMock()
    closed_when_streaming: list[bool] = []
    app = FastAPI()

    @app.get("/download")
    def download(db: core_dependencies.DbSession) -> StreamingResponse:
        def chunks():
            closed_when_streaming.append(session.close.called)
            yield b"data"

        return StreamingResponse(chunks())

    with patch.object(core_database, "SessionLocal", return_value=session):
        response = TestClient(app).get("/download")

    assert response.content == b"data"
    assert closed_when_streaming == [True]
