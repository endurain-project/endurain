"""Tests for the RFC 9457 problem-details error contract.

The value of a single error shape is that a client writes one error path, so
these assert the shape holds across *every* way the API can fail — a domain
error, a bare HTTPException from a module not yet converted, and a request
validation failure — not just the happy one.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException, Query
from fastapi.testclient import TestClient

import core.exceptions as core_exceptions
import core.problem_details as core_problem_details


def _client() -> TestClient:
    app = FastAPI()
    core_exceptions.register_exception_handlers(app)

    @app.get("/domain")
    def _domain():
        raise core_exceptions.NotFoundError("Activity 7 not found")

    @app.get("/legacy")
    def _legacy():
        raise HTTPException(status_code=403, detail="Nope")

    @app.get("/legacy-dict")
    def _legacy_dict():
        raise HTTPException(status_code=413, detail={"message": "Too big", "code": "file-size-exceeded"})

    @app.get("/validated")
    def _validated(count: int = Query()):
        return {"count": count}

    @app.get("/boom")
    def _boom():
        raise core_exceptions.ProcessingError()

    return TestClient(app, raise_server_exceptions=False)


class TestProblemDocumentShape:
    def test_domain_error_is_a_problem_document(self):
        resp = _client().get("/domain")

        assert resp.status_code == 404
        assert resp.headers["content-type"].startswith(core_problem_details.PROBLEM_CONTENT_TYPE)
        body = resp.json()
        assert body["type"] == "urn:endurain:error:not-found"
        assert body["title"] == "Not Found"
        assert body["status"] == 404
        assert body["detail"] == "Activity 7 not found"
        assert body["instance"] == "/domain"

    def test_detail_is_preserved_for_existing_clients(self):
        """RFC 9457 names its human-readable member ``detail`` too.

        That is what makes this change additive: a client that only reads
        ``detail`` keeps working untouched.
        """
        assert _client().get("/domain").json()["detail"] == "Activity 7 not found"

    def test_bare_http_exception_gets_the_same_shape(self):
        """A module not yet on domain errors must not speak a second dialect."""
        resp = _client().get("/legacy")

        assert resp.status_code == 403
        assert resp.headers["content-type"].startswith(core_problem_details.PROBLEM_CONTENT_TYPE)
        body = resp.json()
        assert body["type"] == "urn:endurain:error:forbidden"
        assert body["detail"] == "Nope"

    def test_structured_http_exception_detail_is_flattened(self):
        """The upload helpers raise ``detail={"message":…, "code":…}``."""
        body = _client().get("/legacy-dict").json()

        assert body["status"] == 413
        assert body["detail"] == "Too big"
        # The helper's own code becomes the type, not a nested object.
        assert body["type"] == "urn:endurain:error:file-size-exceeded"

    def test_validation_error_keeps_detail_a_string(self):
        """FastAPI's default 422 makes ``detail`` a list for this one status."""
        resp = _client().get("/validated?count=abc")

        assert resp.status_code == 422
        body = resp.json()
        assert isinstance(body["detail"], str)
        assert body["type"] == "urn:endurain:error:validation-failed"
        assert body["errors"][0]["field"].endswith("count")
        assert body["errors"][0]["message"]

    def test_every_error_path_agrees_on_the_members(self):
        client = _client()
        required = {"type", "title", "status", "detail", "instance"}
        for path in ("/domain", "/legacy", "/legacy-dict", "/validated?count=abc", "/boom"):
            body = client.get(path).json()
            assert required <= set(body), f"{path} is missing {required - set(body)}"


class TestRequestCorrelation:
    def test_request_id_is_included_when_assigned(self):
        with patch("core.exceptions.core_middleware_request_id.get_request_id", return_value="req-123"):
            body = _client().get("/domain").json()
        assert body["request_id"] == "req-123"

    def test_request_id_is_omitted_when_absent(self):
        with patch("core.exceptions.core_middleware_request_id.get_request_id", return_value=""):
            body = _client().get("/domain").json()
        assert "request_id" not in body


class TestInformationDisclosure:
    def test_internal_errors_stay_opaque(self):
        """A 500 must not leak the cause; it belongs in the log line."""
        body = _client().get("/boom").json()

        assert body["status"] == 500
        assert body["detail"] == "Internal Server Error"


class TestErrorCodesAreStable:
    @pytest.mark.parametrize(
        ("error", "expected_type", "expected_status"),
        [
            (core_exceptions.NotFoundError, "urn:endurain:error:not-found", 404),
            (core_exceptions.PermissionDeniedError, "urn:endurain:error:permission-denied", 403),
            (core_exceptions.InvalidInputError, "urn:endurain:error:invalid-input", 400),
            (core_exceptions.ConflictError, "urn:endurain:error:conflict", 409),
            (core_exceptions.UnsupportedFormatError, "urn:endurain:error:unsupported-format", 406),
            (core_exceptions.UnsupportedMediaTypeError, "urn:endurain:error:unsupported-media-type", 415),
            (core_exceptions.ProcessingError, "urn:endurain:error:internal-error", 500),
        ],
    )
    def test_type_urn_and_status(self, error, expected_type, expected_status):
        """These strings are a published contract — clients match on them."""
        instance = error()
        assert core_problem_details.problem_type(instance.code) == expected_type
        assert instance.status_code == expected_status


class TestBuildProblemResponse:
    def test_extension_members_are_included(self):
        request = MagicMock()
        request.url.path = "/x"

        response = core_exceptions.build_problem_response(
            request=request,
            status_code=429,
            code="rate-limited",
            title="Too Many Requests",
            detail="Slow down",
            retry_after=30,
        )

        assert response.status_code == 429
        assert response.media_type == core_problem_details.PROBLEM_CONTENT_TYPE
        assert b'"retry_after":30' in response.body

    def test_none_extensions_are_dropped(self):
        request = MagicMock()
        request.url.path = "/x"

        response = core_exceptions.build_problem_response(
            request=request,
            status_code=400,
            code="invalid-input",
            title="Bad Request",
            detail="nope",
            errors=None,
        )

        assert b"errors" not in response.body
