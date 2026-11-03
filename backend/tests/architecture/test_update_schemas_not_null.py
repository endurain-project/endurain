"""An edit schema must refuse an explicit null for a field whose column is NOT NULL.

A partial update may omit such a field, but ``{"field": null}`` reaches the flush as a NOT NULL violation, which the
database error handler reports as a 409 "duplicate entry". The schema answers it as a 422 instead.
"""

import importlib
import inspect
import pkgutil
import re

import pydantic

import model_registry
import modules
from core.database import Base

_EDIT_SCHEMA = re.compile(r"(Update|Edit)$")


def _schema_modules() -> list[str]:
    return sorted(
        info.name for info in pkgutil.walk_packages(modules.__path__, "modules.") if info.name.endswith(".schema")
    )


def _edit_schemas() -> list[type[pydantic.BaseModel]]:
    found = []
    for module_name in _schema_modules():
        module = importlib.import_module(module_name)
        found.extend(
            cls
            for _, cls in inspect.getmembers(module, inspect.isclass)
            if cls.__module__ == module_name
            and issubclass(cls, pydantic.BaseModel)
            and _EDIT_SCHEMA.search(cls.__name__)
        )
    return found


def _not_null_columns(schema: type[pydantic.BaseModel]) -> set[str]:
    """Name the NOT NULL columns of the models that live beside a schema."""
    package = schema.__module__.rsplit(".", 1)[0]
    return {
        column.name
        for mapper in Base.registry.mappers
        if mapper.class_.__module__.startswith(f"{package}.")
        for column in mapper.local_table.columns
        if not column.nullable and not column.primary_key
    }


def _accepts_null(schema: type[pydantic.BaseModel], field: str) -> bool:
    try:
        schema.model_validate({field: None})
    except pydantic.ValidationError as error:
        return all(item["type"] == "missing" for item in error.errors())
    return True


def _offenders() -> list[str]:
    model_registry.import_all_models()
    offenders = []
    for schema in _edit_schemas():
        columns = _not_null_columns(schema)
        offenders.extend(
            f"{schema.__module__}.{schema.__name__}.{field}"
            for field in schema.model_fields
            if field in columns and _accepts_null(schema, field)
        )
    return offenders


def test_an_edit_schema_refuses_null_for_a_not_null_column():
    offenders = _offenders()

    assert not offenders, (
        "These edit fields map to a NOT NULL column but accept an explicit null; list them in the schema's "
        f"`not_clearable` (core.partial_update.NotClearable): {offenders}"
    )


def test_the_scan_finds_the_edit_schemas():
    names = {schema.__name__ for schema in _edit_schemas()}

    assert {"ActivityEdit", "UsersEdit", "ProfileUpdate", "GearUpdate", "HealthWaterUpdate"} <= names
