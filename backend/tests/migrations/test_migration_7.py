from unittest.mock import MagicMock, patch

import migrations.migration_7 as migration_7


def test_process_migration_7_populates_missing_hr_zone_percentages(mock_db):
    stream = MagicMock(
        id=1,
        activity_id=10,
        stream_type=1,
        zone_percentages=None,
        stream_waypoints=[{"hr": 120}],
        strava_activity_stream_id=None,
    )

    mock_activity = MagicMock(user_id=1)
    mock_user = MagicMock(max_heart_rate=200)

    with (
        patch(
            "migrations.migration_7.activity_streams_crud.get_hr_streams_without_zone_percentages",
            side_effect=[[stream], []],
        ),
        patch(
            "migrations.migration_7.activity_crud.get_activity_by_id",
            return_value=mock_activity,
        ),
        patch(
            "migrations.migration_7.users_crud.get_user_by_id",
            return_value=mock_user,
        ),
        patch(
            "migrations.migration_7.activity_streams_utils.resolve_max_heart_rate",
            return_value=200,
        ),
        patch(
            "migrations.migration_7.activity_streams_utils.compute_hr_zone_breakdown_sync",
            return_value={"zone_1": {}},
        ),
        patch(
            "migrations.migration_7.activity_streams_crud.backfill_zone_percentages_for_missing_hr_streams",
            return_value=True,
        ) as mock_backfill,
        patch("migrations.migration_7.migrations_crud.set_migration_as_executed") as mock_set_executed,
    ):
        migration_7.process_migration_7(mock_db)

    mock_backfill.assert_called_once()
    mock_set_executed.assert_called_once_with(7, mock_db)


def test_process_migration_7_skips_existing_zone_percentages(mock_db):
    existing_payload = {"hr": {"zone_1": {"percent": 50.0}}}
    stream = MagicMock(
        id=2,
        activity_id=20,
        stream_type=1,
        zone_percentages=existing_payload,
        stream_waypoints=[{"hr": 100}],
        strava_activity_stream_id=None,
    )

    with (
        patch(
            "migrations.migration_7.activity_streams_crud.get_hr_streams_without_zone_percentages",
            side_effect=[[stream], []],
        ),
        patch(
            "migrations.migration_7.activity_crud.get_activity_by_id",
            return_value=MagicMock(user_id=1),
        ),
        patch(
            "migrations.migration_7.users_crud.get_user_by_id",
            return_value=MagicMock(max_heart_rate=200),
        ),
        patch(
            "migrations.migration_7.activity_streams_utils.resolve_max_heart_rate",
            return_value=None,
        ),
        patch(
            "migrations.migration_7.activity_streams_crud.backfill_zone_percentages_for_missing_hr_streams",
            return_value=True,
        ) as mock_backfill,
        patch("migrations.migration_7.migrations_crud.set_migration_as_executed") as mock_set_executed,
    ):
        migration_7.process_migration_7(mock_db)

    # Should not be called because no computed_streams
    mock_backfill.assert_not_called()
    mock_set_executed.assert_called_once_with(7, mock_db)
