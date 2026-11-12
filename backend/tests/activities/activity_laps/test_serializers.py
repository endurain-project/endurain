import uuid
from unittest.mock import MagicMock, patch

_ACTIVITY_ID = uuid.UUID("00000000-0000-4000-8000-000000000005")


class TestToReadSchema:
    @patch("modules.activities.activity_laps.serializers.activity_laps_schema.ActivityLapsRead.model_validate")
    def test_success(self, mock_validate):
        import modules.activities.activity_laps.serializers as serializers

        mock_schema = MagicMock()
        mock_validate.return_value = mock_schema
        orm_lap = MagicMock()
        result = serializers.to_read_schema(orm_lap)
        mock_validate.assert_called_once_with(orm_lap)
        assert result == mock_schema


class TestToOrm:
    def test_missing_keys_become_none(self):
        import modules.activities.activity_laps.serializers as serializers

        lap = serializers.to_orm({"total_distance": 10}, activity_id=_ACTIVITY_ID)
        assert lap.activity_id == _ACTIVITY_ID
        assert lap.total_distance == 10
        assert lap.avg_power is None
