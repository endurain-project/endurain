"""A profile export fed back into an import, against real PostgreSQL.

Pins what the profile archive carries today: every section, the split per-activity files, the
stored blobs and the way archived ids are re-keyed onto the rows the import creates. The first test
exports a seeded account, wipes it, imports the archive into a fresh account with the same
username and email, exports again and expects the two archives to describe the same data. The
second imports a checked-in archive, so an archive written by an older release keeps importing.
"""

import asyncio
import base64
import io
import json
import re
import struct
import zipfile
import zlib
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import jasil.providers as platform_providers
import pytest
from sqlalchemy.orm import Session, sessionmaker

import core.hashing as core_hashing
import module_registry
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.crud as activity_crud
import modules.activities.activity_exercise_titles.contracts as titles_contracts
import modules.activities.activity_exercise_titles.crud as titles_crud
import modules.activities.activity_file_storage.constants as activity_file_constants
import modules.activities.activity_file_storage.integration_service as activity_file_storage_integration
import modules.activities.activity_laps.crud as laps_crud
import modules.activities.activity_media.constants as media_constants
import modules.activities.activity_media.contracts as media_contracts
import modules.activities.activity_media.crud as media_crud
import modules.activities.activity_sets.contracts as sets_contracts
import modules.activities.activity_sets.crud as sets_crud
import modules.activities.activity_streams.contracts as streams_contracts
import modules.activities.activity_streams.crud as streams_crud
import modules.activities.activity_workout_steps.contracts as steps_contracts
import modules.activities.activity_workout_steps.crud as steps_crud
import modules.gears.gear.crud as gear_crud
import modules.gears.gear.integration_service as gear_integration
import modules.gears.gear.schema as gear_schema
import modules.gears.gear_components.crud as components_crud
import modules.gears.gear_components.schema as components_schema
import modules.health.health_fasting.schema as fasting_schema
import modules.health.health_fasting.service as fasting_service
import modules.health.health_poop.schema as poop_schema
import modules.health.health_poop.service as poop_service
import modules.health.health_sleep.integration_service as sleep_integration
import modules.health.health_sleep.schema as sleep_schema
import modules.health.health_steps.integration_service as steps_health_integration
import modules.health.health_steps.schema as steps_health_schema
import modules.health.health_targets.crud as targets_crud
import modules.health.health_targets.schema as targets_schema
import modules.health.health_water.schema as water_schema
import modules.health.health_water.service as water_service
import modules.health.health_weight.integration_service as weight_integration
import modules.health.health_weight.schema as weight_schema
import modules.server_settings.models as server_settings_models
import modules.users.users.constants as users_constants
import modules.users.users.crud as users_crud
import modules.users.users.integration_service as users_integration
import modules.users.users.schema as users_schema
import modules.users.users.service as users_service
import modules.users.users_default_gear.integration_service as default_gear_integration
import modules.users.users_default_gear.schema as default_gear_schema
import modules.users.users_default_gear.service as default_gear_service
import modules.users.users_goals.integration_service as goals_integration
import modules.users.users_goals.schema as goals_schema
import modules.users.users_integrations.integration_service as integrations_integration
import modules.users.users_integrations.schema as integrations_schema
import modules.users.users_privacy_settings.integration_service as privacy_integration
import modules.users.users_privacy_settings.schema as privacy_schema
import modules.users.users_profile.constants as profile_constants
import modules.users.users_profile.export_service as profile_export_service
import modules.users.users_profile.import_service as profile_import_service
import modules.users.users_profile.service as profile_service

#: The checked-in archive of an export, written by an earlier run of this suite's seed.
_FIXTURE = Path(__file__).parent / "fixtures" / "profile_export_archive.json"

_USERNAME = "roundtrip"
_EMAIL = "round.trip@example.com"

#: Two items per file: the components are read ``batch_size // 2`` activities at a time.
_BATCH_SIZE = 4

_ACTIVITY_FILE_AREA = activity_file_constants.ACTIVITY_FILE_STORAGE_AREA

