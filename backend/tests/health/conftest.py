"""Shared setup for the health tests."""

from contextlib import contextmanager
from dataclasses import replace
from unittest.mock import MagicMock, patch

import pytest

import model_registry
import modules.health.computation as health_computation

# The ``Users`` mapper resolves its relationships by name, so a health test that
# compiles a statement needs every model imported even when run on its own.
model_registry.import_all_models()


@pytest.fixture
def passthrough_serializers():
    """Return ORM rows untouched: the serializers are covered by ``test_health_computation``."""
    with (
        patch.object(health_computation, "to_read_schema", side_effect=lambda schema, row: row),
        patch.object(health_computation, "to_read_schemas", side_effect=lambda schema, rows: rows),
    ):
        yield


@pytest.fixture
def stub_model():
    """Return a context manager that makes a ``crud`` module build the given row instead of its ORM model."""

    @contextmanager
    def stub(crud_module, row):
        model = MagicMock(return_value=row)
        with patch.object(crud_module, "SPEC", replace(crud_module.SPEC, model=model)):
            yield model

    return stub
