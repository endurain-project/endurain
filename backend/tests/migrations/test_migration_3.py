"""Tests for migration 3: FIT-file backfill of laps, steps, titles and sets."""

import struct
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from fitdecode.utils import compute_crc
from sqlalchemy.orm import Session

import migrations.migration_3 as migration_3
import modules.activities.activity.contracts as activities_contracts

_SESSION_MESG_NUM = 18
_LAP_MESG_NUM = 19
_EXERCISE_TITLE_MESG_NUM = 264
_MESSAGE_INDEX_FIELD = 254
_UINT16 = 0x84


def _write_fit(path: Path, mesg_nums: list[int]) -> None:
    """Write a FIT file holding one message per number, each carrying only its message index.

    Args:
        path: Where to write the file.
        mesg_nums: The global message number of each message, in file order.
    """
    records = b""
    for index, mesg_num in enumerate(mesg_nums):
        records += struct.pack("<BBBHBBBB", 0x40, 0, 0, mesg_num, 1, _MESSAGE_INDEX_FIELD, 2, _UINT16)
        records += struct.pack("<BH", 0x00, index)
    header = struct.pack("<BBHI4s", 14, 0x20, 2132, len(records), b".FIT")
    header += struct.pack("<H", compute_crc(header))
    body = header + records
    path.write_bytes(body + struct.pack("<H", compute_crc(body)))


def _activity() -> activities_contracts.ActivityMigrationRef:
    """Return the activity a migrated FIT file belongs to.

    Returns:
        The activity reference.
    """
    return activities_contracts.ActivityMigrationRef(
        id=1,
        user_id=1,
        start_time=datetime(2024, 1, 1, tzinfo=UTC),
        end_time=datetime(2024, 1, 1, 1, tzinfo=UTC),
        strava_activity_id=None,
        garminconnect_activity_id=None,
    )


class TestProcessFitFile:
    def test_skips_exercise_title_without_step_name(self, tmp_path: Path):
        fit_path = tmp_path / "activity.fit"
        _write_fit(fit_path, [_EXERCISE_TITLE_MESG_NUM])
        db = MagicMock(spec=Session)

        migration_3.process_fit_file(_activity(), str(fit_path), db)

        db.execute.assert_not_called()

    def test_skips_lap_without_start_time_in_a_multi_session_file(self, tmp_path: Path):
        fit_path = tmp_path / "activity.fit"
        _write_fit(fit_path, [_SESSION_MESG_NUM, _SESSION_MESG_NUM, _LAP_MESG_NUM])
        db = MagicMock(spec=Session)

        migration_3.process_fit_file(_activity(), str(fit_path), db)

        db.add_all.assert_not_called()