_GPX = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n'
    b'<gpx version="1.1" creator="endurain-test" xmlns="http://www.topografix.com/GPX/1/1">'
    b"<trk><name>Seed</name><trkseg>"
    b'<trkpt lat="38.7" lon="-9.1"><ele>10</ele><time>2026-07-28T09:00:00Z</time></trkpt>'
    b'<trkpt lat="38.8" lon="-9.2"><ele>12</ele><time>2026-07-28T09:00:10Z</time></trkpt>'
    b"</trkseg></trk></gpx>"
)

_PRIVACY_FLAGS = (
    "hide_start_time",
    "hide_location",
    "hide_map",
    "hide_hr",
    "hide_power",
    "hide_cadence",
    "hide_elevation",
    "hide_speed",
    "hide_pace",
    "hide_laps",
    "hide_workout_sets_steps",
    "hide_gear",
)

#: Keys that name another row; the normaliser re-keys them onto the position of the row they name.
_GEAR_KEYS = re.compile(r"(^|_)gear_id$")


@pytest.fixture(autouse=True)
def _server_settings(pg_factory):
    """The migrations create the settings row; the test schema does not."""
    with pg_factory() as db:
        db.add(server_settings_models.ServerSettings(id=1))
        db.commit()


@pytest.fixture(autouse=True)
def _contributors():
    """Install what the API and the worker install before they run a profile transfer."""
    module_registry.configure_activity_contributors()
    module_registry.configure_gear_contributors()
    module_registry.configure_user_contributors()


@pytest.fixture
def storage(_publish_local_platform) -> platform_providers.StorageProvider:
    return _publish_local_platform.storage


@pytest.fixture(autouse=True)
def _small_export_batches(monkeypatch):
    """Export a few activities at a time, so the components split into several files."""
    config = profile_export_service.ExportPerformanceConfig(batch_size=_BATCH_SIZE)
    monkeypatch.setattr(
        profile_export_service.ExportPerformanceConfig, "get_auto_config", classmethod(lambda cls: config)
    )


