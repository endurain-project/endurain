"""Tests for the request database session dependency's lifetime."""

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from sqlalchemy import select

import core.dependencies as core_dependencies


def test_the_session_is_closed_before_a_streamed_body_is_sent(committed_sessions):
    """A streamed download must not pin the request's pooled connection while the client reads it."""
    in_transaction_when_streaming: list[bool] = []
    app = FastAPI()

    @app.get("/download")
    def download(db: core_dependencies.DbSession) -> StreamingResponse:
        db.execute(select(1))
        assert db.in_transaction()

        def chunks():
            in_transaction_when_streaming.append(db.in_transaction())
            yield b"data"

        return StreamingResponse(chunks())

    response = TestClient(app).get("/download")

    assert response.content == b"data"
    assert in_transaction_when_streaming == [False]
