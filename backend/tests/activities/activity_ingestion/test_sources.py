"""Tests for the ingestion source objects.

These replaced six loosely-related keyword arguments threaded through the
pipeline, so what is tested here is mostly *decisions the source now owns*: which
metadata applies to a file, where a failed file goes, and whether one activity of
a multi-activity file should be imported at all.

The Strava-export specialisation is a subclass owned by the Strava module and is
tested in ``tests/strava/test_bulk_import_source.py`` — the split that stopped
activities importing a provider.
"""

import core.config as core_config
import modules.activities.activity.contracts as activities_contracts
import modules.activities.activity_ingestion.sources as sources


def _activity() -> activities_contracts.ActivityCore:
    return activities_contracts.ActivityCore(
        user_id=1,
        name="Workout",
        distance=1000,
        activity_type=1,
        start_time="2023-10-21T07:41:47",
        end_time="2023-10-21T08:41:47",
    )


class TestSourceKinds:
    def test_each_source_names_its_provenance(self):
        assert sources.UploadSource().kind == "upload"
        assert sources.GarminSource().kind == "garmin"
        assert sources.BulkImportSource().kind == "bulk_import"


class TestGarminSource:
    def test_carries_a_gear_id_the_provider_already_resolved(self):
        # Ingestion never asks a provider module which local gear a Garmin UUID
        # maps to; the provider resolves it and hands the id over.
        source = sources.GarminSource(gear_id=7, provider_gear_id="uuid-1")
        assert (source.gear_id, source.provider_gear_id) == (7, "uuid-1")


class TestErrorDirectory:
    def test_per_user_directory_when_the_import_has_an_owner(self):
        source = sources.BulkImportSource(user_id=7)
        assert source.error_directory == core_config.bulk_import_error_dir_for(7)

    def test_shared_directory_when_it_does_not(self):
        assert sources.BulkImportSource().error_directory == core_config.FILES_BULK_IMPORT_IMPORT_ERRORS_DIR


class TestMetadataFor:
    def test_no_metadata_without_an_initiated_time(self):
        assert sources.BulkImportSource().metadata_for("f.gpx") == {}

    def test_records_only_the_import(self):
        source = sources.BulkImportSource(import_initiated_time="2026-07-21T00:00:00")

        assert source.metadata_for("f.gpx") == {
            "import_dict": {
                "imported": True,
                "import_source": "Basic bulk import",
                "import_ISO_time": "2026-07-21T00:00:00",
            }
        }


class TestShouldImport:
    def test_a_plain_folder_import_never_skips(self):
        # Nothing lists the same file once per activity, so nothing is a duplicate.
        assert sources.BulkImportSource().should_import("activity", {}, activities_in_file=5) is True


class TestApplyBulkImportMetadata:
    def test_manifest_values_take_precedence_over_the_parsed_file(self):
        activity = _activity()

        sources.apply_bulk_import_metadata(
            activity,
            {
                "name": "Morning Ride",
                "description": "Felt good",
                "gear_id": 4,
                "import_dict": {"import_ISO_time": "2026-07-21T00:00:00"},
            },
        )

        assert activity.name == "Morning Ride"
        assert activity.description == "Felt good"
        assert activity.gear_id == 4
        assert activity.import_info == {"import_ISO_time": "2026-07-21T00:00:00"}

    def test_absent_metadata_leaves_the_parsed_values_alone(self):
        activity = _activity()

        sources.apply_bulk_import_metadata(activity, {})

        assert activity.name == "Workout"
        assert activity.gear_id is None

    def test_the_source_applies_through_the_shared_helper(self):
        activity = _activity()

        sources.BulkImportSource().apply_metadata(activity, {"name": "Morning Ride"})

        assert activity.name == "Morning Ride"


class TestImportSideArtifacts:
    def test_a_plain_folder_import_has_no_sidecar(self):
        assert sources.BulkImportSource().import_side_artifacts([], "f.gpx", None) is None