def _png(width: int = 2, height: int = 2, shade: int = 200) -> bytes:
    """Return a valid PNG, different for each shade."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    rows = b"".join(b"\x00" + bytes([shade, shade, shade]) * width for _ in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


def _create_account(factory: sessionmaker[Session]) -> int:
    """Create the account the archive is exported from and imported into, with its default rows."""
    with factory() as db:
        created = users_service.create_user(
            users_schema.UsersCreate(
                name="Round Trip",
                username=_USERNAME,
                email=_EMAIL,
                password="a secure round trip passphrase",
                access_type=users_schema.UserAccessType.REGULAR,
                active=True,
            ),
            db,
        )
        return created.id


def _activity(user_id: int, index: int, gear_id: int | None) -> activity_contracts.ActivityCore:
    return activity_contracts.ActivityCore(
        user_id=user_id,
        name=f"Ride {index}",
        description=f"Seed activity {index}",
        distance=10_000 + index * 1_000,
        activity_type=1 if index % 2 else 4,
        start_time=datetime(2026, 7, 20 + index, 9, 0, tzinfo=UTC),
        end_time=datetime(2026, 7, 20 + index, 10, 0, tzinfo=UTC),
        timezone="Europe/Lisbon",
        total_elapsed_time=3600.0,
        total_timer_time=3540.0,
        calories=500 + index,
        elevation_gain=120.0 + index,
        visibility=2,
        gear_id=gear_id,
        **{flag: index == 2 for flag in _PRIVACY_FLAGS},
    )


def _seed_gears(db: Session, user_id: int) -> list[int]:
    road = gear_crud.create_gear(
        gear_schema.GearCreate(
            nickname="Road Bike",
            gear_type=gear_schema.GearType.BIKE,
            brand="Canyon",
            model="Endurace",
            initial_kms=12.5,
        ),
        user_id,
        db,
    )
    shoes = gear_crud.create_gear(
        gear_schema.GearCreate(nickname="Trail Shoes", gear_type=gear_schema.GearType.SHOES, brand="Hoka"),
        user_id,
        db,
    )
    components_crud.create_gear_component(
        components_schema.GearComponentCreate(
            gear_id=road.id,
            type="chain",
            brand="Shimano",
            model="XT",
            purchase_date=date(2026, 1, 5),
            expected_kms=3000,
            purchase_value=45.5,
        ),
        user_id,
        db,
    )
    components_crud.create_gear_component(
        components_schema.GearComponentCreate(gear_id=road.id, type="cassette", brand="SRAM", model="XG"),
        user_id,
        db,
    )
    return [road.id, shoes.id]


def _seed_activities(db: Session, user_id: int, gear_ids: list[int], storage: platform_providers.StorageProvider):
    """Add three activities with every kind of per-activity child, an activity file and a media blob."""
    titles_crud.create_activity_exercise_titles(
        [
            titles_contracts.ActivityExerciseTitlesCreate(exercise_category=1, exercise_name=2, wkt_step_name="Bench"),
            titles_contracts.ActivityExerciseTitlesCreate(exercise_category=3, exercise_name=4, wkt_step_name="Row"),
        ],
        db,
    )
    for index in range(3):
        created = activity_crud.create_activity(_activity(user_id, index, gear_ids[index % 2]), db)
        activity_id = created.id
        assert activity_id is not None
        laps_crud.create_activity_laps(
            [
                {"start_time": f"2026-07-{20 + index}T09:00:00", "total_distance": 5_000 + lap, "total_calories": lap}
                for lap in range(2)
            ],
            activity_id,
            db,
        )
        sets_crud.create_activity_sets(
            [
                sets_contracts.ActivitySetsCreate(
                    activity_id=activity_id,
                    duration=30.5 + part,
                    repetitions=10,
                    weight=20.0,
                    set_type="active",
                    start_time=f"2026-07-{20 + index}T09:0{part}:00",
                    category=1,
                    category_subtype=2,
                )
                for part in range(2)
            ],
            activity_id,
            db,
        )
        streams_crud.create_activity_streams(
            [
                streams_contracts.ActivityStreamsCreate(
                    activity_id=activity_id,
                    stream_type=stream_type,
                    stream_waypoints=[
                        {"time": f"2026-07-{20 + index}T09:00:0{sample}", "hr": 120 + sample + stream_type}
                        for sample in range(2)
                    ],
                )
                for stream_type in (1, 2)
            ],
            created,
            db,
        )
        steps_crud.create_activity_workout_steps(
            [
                steps_contracts.ActivityWorkoutStepsCreate(
                    message_index=step, duration_type="time", duration_value=60.0 + step, intensity="active"
                )
                for step in range(2)
            ],
            activity_id,
            db,
        )
        media_key = f"{activity_id}_seed{index}.png"
        blob = _png(shade=100 + index)
        media_crud.create_activity_medias(
            [
                media_contracts.ActivityMediaCreate(
                    media_path=media_key, media_type=1, content_hash=core_hashing.sha256_hex(blob)
                )
            ],
            activity_id,
            db,
        )
        storage.save(media_constants.MEDIA_STORAGE_AREA, media_key, blob)
        if index != 1:
            activity_file_storage_integration.store_activity_file(activity_id, ".gpx", _GPX, storage)


def _seed_health(db: Session, user_id: int) -> None:
    for day in range(1, 4):
        weight_integration.upsert_health_weight(
            user_id,
            weight_schema.HealthWeightCreate(
                date=date(2026, 7, day), weight=70.0 + day, body_fat=15.5, source="garmin"
            ),
            db,
        )
        sleep_integration.upsert_health_sleep(
            user_id,
            sleep_schema.HealthSleepCreate(
                date=date(2026, 7, day),
                sleep_start_time_gmt=datetime(2026, 7, day, 22, 0, tzinfo=UTC),
                sleep_end_time_gmt=datetime(2026, 7, day + 1, 6, 0, tzinfo=UTC),
                total_sleep_seconds=27_000 + day,
                deep_sleep_seconds=5_000,
                sleep_score_overall=80 + day,
            ),
            db,
        )
        steps_health_integration.upsert_health_steps(
            user_id, steps_health_schema.HealthStepsCreate(date=date(2026, 7, day), steps=8_000 + day), db
        )
        water_service.stage_upsert_health_water(
            user_id, water_schema.HealthWaterCreate(date=date(2026, 7, day), amount_ml=1_500.0 + day), db
        )
    targets_crud.edit_health_targets(
        targets_schema.HealthTargetsUpdate(weight=68.0, steps=10_000, sleep=28_800, water_ml=2_000, poop_count=1),
        user_id,
        db,
        if_match="*",
    )
    fasting_service.stage_import_health_fasting(
        user_id,
        fasting_schema.HealthFastingCreate(
            fast_start_time=datetime(2026, 7, 1, 20, 0, tzinfo=UTC),
            fast_end_time=datetime(2026, 7, 2, 12, 0, tzinfo=UTC),
            target_duration_seconds=57_600,
            status=fasting_schema.FastingStatus.COMPLETED,
            notes="16:8",
        ),
        db,
    )
    poop_service.stage_import_health_poop(
        user_id,
        poop_schema.HealthPoopCreate(date_time=datetime(2026, 7, 1, 8, 0, tzinfo=UTC), bristol_type=4, notes="ok"),
        db,
    )


def _seed(factory: sessionmaker[Session], storage: platform_providers.StorageProvider) -> int:
    """Create the account and fill every section the archive carries; return its id."""
    user_id = _create_account(factory)
    with factory() as db:
        users_integration.edit_profile(
            user_id,
            users_schema.ProfileUpdate(city="Lisbon", height=178, birthdate=date(1990, 5, 17), max_heart_rate=185),
            db,
            if_match="*",
        )
        gear_ids = _seed_gears(db, user_id)
        default_gear_service.stage_default_gear_edit(
            default_gear_schema.UsersDefaultGearUpdate(ride_gear_id=gear_ids[0], run_gear_id=gear_ids[1]),
            user_id,
            db,
            if_match="*",
        )
        for goal_type, goal in (("calories", {"goal_calories": 5000}), ("distance", {"goal_distance": 40_000})):
            goals_integration.create_goal(
                user_id,
                goals_schema.UsersGoalCreate(interval="weekly", activity_type="run", goal_type=goal_type, **goal),
                db,
            )
        integrations_integration.edit_integrations(
            integrations_schema.UsersIntegrationsUpdate(strava_sync_gear=True, garminconnect_sync_gear=True),
            user_id,
            db,
        )
        privacy_integration.edit_privacy_settings(
            user_id,
            privacy_schema.UsersPrivacySettingsUpdate(hide_activity_map=True, hide_activity_hr=True),
            db,
            if_match="*",
        )
        _seed_activities(db, user_id, gear_ids, storage)
        _seed_health(db, user_id)
        db.commit()
    with factory() as db:
        users_integration.store_user_photo(user_id, ".png", _png(8, 8, 50), storage, db)
    return user_id


def _export(factory: sessionmaker[Session], storage: platform_providers.StorageProvider, user_id: int) -> bytes:
    """Export the way production does and read back the staged archive."""
    with factory() as db:
        profile_service.stage_export(user_id, storage, db)
    key = profile_constants.export_staged_key(user_id)
    data = storage.get(profile_constants.EXPORT_STAGING_AREA, key)
    assert data is not None
    storage.delete(profile_constants.EXPORT_STAGING_AREA, key)
    return data


def _import(
    factory: sessionmaker[Session], storage: platform_providers.StorageProvider, user_id: int, archive: bytes
) -> dict[str, int]:
    """Import the way the import job does, on a session of its own and a loop of its own."""
    with factory() as db:
        importer = profile_import_service.ImportService(
            user_id,
            storage,
            db,
            profile_import_service.ImportPerformanceConfig(batch_size=_BATCH_SIZE // 2),
        )
        return asyncio.run(importer.import_from_zip_data(archive))


def _wipe(factory: sessionmaker[Session], storage: platform_providers.StorageProvider, user_id: int) -> None:
    """Delete the account's rows through the database cascade and every blob the account owned."""
    with factory() as db:
        users_crud.delete_user(user_id, db)
        db.commit()
    for area in (_ACTIVITY_FILE_AREA, media_constants.MEDIA_STORAGE_AREA, users_constants.USER_IMAGE_STORAGE_AREA):
        for key in storage.list_keys(area, ""):
            storage.delete(area, key)


