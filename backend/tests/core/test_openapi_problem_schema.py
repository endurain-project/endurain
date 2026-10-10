"""Tests that the generated OpenAPI describes the errors the API really returns.

The frontend's typed client is generated from this document, so a schema that
disagrees with the handlers is not a documentation problem — it hands every
client the wrong type. FastAPI's defaults disagreed on 146 operations once the
RFC 9457 handlers were installed.
"""

import json

from fastapi import FastAPI, Query

import core.problem_details as core_problem_details


def _schema_of(app: FastAPI) -> dict:
    core_problem_details.install_problem_schema(app)
    return app.openapi()


def _app_with_validated_route() -> FastAPI:
    app = FastAPI()

    @app.get("/thing")
    def _thing(count: int = Query()):
        return {"count": count}

    return app


class TestErrorResponsesAreProblemDocuments:
    def test_problem_detail_is_registered(self):
        schema = _schema_of(_app_with_validated_route())
        assert "ProblemDetail" in schema["components"]["schemas"]

    def test_validation_response_no_longer_claims_a_list_detail(self):
        """FastAPI's HTTPValidationError types ``detail`` as an array of errors.

        The validation handler returns a string ``detail`` with the field errors
        under ``errors``, so leaving the default in place documented a response
        the API cannot produce.
        """
        schema = _schema_of(_app_with_validated_route())

        response = schema["paths"]["/thing"]["get"]["responses"]["422"]
        assert list(response["content"]) == [core_problem_details.PROBLEM_CONTENT_TYPE]
        assert response["content"][core_problem_details.PROBLEM_CONTENT_TYPE]["schema"] == {
            "$ref": "#/components/schemas/ProblemDetail"
        }

    def test_superseded_schemas_are_removed(self):
        """Left behind they would generate dead types in the frontend client."""
        schema = _schema_of(_app_with_validated_route())

        assert "HTTPValidationError" not in schema["components"]["schemas"]
        # Only HTTPValidationError referenced it, so it orphans on the second pass.
        assert "ValidationError" not in schema["components"]["schemas"]

    def test_every_operation_declares_a_default_problem_response(self):
        """Any unlisted failure is a problem document too, stated once per operation."""
        schema = _schema_of(_app_with_validated_route())

        responses = schema["paths"]["/thing"]["get"]["responses"]
        assert core_problem_details.PROBLEM_CONTENT_TYPE in responses["default"]["content"]

    def test_success_responses_are_untouched(self):
        schema = _schema_of(_app_with_validated_route())

        ok = schema["paths"]["/thing"]["get"]["responses"]["200"]
        assert "application/json" in ok["content"]

    def test_generation_is_cached_and_idempotent(self):
        app = _app_with_validated_route()
        first = json.dumps(_schema_of(app), sort_keys=True)
        second = json.dumps(app.openapi(), sort_keys=True)
        assert first == second


class TestExportedSchemaMatchesTheApp:
    def test_exported_document_is_patched(self):
        """``scripts/export_openapi.py`` builds its own app; it must patch too.

        CI generates the frontend client from that script, so an unpatched
        exporter would ship the wrong types even with the runtime app correct.
        """
        import sys
        from pathlib import Path

        scripts = Path(__file__).resolve().parents[2] / "scripts"
        sys.path.insert(0, str(scripts))
        try:
            import export_openapi
        finally:
            sys.path.remove(str(scripts))

        schema = export_openapi.build_openapi()

        assert "ProblemDetail" in schema["components"]["schemas"]
        assert "HTTPValidationError" not in schema["components"]["schemas"]
