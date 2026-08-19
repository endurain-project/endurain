"""Tests for the core activity ingestion service (store_parsed_activity)."""

from unittest.mock import MagicMock, patch

import pytest

import core.exceptions as core_exceptions


def _parsed(**overrides):
    """Build a ParsedActivity with a mock activity and overridable children.

    The default activity carries no provider ids (an ``"upload"``), so
    ``_derive_dedup_key`` yields ``None`` and the idempotency no-op path stays
    inert unless a test opts in via ``source``/``activity`` overrides.
    """
    import modules.activities.activity.contracts as schema

    data = {
        "activity": MagicMock(strava_activity_id=None, garminconnect_activity_id=None, user_id=3),
        "streams": [],
        "laps": None,
        "sets": None,
        "workout_steps": None,
        "source": schema.ImportSource(kind="upload"),
    }
    data.update(overrides)
    return schema.ParsedActivity(**data)


class TestStoreParsedActivity:
    @patch("modules.activities.activity.ingestion_service.activity_event_publishers")
    @patch("modules.activities.activity.ingestion_service.activity_streams_integration")
    @patch("modules.activities.activity.ingestion_service.activities_crud")
    def test_stores_activity_and_streams(self, mock_crud, mock_streams_crud, mock_pub):
        import modules.activities.activity.contracts as schema
        import modules.activities.activity.ingestion_service as ingestion_service

        created = MagicMock(id=7, user_id=3)
        mock_crud.create_activity = MagicMock(return_value=created)
        mock_streams_crud.store_streams = MagicMock()

        parsed = _parsed(streams=[schema.ParsedStream(stream_type=1, stream_waypoints=[{"hr": 100}])])

        result = ingestion_service.store_parsed_activity(parsed, MagicMock())

        assert result is created
        mock_crud.create_activity.assert_called_once()
        # The stream was converted to an ActivityStreamsCreate carrying the new id.
        mock_streams_crud.store_streams.assert_called_once()
        built_streams = mock_streams_crud.store_streams.call_args.args[0]
        assert built_streams[0].activity_id == 7
        assert built_streams[0].stream_type == 1
        mock_pub.publish_activity_created.assert_called_once()
        assert mock_pub.publish_activity_created.call_args.args[:2] == (7, 3)

    @patch("modules.activities.activity.ingestion_service.activity_event_publishers")
    @patch("modules.activities.activity.ingestion_service.activity_streams_integration")
    @patch("modules.activities.activity.ingestion_service.activities_crud")
    def test_no_streams_skips_stream_creation(self, mock_crud, mock_streams_crud, mock_pub):
        import modules.activities.activity.ingestion_service as ingestion_service

        mock_crud.create_activity = MagicMock(return_value=MagicMock(id=1, user_id=1))
        mock_streams_crud.store_streams = MagicMock()

        ingestion_service.store_parsed_activity(_parsed(), MagicMock())

        mock_streams_crud.store_streams.assert_not_called()

    @patch("modules.activities.activity.ingestion_service.activity_event_publishers")
    @patch("modules.activities.activity.ingestion_service.activity_workout_steps_integration")
    @patch("modules.activities.activity.ingestion_service.activity_sets_integration")
    @patch("modules.activities.activity.ingestion_service.activity_laps_integration")
    @patch("modules.activities.activity.ingestion_service.activities_crud")
    def test_persists_laps_sets_and_steps(self, mock_crud, mock_laps, mock_sets, mock_steps, mock_pub):
        import modules.activities.activity.ingestion_service as ingestion_service

        mock_crud.create_activity = MagicMock(return_value=MagicMock(id=9, user_id=1))

        parsed = _parsed(laps=[{"a": 1}], sets=[{"b": 2}], workout_steps=[{"c": 3}])
        ingestion_service.store_parsed_activity(parsed, MagicMock())

        mock_laps.store_laps.assert_called_once()
        mock_sets.store_sets.assert_called_once()
        mock_steps.store_workout_steps.assert_called_once()

    @patch("modules.activities.activity.ingestion_service.activities_crud")
    def test_raises_when_activity_none(self, mock_crud):
        import modules.activities.activity.ingestion_service as ingestion_service

        mock_crud.create_activity = MagicMock(return_value=None)

        with pytest.raises(core_exceptions.ProcessingError) as exc:
            ingestion_service.store_parsed_activity(_parsed(), MagicMock())
        assert exc.value.status_code == 500

    @patch("modules.activities.activity.ingestion_service.activities_crud")
    def test_raises_when_id_none(self, mock_crud):
        import modules.activities.activity.ingestion_service as ingestion_service

        mock_crud.create_activity = MagicMock(return_value=MagicMock(id=None))

        with pytest.raises(core_exceptions.ProcessingError) as exc:
            ingestion_service.store_parsed_activity(_parsed(), MagicMock())
        assert exc.value.status_code == 500

    @patch("modules.activities.activity.ingestion_service.activity_event_publishers")
    @patch("modules.activities.activity.ingestion_service.activity_streams_integration")
    @patch("modules.activities.activity.ingestion_service.activities_crud")
    def test_persists_children_and_activity_without_committing(self, mock_crud, mock_streams_crud, mock_pub):
        import modules.activities.activity.contracts as schema
        import modules.activities.activity.ingestion_service as ingestion_service

        mock_crud.create_activity = MagicMock(return_value=MagicMock(id=7, user_id=3, is_hidden=False))
        db = MagicMock()

        parsed = _parsed(streams=[schema.ParsedStream(stream_type=1, stream_waypoints=[{"hr": 1}])])
        ingestion_service.store_parsed_activity(parsed, db)

        # Activity + children are staged with commit=False so they land in ONE
        # transaction; the publish seam owns the single commit (commit=db.commit).
        assert mock_crud.create_activity.call_args.kwargs["commit"] is False
        assert mock_streams_crud.store_streams.call_args.kwargs["commit"] is False
        assert mock_pub.publish_activity_created.call_args.kwargs["commit"] is db.commit

    @patch("modules.activities.activity.ingestion_service.activity_event_publishers")
    @patch("modules.activities.activity.ingestion_service.activity_streams_integration")
    @patch("modules.activities.activity.ingestion_service.activities_crud")
    def test_rolls_back_and_raises_when_child_fails(self, mock_crud, mock_streams_crud, mock_pub):
        from sqlalchemy.exc import SQLAlchemyError

        import modules.activities.activity.contracts as schema
        import modules.activities.activity.ingestion_service as ingestion_service

        mock_crud.create_activity = MagicMock(return_value=MagicMock(id=5, user_id=2, is_hidden=False))
        mock_streams_crud.store_streams = MagicMock(side_effect=SQLAlchemyError("boom"))
        db = MagicMock()

        parsed = _parsed(streams=[schema.ParsedStream(stream_type=1, stream_waypoints=[{"hr": 100}])])

        with pytest.raises(core_exceptions.ProcessingError) as exc:
            ingestion_service.store_parsed_activity(parsed, db)
        assert exc.value.status_code == 500
        # The whole unit of work rolls back (no partial activity) and no event is
        # published for a store that never committed.
        db.rollback.assert_called_once()
        mock_pub.publish_activity_created.assert_not_called()

    @patch("modules.activities.activity.ingestion_service.activity_event_publishers")
    @patch("modules.activities.activity.ingestion_service.activity_streams_integration")
    @patch("modules.activities.activity.ingestion_service.activities_crud")
    def test_noop_when_dedup_key_already_ingested(self, mock_crud, mock_streams_crud, mock_pub):
        import modules.activities.activity.contracts as schema
        import modules.activities.activity.ingestion_service as ingestion_service

        existing = MagicMock(id=42, user_id=3)
        mock_crud.get_activity_by_dedup_key = MagicMock(return_value=existing)
        mock_crud.create_activity = MagicMock()
        db = MagicMock()

        parsed = _parsed(
            streams=[schema.ParsedStream(stream_type=1, stream_waypoints=[{"hr": 1}])],
            source=schema.ImportSource(kind="strava", dedup_key="strava:123"),
        )

        result = ingestion_service.store_parsed_activity(parsed, db)

        # Re-import of an already-ingested dedup_key is a true no-op: the existing
        # activity is returned and nothing is created, staged, or published.
        assert result is existing
        mock_crud.get_activity_by_dedup_key.assert_called_once_with("strava:123", 3, db)
        mock_crud.create_activity.assert_not_called()
        mock_streams_crud.store_streams.assert_not_called()
        mock_pub.publish_activity_created.assert_not_called()

    @patch("modules.activities.activity.ingestion_service.activity_event_publishers")
    @patch("modules.activities.activity.ingestion_service.activity_streams_integration")
    @patch("modules.activities.activity.ingestion_service.activities_crud")
    def test_losing_the_insert_race_returns_the_winner(self, mock_crud, mock_streams_crud, mock_pub):
        """The pre-insert dedup check is read-then-write, so concurrent imports race.

        The unique index on ``(user_id, dedup_key)`` is what actually guarantees
        idempotency. Losing the race means the other worker stored the activity —
        exactly the outcome the caller wanted — so it must be a no-op, not a 500.
        """
        import sqlalchemy.exc

        import modules.activities.activity.contracts as schema
        import modules.activities.activity.ingestion_service as ingestion_service

        winner = MagicMock(id=42, user_id=3)
        # Not found before the insert, found after the conflict — the race.
        mock_crud.get_activity_by_dedup_key = MagicMock(side_effect=[None, winner])
        mock_crud.create_activity = MagicMock(
            side_effect=sqlalchemy.exc.IntegrityError("INSERT", {}, Exception("duplicate key"))
        )
        db = MagicMock()

        parsed = _parsed(source=schema.ImportSource(kind="strava", dedup_key="strava:123"))

        result = ingestion_service.store_parsed_activity(parsed, db)

        assert result is winner
        db.rollback.assert_called_once()
        mock_pub.publish_activity_created.assert_not_called()

    @patch("modules.activities.activity.ingestion_service.activity_event_publishers")
    @patch("modules.activities.activity.ingestion_service.activity_streams_integration")
    @patch("modules.activities.activity.ingestion_service.activities_crud")
    def test_an_unrelated_integrity_error_still_fails(self, mock_crud, mock_streams_crud, mock_pub):
        """A constraint violation that is not the dedup race must not be swallowed."""
        import sqlalchemy.exc

        import modules.activities.activity.contracts as schema
        import modules.activities.activity.ingestion_service as ingestion_service

        # Nothing found on the retry -> this was not a dedup conflict.
        mock_crud.get_activity_by_dedup_key = MagicMock(side_effect=[None, None])
        mock_crud.create_activity = MagicMock(
            side_effect=sqlalchemy.exc.IntegrityError("INSERT", {}, Exception("fk violation"))
        )
        db = MagicMock()

        parsed = _parsed(source=schema.ImportSource(kind="strava", dedup_key="strava:123"))

        with pytest.raises(core_exceptions.ProcessingError) as exc:
            ingestion_service.store_parsed_activity(parsed, db)

        assert exc.value.status_code == 500
        db.rollback.assert_called_once()

    @patch("modules.activities.activity.ingestion_service.activity_event_publishers")
    @patch("modules.activities.activity.ingestion_service.activity_streams_integration")
    @patch("modules.activities.activity.ingestion_service.activities_crud")
    def test_integrity_error_without_a_dedup_key_still_fails(self, mock_crud, mock_streams_crud, mock_pub):
        """With no dedup key there is no race to recover from."""
        import sqlalchemy.exc

        import modules.activities.activity.ingestion_service as ingestion_service

        mock_crud.get_activity_by_dedup_key = MagicMock(return_value=None)
        mock_crud.create_activity = MagicMock(
            side_effect=sqlalchemy.exc.IntegrityError("INSERT", {}, Exception("boom"))
        )
        activity = MagicMock(strava_activity_id=None, garminconnect_activity_id=None, user_id=3)
        db = MagicMock()

        with pytest.raises(core_exceptions.ProcessingError) as exc:
            ingestion_service.store_parsed_activity(_parsed(activity=activity), db)

        assert exc.value.status_code == 500
        db.rollback.assert_called_once()

    @patch("modules.activities.activity.ingestion_service.activity_event_publishers")
    @patch("modules.activities.activity.ingestion_service.activity_streams_integration")
    @patch("modules.activities.activity.ingestion_service.activities_crud")
    def test_derives_and_passes_strava_dedup_key(self, mock_crud, mock_streams_crud, mock_pub):
        import modules.activities.activity.contracts as schema
        import modules.activities.activity.ingestion_service as ingestion_service

        mock_crud.get_activity_by_dedup_key = MagicMock(return_value=None)
        mock_crud.create_activity = MagicMock(return_value=MagicMock(id=7, user_id=3, is_hidden=False))

        activity = MagicMock(strava_activity_id=123, garminconnect_activity_id=None, user_id=3)
        parsed = _parsed(activity=activity, source=schema.ImportSource(kind="upload"))

        ingestion_service.store_parsed_activity(parsed, MagicMock())

        # The key is derived from the activity's Strava id (no explicit source key)
        # and forwarded to create_activity for persistence on the new row.
        mock_crud.get_activity_by_dedup_key.assert_called_once()
        assert mock_crud.get_activity_by_dedup_key.call_args.args[0] == "strava:123"
        assert mock_crud.create_activity.call_args.kwargs["dedup_key"] == "strava:123"

    @patch("modules.activities.activity.ingestion_service.activity_event_publishers")
    @patch("modules.activities.activity.ingestion_service.activity_streams_integration")
    @patch("modules.activities.activity.ingestion_service.activities_crud")
    def test_derives_garmin_dedup_key_when_no_strava(self, mock_crud, mock_streams_crud, mock_pub):
        import modules.activities.activity.contracts as schema
        import modules.activities.activity.ingestion_service as ingestion_service

        mock_crud.get_activity_by_dedup_key = MagicMock(return_value=None)
        mock_crud.create_activity = MagicMock(return_value=MagicMock(id=8, user_id=3, is_hidden=False))

        activity = MagicMock(strava_activity_id=None, garminconnect_activity_id=456, user_id=3)
        parsed = _parsed(activity=activity, source=schema.ImportSource(kind="garmin"))

        ingestion_service.store_parsed_activity(parsed, MagicMock())

        assert mock_crud.create_activity.call_args.kwargs["dedup_key"] == "garmin:456"

    @patch("modules.activities.activity.ingestion_service.activity_event_publishers")
    @patch("modules.activities.activity.ingestion_service.activity_streams_integration")
    @patch("modules.activities.activity.ingestion_service.activities_crud")
    def test_noop_on_existing_content_hash(self, mock_crud, mock_streams_crud, mock_pub):
        from datetime import UTC, datetime

        import modules.activities.activity.contracts as schema
        import modules.activities.activity.ingestion_service as ingestion_service

        existing = MagicMock(id=99, user_id=3)
        mock_crud.get_activity_by_dedup_key = MagicMock(return_value=existing)
        mock_crud.create_activity = MagicMock()

        activity = MagicMock(
            strava_activity_id=None,
            garminconnect_activity_id=None,
            user_id=3,
            start_time=datetime(2024, 1, 1, tzinfo=UTC),
        )
        parsed = _parsed(activity=activity, source=schema.ImportSource(kind="upload", content_hash="abc"))

        result = ingestion_service.store_parsed_activity(parsed, MagicMock())

        # A file-content dedup key (file:{hash}:{start}) makes re-import of the
        # same file a true no-op — the existing activity is returned, nothing is
        # created or published.
        assert result is existing
        epoch = int(datetime(2024, 1, 1, tzinfo=UTC).timestamp())
        args = mock_crud.get_activity_by_dedup_key.call_args.args
        assert args[0] == f"file:abc:{epoch}"
        assert args[1] == 3
        mock_crud.create_activity.assert_not_called()
        mock_pub.publish_activity_created.assert_not_called()