def _entries(archive: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(archive)) as zipf:
        return {name: zipf.read(name) for name in zipf.namelist()}


def _json_entries(entries: dict[str, bytes]) -> dict[str, Any]:
    return {name: json.loads(data) for name, data in entries.items() if name.endswith(".json")}


class _Normaliser:
    """Re-key an archive's ids onto the position of the row they name.

    The import gives every row a new id, so two archives of the same data differ in every id. A
    gear or an activity is identified by its position in the archive's own list, and each key that
    names one (``activity_id``, ``gear_id``, ``*_gear_id``, the id inside a media key or a file
    name) is rewritten to that position. A link that points at the wrong row, or at none, shows up
    as a difference. The ids of every other row, the owner and the version counter are dropped.
    """

    #: ``activity_files/{activity_id}.gpx`` and ``activity_media/{activity_id}_{suffix}``.
    _BLOB = re.compile(r"^(?P<folder>activity_files|activity_media)/(?P<id>\d+)(?P<rest>[._].*)$")
    _USER_IMAGE = re.compile(r"^user_images/\d+(?P<ext>\..*)$")
    _MEDIA_KEY = re.compile(r"^(?P<id>\d+)_(?P<rest>.*)$")

    def __init__(self, entries: dict[str, Any]) -> None:
        self.gears = {row["id"]: f"gear-{position}" for position, row in enumerate(entries["data/gears.json"])}
        self.activities = {
            row["id"]: f"activity-{position}" for position, row in enumerate(entries["data/activities.json"])
        }

    def name(self, entry: str) -> str:
        if match := self._USER_IMAGE.match(entry):
            return f"user_images/user{match['ext']}"
        if match := self._BLOB.match(entry):
            return f"{match['folder']}/{self.activities[int(match['id'])]}{match['rest']}"
        return entry

    def entry(self, name: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self._row(name, row) for row in rows]

    def _row(self, name: str, row: dict[str, Any]) -> dict[str, Any]:
        keep_id = {"data/gears.json": self.gears, "data/activities.json": self.activities}.get(name)
        out: dict[str, Any] = {}
        for key, value in row.items():
            if key == "id":
                if keep_id is not None:
                    out[key] = keep_id[value]
            elif key in ("user_id", "version"):
                continue
            elif key == "activity_id":
                out[key] = self.activities[value]
            elif _GEAR_KEYS.search(key):
                out[key] = None if value is None else self.gears[value]
            elif key == "photo_path":
                # A signed URL naming the owner: only whether there is a photo can carry over.
                out[key] = bool(value)
            elif key == "media_path" and isinstance(value, str) and (match := self._MEDIA_KEY.match(value)):
                out[key] = f"{self.activities[int(match['id'])]}_{match['rest']}"
            else:
                out[key] = value
        return out


