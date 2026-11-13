"""The streams package's surface for ingestion and profile restore."""

import uuid
from unittest.mock import MagicMock, patch

import modules.activities.activity_streams.integration_service as integration

ORIGINAL = uuid.UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
OTHER = uuid.UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
NEW_ID = uuid.UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
_CRUD = "modules.activities.activity_streams.integration_service.activity_streams_crud"


class TestRestoreProfileRecords:
    def _activity(self) -> MagicMock:
        return MagicMock(id=NEW_ID)

    @patch(_CRUD)
    def test_an_archive_written_with_stored_zones_still_restores(self, mock_crud):
        """Exports from before zones were computed on read carry ``zone_percentages``."""
        record = {
            "id": "ffffffff-ffff-4fff-8fff-ffffffffffff",
            "activity_id": str(ORIGINAL),
            "stream_type": 1,
            "stream_waypoints": [{"hr": 120}],
            "strava_activity_stream_id": None,
            "zone_percentages": {"hr": {"zone_1": {"percent": 100.0}}},
        }

        restored = integration._restore_profile_records([record], ORIGINAL, self._activity(), MagicMock())

        assert restored == 1
        stored = mock_crud.create_activity_streams.call_args.args[0][0]
        assert stored.activity_id == NEW_ID
        assert not hasattr(stored, "zone_percentages")

    @patch(_CRUD)
    def test_a_record_for_another_activity_is_skipped(self, mock_crud):
        record = {"activity_id": str(OTHER), "stream_type": 1, "stream_waypoints": []}

        assert integration._restore_profile_records([record], ORIGINAL, self._activity(), MagicMock()) == 0
        mock_crud.create_activity_streams.assert_not_called()
