"""Tests for Garmin bulk import summary utilities."""

import json
from datetime import UTC, datetime

import garmin.bulk_import_utils as garmin_bulk_import_utils

# 2026-01-16T02:48:23 UTC in milliseconds, mirroring the issue #492 example.
START_MS = 1768531703000
START_S = START_MS // 1000


def _write_summary(tmp_path, file_name, payload):
    file_path = tmp_path / file_name
    file_path.write_text(json.dumps(payload), encoding="utf-8")
    return file_path


class TestLoadSummarizedActivities:
    def test_loads_garmin_export_wrapper_format(self, tmp_path):
        payload = [
            {
                "summarizedActivitiesExport": [
                    {
                        "activityId": 21562025206,
                        "name": "Auckland Cycling",
                        "activityType": "cycling",
                        "startTimeGmt": START_MS,
                    }
                ]
            }
        ]
        _write_summary(tmp_path, "123_summarizedActivities.json", payload)

        index = garmin_bulk_import_utils.load_summarized_activities(str(tmp_path))

        assert index == {START_S: {"name": "Auckland Cycling", "activityId": 21562025206}}

    def test_loads_flat_entry_list(self, tmp_path):
        payload = [
            {"activityId": 1, "name": "Morning Run", "startTimeGmt": START_MS},
            {"activityId": 2, "name": "Evening Swim", "startTimeGmt": START_MS + 3_600_000},
        ]
        _write_summary(tmp_path, "summarizedActivities.json", payload)

        index = garmin_bulk_import_utils.load_summarized_activities(str(tmp_path))

        assert len(index) == 2
        assert index[START_S]["name"] == "Morning Run"
        assert index[START_S + 3600]["name"] == "Evening Swim"

    def test_skips_malformed_json_file(self, tmp_path):
        (tmp_path / "bad_summarizedActivities.json").write_text("{not json", encoding="utf-8")
        _write_summary(
            tmp_path,
            "good_summarizedActivities.json",
            [{"activityId": 1, "name": "Ride", "startTimeGmt": START_MS}],
        )

        index = garmin_bulk_import_utils.load_summarized_activities(str(tmp_path))

        assert len(index) == 1

    def test_skips_entries_without_name_or_start_time(self, tmp_path):
        payload = [
            {"activityId": 1, "name": None, "startTimeGmt": START_MS},
            {"activityId": 2, "name": "No start"},
            {"activityId": 3, "name": "Valid", "startTimeGmt": START_MS + 1000},
        ]
        _write_summary(tmp_path, "summarizedActivities.json", payload)

        index = garmin_bulk_import_utils.load_summarized_activities(str(tmp_path))

        assert list(index.values()) == [{"name": "Valid", "activityId": 3}]

    def test_ignores_unrelated_files_and_missing_dir(self, tmp_path):
        (tmp_path / "activity.fit").write_text("binary-ish", encoding="utf-8")

        assert garmin_bulk_import_utils.load_summarized_activities(str(tmp_path)) == {}
        assert garmin_bulk_import_utils.load_summarized_activities(str(tmp_path / "missing")) == {}


class TestFindSummaryForStartTime:
    def _index(self):
        return {START_S: {"name": "Auckland Cycling", "activityId": 21562025206}}

    def test_exact_match_from_iso_string(self):
        start = datetime.fromtimestamp(START_S, tz=UTC).strftime("%Y-%m-%dT%H:%M:%S")

        entry = garmin_bulk_import_utils.find_summary_for_start_time(self._index(), start)

        assert entry is not None
        assert entry["name"] == "Auckland Cycling"

    def test_match_within_tolerance(self):
        start = datetime.fromtimestamp(START_S + 30, tz=UTC)

        entry = garmin_bulk_import_utils.find_summary_for_start_time(self._index(), start)

        assert entry is not None
        assert entry["name"] == "Auckland Cycling"

    def test_no_match_outside_tolerance(self):
        start = datetime.fromtimestamp(START_S + 120, tz=UTC)

        assert garmin_bulk_import_utils.find_summary_for_start_time(self._index(), start) is None

    def test_nearest_entry_wins(self):
        index = {
            START_S: {"name": "Far", "activityId": 1},
            START_S + 40: {"name": "Near", "activityId": 2},
        }
        start = datetime.fromtimestamp(START_S + 35, tz=UTC)

        entry = garmin_bulk_import_utils.find_summary_for_start_time(index, start)

        assert entry is not None
        assert entry["name"] == "Near"

    def test_none_inputs(self):
        assert garmin_bulk_import_utils.find_summary_for_start_time({}, datetime.now(tz=UTC)) is None
        assert garmin_bulk_import_utils.find_summary_for_start_time(self._index(), None) is None
        assert garmin_bulk_import_utils.find_summary_for_start_time(self._index(), "not-a-date") is None
