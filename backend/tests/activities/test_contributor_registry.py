"""Tests for the process-local activity contributor registry."""

from unittest.mock import MagicMock

import pytest

import module_registry
import modules.activities.contributor_registry as contributor_registry
import modules.activities.contributors as contributors


@pytest.fixture(autouse=True)
def _reset_contributors():
    """Isolate registry mutations and restore app composition afterward."""
    contributor_registry.clear()
    yield
    module_registry.configure_activity_contributors()


def test_duplicate_key_replaces_in_place() -> None:
    """A same-key registration is idempotent and keeps deterministic order."""
    first = contributors.ActivityIngestionContributor("streams", MagicMock())
    laps = contributors.ActivityIngestionContributor("laps", MagicMock())
    replacement = contributors.ActivityIngestionContributor("streams", MagicMock())

    contributor_registry.register_activity_ingestion(first)
    contributor_registry.register_activity_ingestion(laps)
    contributor_registry.register_activity_ingestion(replacement)

    assert contributor_registry.activity_ingestion_contributors() == (replacement, laps)
    assert contributor_registry.get_activity_ingestion_contributor("streams") is replacement


def test_all_contributor_kinds_have_ordered_accessors() -> None:
    """Each contributor kind preserves registration order independently."""
    activity = contributors.ActivityIngestionContributor("laps", MagicMock())
    file = contributors.FileIngestionContributor("exercise_titles", MagicMock())
    profile_activity = contributors.ProfileActivityContributor(
        "media",
        "data/activity_media.json",
        "activity_media",
        False,
        MagicMock(),
        MagicMock(),
    )
    profile_global = contributors.ProfileGlobalContributor(
        "exercise_titles",
        "data/activity_exercise_titles.json",
        "activity_exercise_titles",
        MagicMock(),
        MagicMock(),
    )

    contributor_registry.register_activity_ingestion(activity)
    contributor_registry.register_file_ingestion(file)
    contributor_registry.register_profile_activity(profile_activity)
    contributor_registry.register_profile_global(profile_global)

    assert contributor_registry.activity_ingestion_contributors() == (activity,)
    assert contributor_registry.file_ingestion_contributors() == (file,)
    assert contributor_registry.profile_activity_contributors() == (profile_activity,)
    assert contributor_registry.profile_global_contributors() == (profile_global,)
    assert contributor_registry.get_file_ingestion_contributor("exercise_titles") is file


def test_clear_removes_every_contributor_kind() -> None:
    """Composition reset removes contributors from all four registries."""
    contributor_registry.register_activity_ingestion(contributors.ActivityIngestionContributor("laps", MagicMock()))
    contributor_registry.register_file_ingestion(contributors.FileIngestionContributor("exercise_titles", MagicMock()))

    contributor_registry.clear()

    assert contributor_registry.activity_ingestion_contributors() == ()
    assert contributor_registry.file_ingestion_contributors() == ()
    assert contributor_registry.profile_activity_contributors() == ()
    assert contributor_registry.profile_global_contributors() == ()
