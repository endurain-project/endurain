"""Tests for the Garmin export summary utilities."""

import json
from datetime import UTC, datetime
from unittest.mock import Mock

import modules.garmin.bulk_import_utils as garmin_bulk_import_utils

# 2026-01-16T02:48:23 UTC in milliseconds.
START_MS = 1768531703000
START_S = START_MS // 1000

SUMMARY_PATH = "DI_CONNECT/DI-Connect-Fitness/user_0_summarizedActivities.json"


def _reader(members: dict[str, bytes]):
    return members.get


def _load(members: dict[str, bytes]) -> dict[int, str]:
    return garmin_bulk_import_utils.load_summarized_activities(list(members), _reader(members))


class TestIsSummaryMember:
    def test_matches_the_export_path_and_a_flat_file_case_insensitively(self):
        assert garmin_bulk_import_utils.is_summary_member(SUMMARY_PATH)
        assert garmin_bulk_import_utils.is_summary_member("user_0_SummarizedActivities.JSON")

    def test_rejects_other_and_hidden_files(self):
        assert not garmin_bulk_import_utils.is_summary_member("DI_CONNECT/DI-Connect-Fitness/user_0_gear.json")
        assert not garmin_bulk_import_utils.is_summary_member("._user_0_summarizedActivities.json")


class TestLoadSummarizedActivities:
    def test_loads_garmin_export_wrapper_format(self):
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

        index = _load({SUMMARY_PATH: json.dumps(payload).encode()})

        assert index == {START_S: "Auckland Cycling"}

    def test_loads_flat_entry_list(self):
        payload = [
            {"activityId": 1, "name": "Morning Run", "startTimeGmt": START_MS},
            {"activityId": 2, "name": "Evening Swim", "startTimeGmt": START_MS + 3_600_000},
        ]

        index = _load({"summarizedActivities.json": json.dumps(payload).encode()})

        assert index == {START_S: "Morning Run", START_S + 3600: "Evening Swim"}

    def test_merges_several_summary_files(self):
        index = _load(
            {
                "user_0_summarizedActivities.json": json.dumps([{"name": "Ride", "startTimeGmt": START_MS}]).encode(),
                "user_1_summarizedActivities.json": json.dumps(
                    [{"name": "Run", "startTimeGmt": START_MS + 1000}]
                ).encode(),
            }
        )

        assert index == {START_S: "Ride", START_S + 1: "Run"}

    def test_skips_malformed_json_file(self):
        index = _load(
            {
                "bad_summarizedActivities.json": b"{not json",
                "good_summarizedActivities.json": json.dumps([{"name": "Ride", "startTimeGmt": START_MS}]).encode(),
            }
        )

        assert index == {START_S: "Ride"}

    def test_skips_entries_without_name_or_start_time(self):
        payload = [
            {"activityId": 1, "name": None, "startTimeGmt": START_MS},
            {"activityId": 2, "name": "No start"},
            {"activityId": 3, "name": "Valid", "startTimeGmt": START_MS + 1000},
        ]

        index = _load({"summarizedActivities.json": json.dumps(payload).encode()})

        assert index == {START_S + 1: "Valid"}

    def test_marks_a_start_second_shared_by_different_names_and_warns(self, monkeypatch):
        logger = Mock()
        monkeypatch.setattr(garmin_bulk_import_utils, "logger", logger)
        payload = [
            {"activityId": 1, "name": "First", "startTimeGmt": START_MS},
            {"activityId": 2, "name": "Second", "startTimeGmt": START_MS + 500},
        ]

        index = _load({"summarizedActivities.json": json.dumps(payload).encode()})

        assert index == {START_S: None}
        logger.warning.assert_called_once()

    def test_keeps_a_start_second_shared_by_the_same_name(self, monkeypatch):
        logger = Mock()
        monkeypatch.setattr(garmin_bulk_import_utils, "logger", logger)
        payload = [
            {"activityId": 1, "name": "Run", "startTimeGmt": START_MS},
            {"activityId": 1, "name": "Run", "startTimeGmt": START_MS},
        ]

        index = _load({"summarizedActivities.json": json.dumps(payload).encode()})

        assert index == {START_S: "Run"}
        logger.warning.assert_not_called()

    def test_ignores_unrelated_members(self):
        assert _load({"activity.fit": b"binary-ish", "user_0_gear.json": b"[]"}) == {}


class TestFindNameForStartTime:
    def _index(self):
        return {START_S: "Auckland Cycling"}

    def test_exact_match(self):
        start = datetime.fromtimestamp(START_S, tz=UTC)

        assert garmin_bulk_import_utils.find_name_for_start_time(self._index(), start) == "Auckland Cycling"

    def test_match_within_tolerance(self):
        start = datetime.fromtimestamp(START_S + 30, tz=UTC)

        assert garmin_bulk_import_utils.find_name_for_start_time(self._index(), start) == "Auckland Cycling"

    def test_no_match_outside_tolerance(self):
        start = datetime.fromtimestamp(START_S + 120, tz=UTC)

        assert garmin_bulk_import_utils.find_name_for_start_time(self._index(), start) is None

    def test_single_entry_in_range_matches_when_others_are_outside(self):
        index = {START_S: "Ride", START_S + 600: "Run"}
        start = datetime.fromtimestamp(START_S + 30, tz=UTC)

        assert garmin_bulk_import_utils.find_name_for_start_time(index, start) == "Ride"

    def test_two_entries_in_range_give_no_name(self):
        index = {START_S: "Bike", START_S + 40: "Run"}
        start = datetime.fromtimestamp(START_S + 35, tz=UTC)

        assert garmin_bulk_import_utils.find_name_for_start_time(index, start) is None

    def test_exact_match_wins_over_other_entries_in_range(self):
        index = {START_S: "Bike", START_S + 40: "Run"}
        start = datetime.fromtimestamp(START_S + 40, tz=UTC)

        assert garmin_bulk_import_utils.find_name_for_start_time(index, start) == "Run"

    def test_shared_start_second_gives_no_name_even_with_a_unique_neighbour(self):
        index = {START_S: None, START_S + 600: "Run"}

        assert garmin_bulk_import_utils.find_name_for_start_time(index, datetime.fromtimestamp(START_S, tz=UTC)) is None
        assert (
            garmin_bulk_import_utils.find_name_for_start_time(index, datetime.fromtimestamp(START_S + 20, tz=UTC))
            is None
        )

    def test_empty_index(self):
        assert garmin_bulk_import_utils.find_name_for_start_time({}, datetime.now(tz=UTC)) is None
