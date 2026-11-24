"""The OpenAPI document describes an operation by its docstring prose and names it by its handler."""

import uuid

import core.idempotency as core_idempotency
import core.problem_details as core_problem_details


def _document() -> dict:
    app = core_problem_details.ProblemDetailsFastAPI()

    @app.get("/sectioned")
    def read_sectioned(user_id: uuid.UUID) -> dict:
        """Return the thing for a client.

        It answers the same thing every time.
        """
        return {"user_id": str(user_id)}

    @app.post("/prose")
    def create_prose() -> dict:
        """Create the thing.

        Notes are prose here, not a section.
        """
        return {}

    @app.delete("/bare")
    def delete_bare() -> dict:
        return {}

    return app.openapi()


def test_a_description_is_the_docstring():
    assert _document()["paths"]["/prose"]["post"]["description"] == (
        "Create the thing.\n\nNotes are prose here, not a section."
    )


def test_an_operation_without_a_docstring_has_no_description():
    assert "description" not in _document()["paths"]["/bare"]["delete"]


def test_the_operation_id_is_the_handler_name():
    paths = _document()["paths"]

    assert paths["/sectioned"]["get"]["operationId"] == "read_sectioned"
    assert paths["/prose"]["post"]["operationId"] == "create_prose"
    assert paths["/bare"]["delete"]["operationId"] == "delete_bare"


def _idempotent_document() -> dict:
    app = core_problem_details.ProblemDetailsFastAPI()

    @app.post("/things", status_code=201, dependencies=[core_idempotency.Idempotent])
    def create_thing(body: dict) -> dict:
        return {}

    @app.post("/plain")
    def create_plain(body: dict) -> dict:
        return {}

    @app.post("/keyed", status_code=202)
    def create_keyed(body: dict, key: core_idempotency.IdempotencyKey) -> dict:
        return {}

    return app.openapi()


def test_an_operation_that_reads_the_key_declares_the_header_and_its_three_errors():
    operation = _idempotent_document()["paths"]["/things"]["post"]
    header = next(item for item in operation["parameters"] if item["name"] == "Idempotency-Key")

    assert header["in"] == "header"
    assert not header.get("required")
    assert "Idempotency-Key" in operation["responses"]["400"]["description"]
    assert "Idempotency-Key" in operation["responses"]["409"]["description"]
    assert "Retry-After" in operation["responses"]["409"]["headers"]
    assert "Idempotency-Key" in operation["responses"]["422"]["description"]


def test_an_operation_without_the_key_describes_none_of_it():
    operation = _idempotent_document()["paths"]["/plain"]["post"]

    assert "400" not in operation["responses"]
    assert "Idempotency-Key" not in operation["responses"]["409"]["description"]
    assert "Idempotency-Key" not in operation["responses"]["422"]["description"]


def test_a_route_that_only_reads_the_key_declares_400_and_422_but_no_in_flight_409():
    operation = _idempotent_document()["paths"]["/keyed"]["post"]

    assert "Idempotency-Key" in operation["responses"]["400"]["description"]
    assert "Idempotency-Key" in operation["responses"]["422"]["description"]
    assert "Idempotency-Key" not in operation["responses"]["409"]["description"]
    assert "Retry-After" not in operation["responses"]["409"].get("headers", {})
