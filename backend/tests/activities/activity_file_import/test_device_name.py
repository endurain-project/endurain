"""Device names read from imported files."""

from modules.activities.activity_file_import.device_name import split_device_name, tcx_creator_name


def test_split_device_name_keeps_the_watch() -> None:
    assert split_device_name("Fitbit Versa 4") == ("Fitbit", "Versa 4")


def test_split_device_name_ignores_the_exporting_program() -> None:
    assert split_device_name("FitBridge") == (None, None)


def test_tcx_creator_name_reads_the_device(tmp_path) -> None:
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
