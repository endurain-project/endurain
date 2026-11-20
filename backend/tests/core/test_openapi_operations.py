"""The OpenAPI document describes an operation by its docstring prose and names it by its handler."""

import uuid

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
