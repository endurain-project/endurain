"""Tests for Strava gear utility functions."""

from __future__ import annotations

from unittest.mock import Mock

import modules.strava.gear_utils as gear_utils


def test_shoe_csv_uses_strava_import_directory(monkeypatch, tmp_path):
    """Shoe CSV imports read from the Strava export directory."""
    strava_import_dir = tmp_path / "strava_import"
    generic_import_dir = tmp_path / "bulk_import"
    shoes_file_path = strava_import_dir / "shoes.csv"
    read_paths = []

    monkeypatch.setattr(gear_utils.core_config, "STRAVA_BULK_IMPORT_DIR", str(strava_import_dir))
    monkeypatch.setattr(gear_utils.core_config, "FILES_BULK_IMPORT_DIR", str(generic_import_dir))
    monkeypatch.setattr(gear_utils.os.path, "isfile", lambda path: path == str(shoes_file_path))

    def read_csv(path):
        read_paths.append(path)
        return iter([{"Shoe Name": "Pegasus", "Shoe Brand": "Nike", "Shoe Model": "Pegasus"}])

    monkeypatch.setattr(gear_utils.core_text_imports, "read_bounded_csv", read_csv)

    shoes = gear_utils.iterate_over_shoes_csv()

    assert shoes == [{"Shoe Name": "Pegasus", "Shoe Brand": "Nike", "Shoe Model": "Pegasus"}]
    assert read_paths == [str(shoes_file_path)]


def test_bike_transform_strips_whitespace():
    """Bike brand, model, and nickname are stripped of whitespace."""
    bikes_dict = {
        " Trek ": {"Bike Brand": " Trek ", "Bike Model": " Domane "},
    }
    gears = gear_utils.transform_csv_bike_gear_to_schema_gear(bikes_dict, 1)
    assert len(gears) == 1
    assert gears[0].brand == "Trek"
    assert gears[0].model == "Domane"
    assert gears[0].nickname == "Trek"


def test_bike_transform_none_fields():
    """None brand/model are preserved as None, not crashed."""
    bikes_dict = {
        "Commuter": {"Bike Brand": None, "Bike Model": None},
    }
    gears = gear_utils.transform_csv_bike_gear_to_schema_gear(bikes_dict, 1)
    assert len(gears) == 1
    assert gears[0].brand is None
    assert gears[0].model is None
    assert gears[0].nickname == "Commuter"


def test_bike_transform_empty_string_brand():
    """Empty string brand is handled safely."""
    bikes_dict = {
        "Road Bike": {"Bike Brand": "", "Bike Model": "Defy"},
    }
    gears = gear_utils.transform_csv_bike_gear_to_schema_gear(bikes_dict, 1)
    assert len(gears) == 1
    assert gears[0].brand is None
    assert gears[0].model == "Defy"


def test_bike_transform_multiple_bikes():
    """Multiple bikes are all processed with stripping."""
    bikes_dict = {
        "Road": {"Bike Brand": "Giant ", "Bike Model": " TCR "},
        "MTB": {"Bike Brand": " Specialized", "Bike Model": "Stumpjumper"},
    }
    gears = gear_utils.transform_csv_bike_gear_to_schema_gear(bikes_dict, 1)
    assert len(gears) == 2
    assert gears[0].brand == "Giant"
    assert gears[0].model == "TCR"
    assert gears[1].brand == "Specialized"
    assert gears[1].model == "Stumpjumper"


def test_shoe_transform_strips_whitespace():
    """Shoe brand, model, and name are stripped of whitespace."""
    shoes_list = [
        {"Shoe Name": " Pegasus ", "Shoe Brand": " Nike ", "Shoe Model": " Pegasus "},
    ]
    gears = gear_utils.transform_csv_shoe_gear_to_schema_gear(shoes_list, 1, Mock())
    assert len(gears) == 1
    assert gears[0].brand == "Nike"
    assert gears[0].model == "Pegasus"
    assert gears[0].nickname == "Pegasus"


