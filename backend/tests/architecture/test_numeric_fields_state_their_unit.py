"""A numeric field of the gear, health and activity schemas says what it measures and in which unit.

A bare ``distance: float`` leaves a client to guess meters or kilometers. The description is where the unit lives
when the name cannot carry it (``docs/developer-guide/http-api.md``, "Response bodies"). A count, a code or a
score still needs a description, but not a unit; the names below are the ones that are neither a measurement nor
documented in the schema's own words.
"""

import enum
import importlib
import inspect
import pkgutil
import types
import typing
from decimal import Decimal

import pydantic

import modules

_PREFIXES = ("modules.gears.", "modules.health.", "modules.activities.")
_NUMERIC = (int, float, Decimal)

#: Names that are identifiers or paging, never a measurement.
_NOT_MEASURED = {"id", "version", "user_id", "page", "num_records", "total", "next"}

#: ``"<module>.<Model>.<field>"`` of a numeric field with no description, by design. Permanent; the value is
#: the reason. Identifiers, counts, indexes and codes of the provider's catalogue have no unit.
_UNDESCRIBED = {
    "modules.activities.activity_exercise_titles.schema.ActivityExerciseTitlesBase.exercise_category": "catalogue code",
    "modules.activities.activity_exercise_titles.schema.ActivityExerciseTitlesBase.exercise_name": "catalogue code",
    "modules.activities.activity_streams.schema.ActivityStreamsBase.stream_type": "the stored code of the stream enum",
    "modules.activities.activity_ingestion.schema.ActivityIngestionJobRead.files_done": "count of files",
    "modules.activities.activity_ingestion.schema.ActivityIngestionJobRead.files_failed": "count of files",
    "modules.activities.activity_ingestion.schema.ActivityIngestionJobRead.files_total": "count of files",
    "modules.activities.activity_sets.schema.ActivitySetsBase.category": "FIT catalogue code",
    "modules.activities.activity_sets.schema.ActivitySetsBase.category_subtype": "FIT catalogue code",
    "modules.activities.activity_sets.schema.ActivitySetsBase.repetitions": "count of repetitions",
    "modules.activities.activity_workout_steps.schema.ActivityWorkoutStepsBase.exercise_category": "FIT code",
    "modules.activities.activity_workout_steps.schema.ActivityWorkoutStepsBase.exercise_name": "FIT code",
    "modules.activities.activity_workout_steps.schema.ActivityWorkoutStepsBase.message_index": "position of a step",
}


def _is_numeric(annotation: object) -> bool:
    """Whether an annotation is a number, optionally nullable; a list, a mapping or an enum is not."""
    if isinstance(annotation, type):
        return issubclass(annotation, _NUMERIC) and not issubclass(annotation, bool | enum.Enum)
    if typing.get_origin(annotation) is typing.Annotated:
        return _is_numeric(typing.get_args(annotation)[0])
    if typing.get_origin(annotation) in {typing.Union, types.UnionType}:
        return any(_is_numeric(arg) for arg in typing.get_args(annotation) if arg is not type(None))
    return False


def _schema_models() -> list[type[pydantic.BaseModel]]:
    found = []
    for info in pkgutil.walk_packages(modules.__path__, "modules."):
        if not info.name.endswith(".schema") or not info.name.startswith(_PREFIXES):
            continue
        module = importlib.import_module(info.name)
        found.extend(
            cls
            for _, cls in inspect.getmembers(module, inspect.isclass)
            if cls.__module__ == info.name and issubclass(cls, pydantic.BaseModel)
        )
    return found


def test_a_numeric_field_has_a_description():
    undescribed = set()
    for model in _schema_models():
        for name, info in model.model_fields.items():
            if name not in inspect.get_annotations(model):
                continue
            skipped = name in _NOT_MEASURED or name.endswith(("_id", "_count"))
            if _is_numeric(info.annotation) and not info.description and not skipped:
                undescribed.add(f"{model.__module__}.{model.__name__}.{name}")

    new = sorted(undescribed - _UNDESCRIBED.keys())
    stale = sorted(_UNDESCRIBED.keys() - undescribed)
    assert not new, "A numeric field has no description naming its unit:\n  " + "\n  ".join(new)
    assert not stale, "Remove from the register, they now have a description:\n  " + "\n  ".join(stale)
