"""Tests for the Garmin-export bulk-import source."""

import json

import pytest

import core.exceptions as core_exceptions
import modules.activities.activity.contracts as activity_contracts
import modules.garmin.bulk_import_source as garmin_bulk_import_source

SUMMARY_PATH = "DI_CONNECT/DI-Connect-Fitness/user_0_summarizedActivities.json"

# 2026-01-16T02:48:23 UTC as epoch seconds.
START_S = 1768531703


def _activity(start_time: str = "2026-01-16T02:48:23") -> activity_contracts.ActivityCore:
    return activity_contracts.ActivityCore(
        user_id=1,
        name="Workout",
        distance=1000,
        activity_type=4,
        start_time=start_time,
        end_time="2026-01-16T03:48:23",
    )


def _source(**kwargs) -> garmin_bulk_import_source.GarminBulkImportSource:
    return garmin_bulk_import_source.GarminBulkImportSource(**kwargs)


class TestSourceKind:
    def test_it_is_a_bulk_import(self):
        assert _source().kind == "bulk_import"
        assert isinstance(_source(), garmin_bulk_import_source.activity_ingestion_integration.BulkImportSource)


class TestMetadataFor:
    def test_no_metadata_without_an_initiated_time(self):
        assert _source().metadata_for("1.fit") == {}

    def test_stamps_the_garmin_import_record(self):
        metadata = _source(import_initiated_time="2026-10-15T00:00:00").metadata_for("1.fit")

        assert metadata == {
            "import_dict": {
                "imported": True,
                "import_source": "Garmin bulk import",
                "import_ISO_time": "2026-10-15T00:00:00",
            }
        }


class TestApplyMetadata:
    def test_names_the_activity_from_the_summary_entry_with_the_same_start_time(self):
        source = _source(import_initiated_time="2026-10-15T00:00:00", activity_names={START_S: "Auckland Cycling"})
        activity = _activity()

        source.apply_metadata(activity, source.metadata_for("1.fit"))

        assert activity.name == "Auckland Cycling"
        assert activity.import_info["import_source"] == "Garmin bulk import"

    def test_keeps_the_parsed_name_without_a_matching_entry(self):
        source = _source(activity_names={START_S: "Auckland Cycling"})
        activity = _activity("2026-01-16T10:00:00")

        source.apply_metadata(activity, {})

        assert activity.name == "Workout"


class TestArchiveLayout:
    def test_activity_files_in_any_folder_are_imported(self):
        assert garmin_bulk_import_source._is_activity_member("DI-Connect-Uploaded-Files/1.fit")
        assert garmin_bulk_import_source._is_activity_member("2.GPX")
        assert not garmin_bulk_import_source._is_activity_member("__MACOSX/1.fit")
        assert not garmin_bulk_import_source._is_activity_member(SUMMARY_PATH)

    def test_the_summary_files_are_packed_but_other_export_files_are_not(self):
        assert garmin_bulk_import_source._is_export_member(SUMMARY_PATH)
        assert garmin_bulk_import_source._is_export_member("1.fit")
        assert not garmin_bulk_import_source._is_export_member("DI_CONNECT/DI-Connect-User/user_profile.json")


class TestBuildSource:
    def test_reads_the_names_from_the_summary_files(self):
        members = {
            SUMMARY_PATH: json.dumps([{"name": "Auckland Cycling", "startTimeGmt": START_S * 1000}]).encode(),
            "1.fit": b"fit",
        }

        source = garmin_bulk_import_source._build_source(7, "2026-10-15T00:00:00", members.get, list(members))

        assert source.activity_names == {START_S: "Auckland Cycling"}
        assert (source.user_id, source.import_initiated_time) == (7, "2026-10-15T00:00:00")

    def test_an_archive_without_a_summary_file_is_not_a_garmin_export(self):
        with pytest.raises(core_exceptions.InvalidInputError):
            garmin_bulk_import_source._build_source(7, "t", lambda name: None, ["1.fit"])

    def test_the_format_is_registered_under_garmin_with_the_bulk_import_folder(self):
        from modules.activities.activity_ingestion import provider_registry

        provider_registry.clear()
        garmin_bulk_import_source.register_bulk_import_format()

        registered = provider_registry.get_bulk_format("garmin")
        assert registered is not None
        assert registered.drop_directory(5) == garmin_bulk_import_source.core_config.bulk_import_dir_for(5)
