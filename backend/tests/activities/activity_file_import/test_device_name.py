"""Device names read from imported files."""

from modules.activities.activity_file_import.device_name import split_device_name, tcx_creator_name


def test_split_device_name_keeps_the_watch() -> None:
    """A combined creator name splits into manufacturer and model."""
    assert split_device_name("Fitbit Versa 4") == ("Fitbit", "Versa 4")


def test_split_device_name_ignores_the_exporting_program() -> None:
    """An exporter name is not stored as the recording device."""
    assert split_device_name("FitBridge") == (None, None)


def test_split_device_name_fits_the_column() -> None:
    """Each part of a device name fits the 250-character column."""
    manufacturer, model = split_device_name(f"{'A' * 300} {'B' * 300}")

    assert manufacturer is not None and len(manufacturer) == 250
    assert model is not None and len(model) == 250


def test_tcx_creator_name_reads_the_device(tmp_path) -> None:
    """A TCX device creator yields its name."""
    path = tmp_path / "walk.tcx"
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
        <TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
          <Activities>
            <Activity Sport="Other">
              <Creator>
                <Name>Fitbit Versa 4</Name>
              </Creator>
            </Activity>
          </Activities>
        </TrainingCenterDatabase>
        """,
        encoding="utf-8",
    )

    assert tcx_creator_name(str(path)) == "Fitbit Versa 4"


def test_tcx_creator_name_skips_an_application(tmp_path) -> None:
    """A TCX application creator is not a watch."""
    path = tmp_path / "walk.tcx"
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
        <TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
            xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
          <Activities>
            <Activity Sport="Other">
              <Creator xsi:type="Application_t">
                <Name>Garmin Training Center</Name>
              </Creator>
            </Activity>
          </Activities>
        </TrainingCenterDatabase>
        """,
        encoding="utf-8",
    )

    assert tcx_creator_name(str(path)) is None
