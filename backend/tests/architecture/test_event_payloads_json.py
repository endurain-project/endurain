"""Every event payload survives the JSON round trip the outbox and the event bus put it through."""

import datetime
import enum
import importlib
import inspect
import json
import pathlib
import types
import typing
import uuid

import pytest
from jasil.event_versioning import VersionedPayload

_MODULES_ROOT = pathlib.Path("app/modules")

_SCALAR_SAMPLES: dict[typing.Any, typing.Any] = {
    bool: True,
    int: 7,
    str: "sample",
    datetime.datetime: datetime.datetime(2026, 1, 2, 3, 4, 5, tzinfo=datetime.UTC),
    datetime.date: datetime.date(2026, 1, 2),
    uuid.UUID: uuid.uuid4(),
}


def _payload_classes() -> list[type[VersionedPayload]]:
    """
    Return every payload class defined in a ``modules.*.events`` module.

    Returns:
        The payload classes, sorted by dotted name.
    """
    classes: dict[str, type[VersionedPayload]] = {}
    for path in sorted(_MODULES_ROOT.rglob("events.py")):
        name = ".".join(path.relative_to(_MODULES_ROOT.parent).with_suffix("").parts)
        module = importlib.import_module(name)
        for _, cls in inspect.getmembers(module, inspect.isclass):
            if issubclass(cls, VersionedPayload) and cls is not VersionedPayload and cls.__module__ == name:
                classes[f"{cls.__module__}.{cls.__qualname__}"] = cls
    return [classes[name] for name in sorted(classes)]


def _sample(annotation: typing.Any) -> typing.Any:
    """
    Build a sample value for a field annotation.

    Args:
        annotation: The field's type annotation.

    Returns:
        A value that validates against the annotation.

    Raises:
        AssertionError: When the annotation is not covered, so a new payload type extends this table.
    """
    origin = typing.get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        members = [arg for arg in typing.get_args(annotation) if arg is not type(None)]
        return _sample(members[0])
    if origin is list:
        return [_sample(typing.get_args(annotation)[0])]
    if inspect.isclass(annotation) and issubclass(annotation, enum.Enum):
        return next(iter(annotation))
    if annotation in _SCALAR_SAMPLES:
        return _SCALAR_SAMPLES[annotation]
    raise AssertionError(f"no sample value for the payload annotation {annotation!r}; extend _SCALAR_SAMPLES")


def test_payload_classes_are_discovered() -> None:
    """The discovery finds the payloads, so an empty parametrization cannot pass silently."""
    assert len(_payload_classes()) > 0


@pytest.mark.parametrize("cls", _payload_classes(), ids=lambda cls: f"{cls.__module__}.{cls.__qualname__}")
def test_payload_round_trips_through_json(cls: type[VersionedPayload]) -> None:
    """A payload dumps in JSON mode, serialises with ``json.dumps`` and validates back to an equal instance."""
    values = {name: _sample(field.annotation) for name, field in cls.model_fields.items()}
    instance = cls(**values)
    encoded = json.dumps(instance.model_dump(mode="json"))
    assert cls.model_validate(json.loads(encoded)) == instance