#: The per-activity child files, whole or split into numbered parts (``data/activity_laps_001.json``).
_CHILD_FILE = re.compile(r"^data/(?P<family>activity_(?!exercise_titles)\w+?)(_\d{3})?\.json$")


def _normalised(archive: bytes) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Return an archive's JSON entries and binary entries, with ids re-keyed and names made comparable.

    A child file lists its rows in the order of their activity's id, which the import assigns anew, so
    the rows of one kind are compared as a set across its parts, while each part keeps its row count.
    """
    entries = _entries(archive)
    parsed = _json_entries(entries)
    normaliser = _Normaliser(parsed)
    data: dict[str, Any] = {}
    for name, rows in parsed.items():
        if not name.startswith("data/"):
            data[name] = rows
        elif match := _CHILD_FILE.match(name):
            family = normaliser.entry(name, rows)
            data[f"{name} (size)"] = len(rows)
            data.setdefault(f"family:{match['family']}", []).extend(family)
        else:
            data[name] = normaliser.entry(name, rows)
    for key, value in data.items():
        if key.startswith("family:"):
            value.sort(key=lambda row: json.dumps(row, sort_keys=True))
    binaries = {normaliser.name(name): blob for name, blob in entries.items() if not name.endswith(".json")}
    return data, binaries


def test_an_export_imported_into_a_fresh_account_exports_the_same_archive(pg_factory, storage):
    first_user = _seed(pg_factory, storage)
    first = _export(pg_factory, storage, first_user)

    _wipe(pg_factory, storage, first_user)
    second_user = _create_account(pg_factory)
    assert second_user != first_user
    imported = _import(pg_factory, storage, second_user, first)
    second = _export(pg_factory, storage, second_user)

    first_data, first_binaries = _normalised(first)
    second_data, second_binaries = _normalised(second)

    assert first_data.keys() == second_data.keys()
    assert any(re.fullmatch(r"data/activity_laps_\d{3}\.json \(size\)", name) for name in first_data), "no split files"
    assert first_binaries.keys() == second_binaries.keys()
    assert {name for name in first_binaries if name.startswith("activity_files/")}
    assert {name for name in first_binaries if name.startswith("activity_media/")}
    assert {name for name in first_binaries if name.startswith("user_images/")}
    for name in first_binaries:
        assert first_binaries[name] == second_binaries[name], name

    assert second_data["counts.json"] == first_data["counts.json"]
    assert imported["gears"] == 2
    assert imported["activities"] == 3
    for name, rows in first_data.items():
        if name != "counts.json":
            assert second_data[name] == rows, name


def _document_of(archive: bytes) -> dict[str, dict[str, Any]]:
    """Describe an archive as a text document: JSON entries as JSON, the rest as base64."""
    return {
        name: {"json": json.loads(data)} if name.endswith(".json") else {"base64": base64.b64encode(data).decode()}
        for name, data in sorted(_entries(archive).items())
    }


def _archive_of(document: dict[str, dict[str, Any]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
        for name, entry in document.items():
            zipf.writestr(name, json.dumps(entry["json"]) if "json" in entry else base64.b64decode(entry["base64"]))
    return buffer.getvalue()


def test_an_archive_written_by_an_earlier_release_still_imports(pg_factory, storage):
    document = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    user_id = _create_account(pg_factory)

    imported = _import(pg_factory, storage, user_id, _archive_of(document))

    exported = document["counts.json"]["json"][0]
    assert imported == {key: exported[key] for key in imported}
    assert imported["gears"] == 2
    assert imported["gear_components"] == 2
    assert imported["activities"] == 3
    assert imported["activity_laps"] == imported["activity_sets"] == imported["activity_streams"] == 6
    assert (imported["activity_workout_steps"], imported["activity_media"]) == (6, 3)
    assert (imported["activity_files"], imported["media"], imported["user_images"]) == (2, 3, 1)
    assert all(imported[key] == 3 for key in ("health_weight", "health_sleep", "health_steps", "health_water"))

    with pg_factory() as db:
        gears = {gear.nickname: gear.id for gear in gear_integration.get_gear_user(user_id, db)}
        default_gear = default_gear_integration.get_default_gear(user_id, db)
        assert default_gear is not None
        assert (default_gear.ride_gear_id, default_gear.run_gear_id) == (gears["Road Bike"], gears["Trail Shoes"])
        assert users_integration.require_user(user_id, db).city == "Lisbon"
