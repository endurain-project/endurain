"""Tests for positive identity-provider route identifiers."""

import pytest
from pydantic import TypeAdapter, ValidationError

import core.dependencies as core_dependencies


@pytest.mark.parametrize("value", [1, 100])
def test_positive_id_accepts_positive_values(value):
    assert TypeAdapter(core_dependencies.PositiveId).validate_python(value) == value


@pytest.mark.parametrize("value", [0, -1])
def test_positive_id_rejects_non_positive_values(value):
    with pytest.raises(ValidationError):
        TypeAdapter(core_dependencies.PositiveId).validate_python(value)
