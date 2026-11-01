"""Strava gear import takes the CSV as an upload and leaves nothing behind."""

import io
import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi import UploadFile

import core.exceptions as core_exceptions
import modules.gears.gear.schema as gears_schema
import modules.strava.gear_service as strava_gear_service


def _upload(content: bytes) -> UploadFile:
    return UploadFile(filename="whatever.csv", file=io.BytesIO(content))


BIKES = b"Bike Name,Bike Brand,Bike Model\nCommuter,Trek,Domane\n"
SHOES = b"Shoe Name,Shoe Brand,Shoe Model\nPegasus,Nike,Pegasus\n"


class TestImportBikes:
    def test_creates_the_listed_bikes_for_the_caller(self):
        db = MagicMock()
        with patch.object(strava_gear_service.gears_integration, "create_multiple_gears") as create:
            count = strava_gear_service.import_gear(_upload(BIKES), 7, gears_schema.GearType.BIKE, db)

        gears, user_id, passed_db = create.call_args.args
        assert [g.nickname for g in gears] == ["Commuter"]
        assert (user_id, passed_db, count) == (7, db, 1)
        db.commit.assert_called_once()

    def test_the_temp_file_is_removed_whether_or_not_it_parses(self):
        seen: list[str] = []
        real = strava_gear_service.parse_gear_csv

        def spy(path, gear_type):
            seen.append(path)
            return real(path, gear_type)

        with (
            patch.object(strava_gear_service, "parse_gear_csv", side_effect=spy),
            pytest.raises(core_exceptions.InvalidInputError),
        ):
            strava_gear_service.import_gear(_upload(b"Name\nx\n"), 7, gears_schema.GearType.BIKE, MagicMock())

        assert not os.path.exists(seen[0])

    def test_an_oversized_upload_is_refused(self):
        big = b"Bike Name,Bike Brand,Bike Model\n" + b"x," * (strava_gear_service._GEAR_CSV_MAX_BYTES)
        with pytest.raises(core_exceptions.PayloadTooLargeError):
            strava_gear_service.import_gear(_upload(big), 7, gears_schema.GearType.BIKE, MagicMock())

    def test_nothing_is_committed_when_the_file_lists_no_gear(self):
        db = MagicMock()
        with patch.object(strava_gear_service.gears_integration, "create_multiple_gears") as create:
            count = strava_gear_service.import_gear(
                _upload(b"Bike Name,Bike Brand,Bike Model\n"), 7, gears_schema.GearType.BIKE, db
            )

        create.assert_not_called()
        db.commit.assert_not_called()
        assert count == 0


class TestImportShoes:
    def test_creates_the_listed_shoes_for_the_caller(self):
        db = MagicMock()
        with (
            patch.object(strava_gear_service.gears_integration, "create_multiple_gears") as create,
            patch.object(strava_gear_service.gears_integration, "get_gear_user", return_value=[]),
        ):
            strava_gear_service.import_gear(_upload(SHOES), 7, gears_schema.GearType.SHOES, db)

        gears, user_id, passed_db = create.call_args.args
        assert [g.nickname for g in gears] == ["Pegasus"]
        assert (user_id, passed_db) == (7, db)
