"""Tests for Strava gear parsing and sync."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from stravalib.exc import AccessUnauthorized

import core.exceptions as core_exceptions
import modules.gears.gear.schema as gears_schema
import modules.strava.gear_service as gear_utils

BIKE = gears_schema.GearType.BIKE
SHOES = gears_schema.GearType.SHOES


def _bike(name, brand=None, model=None):
    return {"Bike Name": name, "Bike Brand": brand, "Bike Model": model}


def _shoe(name, brand=None, model=None):
    return {"Shoe Name": name, "Shoe Brand": brand, "Shoe Model": model}


def test_shoe_csv_is_parsed_from_the_path_it_is_given(tmp_path):
    """The upload is parsed where the caller saved it; no configured directory is consulted."""
    shoes_file = tmp_path / "gear.csv"
    shoes_file.write_text("Shoe Name,Shoe Brand,Shoe Model\nPegasus,Nike,Pegasus\n")

    assert gear_utils.parse_gear_csv(str(shoes_file), SHOES) == [_shoe("Pegasus", "Nike", "Pegasus")]


def test_bike_csv_is_parsed_from_the_path_it_is_given(tmp_path):
    bikes_file = tmp_path / "gear.csv"
    bikes_file.write_text("Bike Name,Bike Brand,Bike Model\nCommuter,Trek,Domane\n")

    assert gear_utils.parse_gear_csv(str(bikes_file), BIKE) == [_bike("Commuter", "Trek", "Domane")]


def test_a_csv_with_the_wrong_headers_is_refused_as_bad_input(tmp_path):
    bikes_file = tmp_path / "gear.csv"
    bikes_file.write_text("Name,Brand\nCommuter,Trek\n")

    with pytest.raises(core_exceptions.InvalidInputError):
        gear_utils.parse_gear_csv(str(bikes_file), BIKE)


def test_shoes_headers_are_not_accepted_for_bikes(tmp_path):
    shoes_file = tmp_path / "gear.csv"
    shoes_file.write_text("Shoe Name,Shoe Brand,Shoe Model\nPegasus,Nike,Pegasus\n")

    with pytest.raises(core_exceptions.InvalidInputError):
        gear_utils.parse_gear_csv(str(shoes_file), BIKE)


def test_bike_transform_strips_whitespace():
    gears = gear_utils.transform_csv_bike_gear_to_schema_gear([_bike(" Trek ", " Trek ", " Domane ")], 1)

    assert [(g.nickname, g.brand, g.model) for g in gears] == [("Trek", "Trek", "Domane")]


def test_bike_transform_keeps_missing_brand_and_model_as_none():
    gears = gear_utils.transform_csv_bike_gear_to_schema_gear([_bike("Commuter"), _bike("Road", "", "Defy")], 1)

    assert [(g.brand, g.model) for g in gears] == [(None, None), (None, "Defy")]


def test_bike_transform_keeps_the_last_of_two_rows_with_one_name():
    gears = gear_utils.transform_csv_bike_gear_to_schema_gear([_bike("Road", "Giant"), _bike("Road", "Trek")], 1)

    assert [(g.nickname, g.brand) for g in gears] == [("Road", "Trek")]


def test_bike_transform_skips_a_row_without_a_name():
    gears = gear_utils.transform_csv_bike_gear_to_schema_gear([_bike("  ", "Giant"), _bike("MTB")], 1)

    assert [g.nickname for g in gears] == ["MTB"]


def test_shoe_transform_strips_whitespace():
    gears = gear_utils.transform_csv_shoe_gear_to_schema_gear(
        [_shoe(" Pegasus ", " Nike ", " Pegasus ")], 1, MagicMock()
    )

    assert [(g.nickname, g.brand, g.model) for g in gears] == [("Pegasus", "Nike", "Pegasus")]


def test_shoe_transform_keeps_a_trailing_plus_in_a_name():
    with patch.object(gear_utils.gears_integration, "get_gear_user", return_value=[]):
        gears = gear_utils.transform_csv_shoe_gear_to_schema_gear(
            [_shoe("Pegasus+ ", "Nike", "Pegasus")], 1, MagicMock()
        )

    assert gears[0].nickname == "Pegasus+"


@pytest.mark.parametrize("blank", [None, "", "  ", "+", "+ +"])
def test_shoe_transform_names_a_nameless_shoe(blank, monkeypatch):
    with patch.object(gear_utils.gears_integration, "get_gear_user", return_value=[]):
        gears = gear_utils.transform_csv_shoe_gear_to_schema_gear([_shoe(blank, "Nike", "Pegasus")], 1, MagicMock())

    assert [(g.nickname, g.brand) for g in gears] == [("Unnamed Shoe 1", "Nike")]


def test_nameless_shoes_avoid_the_users_gear_and_each_other(monkeypatch):
    existing = [SimpleNamespace(nickname="Unnamed Shoe 1")]
    with patch.object(gear_utils.gears_integration, "get_gear_user", return_value=existing) as lookup:
        gears = gear_utils.transform_csv_shoe_gear_to_schema_gear(
            [_shoe(None), _shoe(""), _shoe("Speed")], 1, MagicMock()
        )

    assert [g.nickname for g in gears] == ["Unnamed Shoe 2", "Unnamed Shoe 3", "Speed"]
    lookup.assert_called_once()


class TestMatchGear:
    def test_an_activity_without_strava_gear_matches_nothing(self):
        assert gear_utils.match_gear_for_activity(SimpleNamespace(strava_gear_id=None), []) is None

    def test_the_gear_with_the_same_strava_id_is_matched(self):
        gears = [SimpleNamespace(id=1, strava_gear_id="a"), SimpleNamespace(id=2, strava_gear_id="b")]

        assert gear_utils.match_gear_for_activity(SimpleNamespace(strava_gear_id="b"), gears) == 2


class TestSetActivitiesGear:
    def test_activities_are_assigned_and_the_caller_commits(self):
        db = MagicMock()
        activities = [SimpleNamespace(id=10, strava_gear_id="a"), SimpleNamespace(id=11, strava_gear_id=None)]
        gears = [SimpleNamespace(id=5, strava_gear_id="a")]
        with (
            patch.object(gear_utils.activity_integration, "list_user_activities_page", side_effect=[activities, []]),
            patch.object(gear_utils.gears_integration, "get_gear_user", return_value=gears),
            patch.object(gear_utils.activity_integration, "bulk_set_activities_gear") as bulk,
        ):
            assigned = gear_utils.set_activities_gear(7, db)

        assert assigned == 1
        bulk.assert_called_once_with(7, {10: 5}, db)
        db.commit.assert_not_called()

    def test_a_long_history_is_read_a_page_at_a_time_and_every_page_is_matched(self):
        size = gear_utils._ACTIVITY_PAGE_SIZE
        first = [SimpleNamespace(id=i, strava_gear_id="a") for i in range(size)]
        second = [SimpleNamespace(id=size, strava_gear_id="a")]
        gears = [SimpleNamespace(id=5, strava_gear_id="a")]
        with (
            patch.object(
                gear_utils.activity_integration, "list_user_activities_page", side_effect=[first, second]
            ) as listing,
            patch.object(gear_utils.gears_integration, "get_gear_user", return_value=gears),
            patch.object(gear_utils.activity_integration, "bulk_set_activities_gear") as bulk,
        ):
            assigned = gear_utils.set_activities_gear(7, MagicMock())

        assert assigned == size + 1
        assert [c.kwargs["page_number"] for c in listing.call_args_list] == [1, 2]
        assert all(c.kwargs["num_records"] == size for c in listing.call_args_list)
        assert len(bulk.call_args.args[1]) == size + 1

    def test_a_user_without_gear_reads_no_activities(self):
        with (
            patch.object(gear_utils.activity_integration, "list_user_activities_page") as listing,
            patch.object(gear_utils.gears_integration, "get_gear_user", return_value=[]),
            patch.object(gear_utils.activity_integration, "bulk_set_activities_gear") as bulk,
        ):
            assert gear_utils.set_activities_gear(7, MagicMock()) == 0

        listing.assert_not_called()
        bulk.assert_not_called()

    def test_no_matching_activity_writes_nothing(self):
        gears = [SimpleNamespace(id=5, strava_gear_id="a")]
        with (
            patch.object(
                gear_utils.activity_integration,
                "list_user_activities_page",
                side_effect=[[SimpleNamespace(id=1, strava_gear_id="zzz")]],
            ),
            patch.object(gear_utils.gears_integration, "get_gear_user", return_value=gears),
            patch.object(gear_utils.activity_integration, "bulk_set_activities_gear") as bulk,
        ):
            assert gear_utils.set_activities_gear(7, MagicMock()) == 0

        bulk.assert_not_called()


def _linked_sync(athlete, *, existing_ids=(), gear_error=None):
    """Run ``get_user_gear`` against a fake Strava; returns what it stored."""
    client = MagicMock()
    client.get_athlete.return_value = athlete
    if gear_error:
        client.get_gear.side_effect = gear_error
    else:
        client.get_gear.side_effect = lambda gear_id: SimpleNamespace(
            brand_name="B", model_name="M", name=f"n-{gear_id}"
        )
    rate_limits = MagicMock()
    rate_limits.is_rate_limited.return_value = False
    sessions = MagicMock()
    integrations = SimpleNamespace(strava_client_id="enc", strava_refresh_token="enc-refresh")
    with (
        patch.object(gear_utils.core_database, "SessionLocal", sessions),
        patch.object(gear_utils.strava_client_service, "refresh_user_strava_token"),
        patch.object(
            gear_utils.strava_client_service, "fetch_user_integrations_and_validate_token", return_value=integrations
        ),
        patch.object(gear_utils.strava_client_service, "get_client_id", return_value="42"),
        patch.object(gear_utils.strava_client_service, "create_strava_client", return_value=client),
        patch.object(
            gear_utils.gears_integration,
            "get_gear_by_strava_id",
            side_effect=lambda gear_id, user_id, db: object() if gear_id in existing_ids else None,
        ),
        patch.object(gear_utils.gears_integration, "create_multiple_gears") as create,
        patch.object(gear_utils.user_integrations_integration, "set_strava_sync_gear") as sync_pref,
        patch.object(gear_utils, "set_activities_gear", return_value=3) as assign,
    ):
        try:
            result = gear_utils.get_user_gear(7, rate_limits)
            error = None
        except core_exceptions.DomainError as err:
            result, error = None, err
    return result, error, create, sync_pref, assign, sessions, rate_limits


class TestGetUserGear:
    def test_new_gear_is_created_with_the_preference_and_the_assignments_in_one_commit(self):
        athlete = SimpleNamespace(bikes=[SimpleNamespace(id="b1")], shoes=[SimpleNamespace(id="s1")])

        result, error, create, sync_pref, assign, sessions, _ = _linked_sync(athlete)

        assert (result, error) == (True, None)
        created = create.call_args.args[0]
        assert [(g.strava_gear_id, g.gear_type) for g in created] == [("b1", BIKE), ("s1", SHOES)]
        sync_pref.assert_called_once()
        assign.assert_called_once()
        sessions.return_value.__enter__.return_value.commit.assert_called_once()

    def test_gear_the_user_already_has_is_not_fetched_again(self):
        athlete = SimpleNamespace(bikes=[SimpleNamespace(id="b1")], shoes=[])

        result, _error, create, *_ = _linked_sync(athlete, existing_ids={"b1"})

        assert result is True
        assert create.call_args.args[0] == []

    def test_an_athlete_without_gear_is_fine(self):
        result, error, *_ = _linked_sync(SimpleNamespace(bikes=None, shoes=None))

        assert (result, error) == (True, None)

    def test_an_unlinked_user_is_reported_not_crashed(self):
        with (
            patch.object(gear_utils.core_database, "SessionLocal"),
            patch.object(gear_utils.strava_client_service, "refresh_user_strava_token"),
            patch.object(
                gear_utils.strava_client_service, "fetch_user_integrations_and_validate_token", return_value=None
            ),
            patch.object(gear_utils.strava_client_service, "create_strava_client") as create_client,
        ):
            assert gear_utils.get_user_gear(7, MagicMock()) is False

        create_client.assert_not_called()

    def test_a_failed_fetch_stores_nothing_and_leaves_the_preference_off(self):
        athlete = SimpleNamespace(bikes=[SimpleNamespace(id="b1")], shoes=[])

        _result, error, create, sync_pref, *_ = _linked_sync(athlete, gear_error=RuntimeError("boom"))

        assert isinstance(error, core_exceptions.DependencyFailedError)
        create.assert_not_called()
        sync_pref.assert_not_called()

    def test_a_rejected_token_unlinks_the_account_and_stores_nothing(self):
        athlete = SimpleNamespace(bikes=[SimpleNamespace(id="b1")], shoes=[])
        with patch.object(gear_utils.strava_client_service, "handle_rejected_token") as handle:
            _result, error, create, *_ = _linked_sync(athlete, gear_error=AccessUnauthorized())

        assert isinstance(error, core_exceptions.DependencyFailedError)
        handle.assert_called_once()
        create.assert_not_called()

    def test_an_active_rate_limit_stops_the_sync_before_any_strava_call(self):
        client = MagicMock()
        rate_limits = MagicMock()
        rate_limits.is_rate_limited.return_value = True
        with (
            patch.object(gear_utils.core_database, "SessionLocal"),
            patch.object(gear_utils.strava_client_service, "refresh_user_strava_token"),
            patch.object(
                gear_utils.strava_client_service, "fetch_user_integrations_and_validate_token", return_value=object()
            ),
            patch.object(gear_utils.strava_client_service, "get_client_id", return_value="42"),
            patch.object(gear_utils.strava_client_service, "create_strava_client", return_value=client),
            pytest.raises(core_exceptions.TooManyRequestsError),
        ):
            gear_utils.get_user_gear(7, rate_limits)

        client.get_athlete.assert_not_called()