def test_shoe_transform_none_brand_model():
    """None brand/model are preserved as None, not crashed."""
    shoes_list = [
        {"Shoe Name": "Speedsters", "Shoe Brand": None, "Shoe Model": None},
    ]
    gears = gear_utils.transform_csv_shoe_gear_to_schema_gear(shoes_list, 1, Mock())
    assert len(gears) == 1
    assert gears[0].brand is None
    assert gears[0].model is None
    assert gears[0].nickname == "Speedsters"


def test_shoe_transform_trailing_plus_encoded(monkeypatch):
    """Shoe name trailing whitespace is stripped."""
    monkeypatch.setattr(gear_utils.core_config, "STRAVA_BULK_IMPORT_SHOES_UNNAMED_SHOE", "Unnamed Shoe ")
    monkeypatch.setattr(gear_utils.gears_crud, "get_gear_user_by_nickname", lambda uid, name, db: None)
    monkeypatch.setattr(gear_utils, "logger", Mock())

    shoes_list = [
        {"Shoe Name": "Pegasus+ ", "Shoe Brand": "Nike", "Shoe Model": "Pegasus"},
    ]
    gears = gear_utils.transform_csv_shoe_gear_to_schema_gear(shoes_list, 1, Mock())
    assert len(gears) == 1
    assert gears[0].nickname == "Pegasus+"


def test_shoe_transform_blank_name(monkeypatch):
    """Blank shoe name gets renamed to default name."""
    monkeypatch.setattr(gear_utils.core_config, "STRAVA_BULK_IMPORT_SHOES_UNNAMED_SHOE", "Unnamed Shoe ")
    monkeypatch.setattr(gear_utils.gears_crud, "get_gear_user_by_nickname", lambda uid, name, db: None)
    logger = Mock()
    monkeypatch.setattr(gear_utils, "logger", logger)

    shoes_list = [
        {"Shoe Name": None, "Shoe Brand": "Nike", "Shoe Model": "Pegasus"},
    ]
    gears = gear_utils.transform_csv_shoe_gear_to_schema_gear(shoes_list, 1, Mock())
    assert len(gears) == 1
    assert gears[0].nickname == "Unnamed Shoe 1"
    assert gears[0].brand == "Nike"
    assert gears[0].model == "Pegasus"
    assert len(logger.method_calls) == 1


def test_shoe_transform_multiple_shoes():
    """Multiple shoes are all processed with stripping."""
    shoes_list = [
        {"Shoe Name": " Speed ", "Shoe Brand": " Nike", "Shoe Model": " Vaporfly "},
        {"Shoe Name": "Trail  ", "Shoe Brand": " Hoka ", "Shoe Model": " Speedgoat"},
    ]
    gears = gear_utils.transform_csv_shoe_gear_to_schema_gear(shoes_list, 1, Mock())
    assert len(gears) == 2
    assert gears[0].brand == "Nike"
    assert gears[0].nickname == "Speed"
    assert gears[1].brand == "Hoka"
    assert gears[1].nickname == "Trail"


def test_shoe_transform_empty_string_name(monkeypatch):
    """Empty string shoe name gets renamed."""
    monkeypatch.setattr(gear_utils.core_config, "STRAVA_BULK_IMPORT_SHOES_UNNAMED_SHOE", "Unnamed Shoe ")
    monkeypatch.setattr(gear_utils.gears_crud, "get_gear_user_by_nickname", lambda uid, name, db: None)
    monkeypatch.setattr(gear_utils, "logger", Mock())

    shoes_list = [
        {"Shoe Name": "", "Shoe Brand": "Adidas", "Shoe Model": "Adios"},
    ]
    gears = gear_utils.transform_csv_shoe_gear_to_schema_gear(shoes_list, 1, Mock())
    assert len(gears) == 1
    assert gears[0].nickname == "Unnamed Shoe 1"
