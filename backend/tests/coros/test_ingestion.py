"""COROS activities enter the shared ingestion contract without a duplicate key clash."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.ingestion_service as ingestion_service
import modules.activities.activity_ingestion.contracts as ingestion_contracts


def _activity(start: datetime) -> activity_contracts.ActivityCore:
    return activity_contracts.ActivityCore(
        user_id=uuid.uuid4(),
        distance=0,
        name="COROS activity",
        activity_type=1,
        start_time=start,
        end_time=start,
        coros_activity_id="label-1",
    )


class TestCorosDedupKey:
    """One COROS id can carry several sessions; the start time keeps them apart."""

    def test_the_key_uses_the_coros_id_and_start_time(self):
        start = datetime(2026, 1, 1, 10, tzinfo=UTC)
        activity = _activity(start)

        key = ingestion_service._derive_dedup_key(
            activity,
            activity_contracts.ImportSource(kind="coros"),
        )

        assert key == f"coros:label-1:{int(start.timestamp())}"

    def test_two_sessions_of_one_activity_get_distinct_keys(self):
        first = _activity(datetime(2026, 1, 1, 10, tzinfo=UTC))
        second = _activity(datetime(2026, 1, 1, 11, tzinfo=UTC))

        source = activity_contracts.ImportSource(kind="coros")
        assert ingestion_service._derive_dedup_key(first, source) != ingestion_service._derive_dedup_key(second, source)

    def test_the_source_kind_is_recorded(self):
        source = ingestion_contracts.CorosSource(activity_id="label-1")
        assert source.kind == "coros"
        assert source.activity_id == "label-1"
