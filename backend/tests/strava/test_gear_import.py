"""Strava gear import takes the CSV as an upload and leaves nothing behind."""

import io
import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi import UploadFile

import core.exceptions as core_exceptions
import modules.strava.gear_service as strava_gear_service


def _upload(content: bytes) -> UploadFile:
    return UploadFile(filename="whatever.csv", file=io.BytesIO(content))


BIKES = b"Bike Name,Bike Brand,Bike Model\nCommuter,Trek,Domane\n"
SHOES = b"Shoe Name,Shoe Brand,Shoe Model\nPegasus,Nike,Pegasus\n"


class TestImportBikes:
    def test_creates_the_listed_bikes_for_the_caller(self):
        db = MagicMock()
        with patch.object(strava_gear_service.gears_integration, "create_multiple_gears") as create:
            strava_gear_service.import_bikes(_upload(BIKES), 7, db)

        gears, user_id, passed_db = create.call_args.args
        assert [g.nickname for g in gears] == ["Commuter"]
        assert (user_id, passed_db) == (7, db)

    def test_the_temp_file_is_removed_whether_or_not_it_parses(self):
        seen: list[str] = []
        real = strava_gear_service.iterate_over_bikes_csv

        def spy(path):
            seen.append(path)
            return real(path)

        with (
            patch.object(strava_gear_service, "iterate_over_bikes_csv", side_effect=spy),
            pytest.raises(core_exceptions.DependencyFailedError),
        ):
            strava_gear_service.import_bikes(_upload(b"Name\nx\n"), 7, MagicMock())

        assert not os.path.exists(seen[0])

    def test_an_oversized_upload_is_refused(self):
        big = b"Bike Name,Bike Brand,Bike Model\n" + b"x," * (strava_gear_service._GEAR_CSV_MAX_BYTES)
        with pytest.raises(core_exceptions.PayloadTooLargeError):
            strava_gear_service.import_bikes(_upload(big), 7, MagicMock())


class TestImportShoes:
    def test_creates_the_listed_shoes_for_the_caller(self):
        db = MagicMock()
        with (
            patch.object(strava_gear_service.gears_integration, "create_multiple_gears") as create,
            patch.object(strava_gear_service, "transform_csv_shoe_gear_to_schema_gear") as transform,
        ):
            transform.return_value = ["shoe"]
            strava_gear_service.import_shoes(_upload(SHOES), 7, db)

        create.assert_called_once_with(["shoe"], 7, db)
