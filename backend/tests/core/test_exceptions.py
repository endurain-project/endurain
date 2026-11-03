class TestAccessConcealedError:
    def test_is_indistinguishable_from_not_found_to_a_client(self):
        import core.exceptions as core_exceptions

        concealed = core_exceptions.AccessConcealedError()
        missing = core_exceptions.NotFoundError()

        assert (concealed.status_code, concealed.code, concealed.title, concealed.detail) == (
            missing.status_code,
            missing.code,
            missing.title,
            missing.detail,
        )
        assert isinstance(concealed, core_exceptions.NotFoundError)


class TestDependencyFailedError:
    def test_renders_as_a_424_failed_dependency(self):
        import core.exceptions as core_exceptions

        error = core_exceptions.DependencyFailedError("Strava rejected the code")

        assert (error.status_code, error.code, error.title, error.detail) == (
            424,
            "dependency-failed",
            "Failed Dependency",
            "Strava rejected the code",
        )


class TestTooManyRequestsRetryAt:
    """A rate-limited caller can learn when the limit clears, so a job can wait for it."""

    def test_the_time_the_limit_clears_is_carried(self):
        from datetime import UTC, datetime

        import core.exceptions as core_exceptions

        retry_at = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

        error = core_exceptions.TooManyRequestsError("slow down", retry_at=retry_at)

        assert error.retry_at == retry_at
        assert error.detail == "slow down"

    def test_it_is_optional(self):
        import core.exceptions as core_exceptions

        error = core_exceptions.TooManyRequestsError()

        assert error.retry_at is None
        assert error.detail == "Too Many Requests"


class TestUnhandledErrorBoundary:
    """An error nothing else handles still answers with the problem document."""

    def test_an_unexpected_error_is_an_opaque_problem_document(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        import core.exceptions as core_exceptions

        app = FastAPI()
        core_exceptions.register_exception_handlers(app)

        @app.get("/boom")
        def boom():
            raise RuntimeError("secret internals")

        response = TestClient(app, raise_server_exceptions=False).get("/boom")

        assert response.status_code == 500
        assert response.headers["content-type"].startswith("application/problem+json")
        assert "secret internals" not in response.text


class TestRegisterHandler:
    @staticmethod
    def _client(handled: list[Exception], *, sync: bool = False):
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse
        from fastapi.testclient import TestClient

        import core.exceptions as core_exceptions

        def render(request: Request, exc: LookupError) -> JSONResponse:
            handled.append(exc)
            return JSONResponse({"path": request.url.path}, status_code=418)

        async def handler(request: Request, exc: LookupError) -> JSONResponse:
            return render(request, exc)

        app = FastAPI()
        if sync:
            core_exceptions.register_sync_handler(app, LookupError, render)
        else:
            core_exceptions.register_handler(app, LookupError, handler)

        @app.get("/missing")
        def _missing():
            raise KeyError("absent")

        return TestClient(app)

    def test_a_subclass_of_the_registered_class_reaches_its_handler(self):
        handled: list[Exception] = []

        response = self._client(handled).get("/missing")

        assert (response.status_code, response.json()) == (418, {"path": "/missing"})
        assert [type(exc) for exc in handled] == [KeyError]

    def test_a_synchronous_handler_receives_the_exception_too(self):
        handled: list[Exception] = []

        response = self._client(handled, sync=True).get("/missing")

        assert (response.status_code, response.json()) == (418, {"path": "/missing"})
        assert [type(exc) for exc in handled] == [KeyError]