class TestDeriveDedupKey:
    def test_prefers_strava_over_garmin(self):
        import modules.activities.activity.ingestion_service as ingestion_service

        activity = MagicMock(strava_activity_id=1, garminconnect_activity_id=2)
        assert ingestion_service._derive_dedup_key(activity, None) == "strava:1"

    def test_falls_back_to_garmin(self):
        import modules.activities.activity.ingestion_service as ingestion_service

        activity = MagicMock(strava_activity_id=None, garminconnect_activity_id=2)
        assert ingestion_service._derive_dedup_key(activity, None) == "garmin:2"

    def test_garmin_key_is_salted_with_start_time(self):
        """One multi-activity Garmin .fit yields several activities sharing an id.

        Without the salt every activity after the first collided with the first
        one's key and was silently discarded as already-ingested.
        """
        from datetime import UTC, datetime

        import modules.activities.activity.ingestion_service as ingestion_service

        first = MagicMock(
            strava_activity_id=None,
            garminconnect_activity_id=999,
            start_time=datetime(2024, 1, 1, 10, tzinfo=UTC),
        )
        second = MagicMock(
            strava_activity_id=None,
            garminconnect_activity_id=999,
            start_time=datetime(2024, 1, 1, 12, tzinfo=UTC),
        )

        k1 = ingestion_service._derive_dedup_key(first, None)
        k2 = ingestion_service._derive_dedup_key(second, None)
        assert k1 != k2
        assert k1.startswith("garmin:999:")
        assert k2.startswith("garmin:999:")

    def test_garmin_key_is_stable_for_the_same_activity(self):
        from datetime import UTC, datetime

        import modules.activities.activity.ingestion_service as ingestion_service

        def _activity():
            return MagicMock(
                strava_activity_id=None,
                garminconnect_activity_id=999,
                start_time=datetime(2024, 1, 1, 10, tzinfo=UTC),
            )

        assert ingestion_service._derive_dedup_key(_activity(), None) == ingestion_service._derive_dedup_key(
            _activity(), None
        )

    def test_none_for_plain_upload_without_hash(self):
        import modules.activities.activity.contracts as schema
        import modules.activities.activity.ingestion_service as ingestion_service

        activity = MagicMock(strava_activity_id=None, garminconnect_activity_id=None)
        assert ingestion_service._derive_dedup_key(activity, schema.ImportSource(kind="upload")) is None

    def test_content_hash_key_when_no_provider_id(self):
        from datetime import UTC, datetime

        import modules.activities.activity.contracts as schema
        import modules.activities.activity.ingestion_service as ingestion_service

        activity = MagicMock(
            strava_activity_id=None,
            garminconnect_activity_id=None,
            start_time=datetime(2024, 1, 1, tzinfo=UTC),
        )
        source = schema.ImportSource(kind="upload", content_hash="abc123")
        epoch = int(datetime(2024, 1, 1, tzinfo=UTC).timestamp())
        assert ingestion_service._derive_dedup_key(activity, source) == f"file:abc123:{epoch}"

    def test_provider_id_wins_over_content_hash(self):
        import modules.activities.activity.contracts as schema
        import modules.activities.activity.ingestion_service as ingestion_service

        activity = MagicMock(strava_activity_id=9, garminconnect_activity_id=None)
        source = schema.ImportSource(kind="upload", content_hash="abc123")
        assert ingestion_service._derive_dedup_key(activity, source) == "strava:9"

    def test_multi_activity_distinct_start_times_yield_distinct_keys(self):
        from datetime import UTC, datetime

        import modules.activities.activity.contracts as schema
        import modules.activities.activity.ingestion_service as ingestion_service

        # Two activities parsed from the SAME multi-activity file share the file
        # hash but differ by start time, so the start-time salt keeps their keys
        # distinct (they must not dedup against each other).
        source = schema.ImportSource(kind="upload", content_hash="deadbeef")
        a1 = MagicMock(
            strava_activity_id=None, garminconnect_activity_id=None, start_time=datetime(2024, 1, 1, 10, tzinfo=UTC)
        )
        a2 = MagicMock(
            strava_activity_id=None, garminconnect_activity_id=None, start_time=datetime(2024, 1, 1, 12, tzinfo=UTC)
        )
        k1 = ingestion_service._derive_dedup_key(a1, source)
        k2 = ingestion_service._derive_dedup_key(a2, source)
        assert k1 != k2
        assert k1.startswith("file:deadbeef:")
        assert k2.startswith("file:deadbeef:")
