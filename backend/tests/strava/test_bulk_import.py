"""Strava-export bulk import: the manifest, the gear and photos it names, and the pieces of the export layout."""

import io
import uuid
import zipfile
from datetime import UTC, datetime, timedelta

import jasil.runtime as platform_runtime
import pytest
from PIL import Image
from sqlalchemy import select

import core.config as core_config
import core.exceptions as core_exceptions
import modules.activities.activity.contracts as activity_contracts
import modules.activities.activity.models as activity_models
import modules.activities.activity_ingestion.bulk_import_service as ingestion_bulk_import
import modules.activities.activity_ingestion.provider_registry as provider_registry
import modules.activities.activity_media.models as activity_media_models
import modules.gears.gear.integration_service as gears_integration
import modules.strava.bulk_import_service as strava_bulk
import modules.strava.integration_service as strava_integration
from tests._factories.activities import make_activity
from tests._factories.gears import gear_payload
from tests._factories.ingestion import fit_file
from tests._factories.users import make_user

_API = core_config.ROOT_PATH
_HEADER = (
    "Activity ID,Activity Date,Activity Name,Activity Type,Activity Description,Elapsed Time,Filename,"
    "Activity Gear,Media\n"
)
_DATE = "Oct 21, 2023, 7:41:47 AM"


def _row(**fields: str) -> dict[str, str]:
    return {
        "Activity ID": "1",
        "Activity Date": _DATE,
        "Activity Name": "Run",
        "Activity Type": "Run",
        "Activity Description": "",
        "Filename": "activities/1.gpx",
        "Activity Gear": "",
        "Media": "",
        **fields,
    }


def _csv(*rows: dict[str, str]) -> bytes:
    columns = _HEADER.strip().split(",")
    body = "".join(",".join(f'"{row.get(column, "")}"' for column in columns) + "\n" for row in rows)
    return (_HEADER + body).encode()


def _jpeg(colour: str = "red") -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (20, 10), colour).save(out, "JPEG")
    return out.getvalue()


def _gpx(start: datetime) -> bytes:
    def moment(i: int) -> str:
        return (start + timedelta(seconds=10 * i)).strftime("%Y-%m-%dT%H:%M:%SZ")

    points = "".join(
        f'<trkpt lat="38.7{i}" lon="-9.1{i}"><ele>{10 + i}</ele><time>{moment(i)}</time></trkpt>' for i in range(6)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?><gpx version="1.1" creator="test" '
        'xmlns="http://www.topografix.com/GPX/1/1"><trk><name>From the file</name><type>running</type>'
        f"<trkseg>{points}</trkseg></trk></gpx>"
    ).encode()


def _zip(members: dict[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return out.getvalue()


class TestAStravaExportImport:
    @pytest.fixture(autouse=True)
    def _registered(self, durable_jobs, tmp_path):
        provider_registry.clear()
        strava_integration.register_activity_provider()
        yield
        provider_registry.clear()

    def test_the_activities_take_their_name_gear_and_photos_from_the_manifest(self, sign_in, committed_sessions):
        start = datetime(2023, 10, 21, 7, 41, 47, tzinfo=UTC)
        with committed_sessions() as db:
            user = make_user(db)
            gears_integration.create_multiple_gears([gear_payload("Pegasus", user_id=user.id)], user.id, db)
            db.commit()
        archive = _zip(
            {
                "activities.csv": _csv(
                    _row(
                        **{
                            "Activity Name": "Morning run",
                            "Activity Description": "From Strava",
                            "Activity Gear": "Pegasus",
                            "Activity ID": "987",
                            "Media": "media/photo.jpg",
                        }
                    )
                ),
                "activities/1.gpx": _gpx(start),
                "media/photo.jpg": _jpeg(),
            }
        )
        client = sign_in(user).client

        response = client.post(
            f"{_API}/activities/bulk-import",
            params={"source": "strava"},
            files={"file": ("export.zip", archive, "application/zip")},
        )
        assert response.status_code == 202, response.text
        ingestion_bulk_import.run_bulk_import_job(
            uuid.UUID(response.json()["id"]), platform_runtime.get_active_platform().storage
        )

        job = client.get(f"{_API}/jobs/{response.json()['id']}").json()
        assert (job["status"], job["files_done"], job["files_failed"]) == ("succeeded", 1, 0)
        with committed_sessions() as db:
            (activity,) = db.scalars(
                select(activity_models.Activity).where(activity_models.Activity.user_id == user.id)
            )
            gear = gears_integration.get_gear_user(user.id, db)[0]
            media = db.scalars(
                select(activity_media_models.ActivityMedia).where(
                    activity_media_models.ActivityMedia.activity_id == activity.id
                )
            ).all()
        assert (activity.name, activity.description, activity.gear_id) == ("Morning run", "From Strava", gear.id)
        assert activity.strava_activity_id is None, "the id only goes in the import record"
        assert activity.import_info["strava_activity_id"] == 987
        assert len(media) == 1

    def _import_triathlon(self, sign_in, committed_sessions, row_date: str):
        with committed_sessions() as db:
            user = make_user(db)
            gears_integration.create_multiple_gears([gear_payload("Pegasus", user_id=user.id)], user.id, db)
            db.commit()
        archive = _zip(
            {
                "activities.csv": _csv(
                    _row(
                        **{
                            "Activity Date": row_date,
                            "Activity Name": "Race day",
                            "Activity Description": "From Strava",
                            "Activity Gear": "Pegasus",
                            "Filename": "activities/2.fit",
                            "Media": "media/photo.jpg",
                        }
                    )
                ),
                "activities/2.fit": fit_file(activities=3, multisport=True),
                "media/photo.jpg": _jpeg(),
            }
        )
        client = sign_in(user).client
        response = client.post(
            f"{_API}/activities/bulk-import",
            params={"source": "strava"},
            files={"file": ("export.zip", archive, "application/zip")},
        )
        assert response.status_code == 202, response.text
        ingestion_bulk_import.run_bulk_import_job(
            uuid.UUID(response.json()["id"]), platform_runtime.get_active_platform().storage
        )
        assert client.get(f"{_API}/jobs/{response.json()['id']}").json()["status"] == "succeeded"
        with committed_sessions() as db:
            rows = list(
                db.scalars(
                    select(activity_models.Activity)
                    .where(activity_models.Activity.user_id == user.id)
                    .order_by(activity_models.Activity.start_time)
                )
            )
            media = db.scalars(select(activity_media_models.ActivityMedia)).all()
            gear_id = gears_integration.get_gear_user(user.id, db)[0].id
        return rows, media, gear_id

    def test_a_multisport_file_imports_once_as_a_parent_that_takes_the_listings_name_and_photos_but_no_gear(
        self, sign_in, committed_sessions
    ):
        rows, media, _gear_id = self._import_triathlon(sign_in, committed_sessions, "Jan 15, 2026, 8:00:00 AM")

        [parent] = [row for row in rows if row.parent_activity_id is None]
        legs = [row for row in rows if row.parent_activity_id is not None]
        assert len(legs) == 3
        assert (parent.name, parent.description, parent.gear_id) == ("Race day", "From Strava", None)
        assert parent.import_info["strava_activity_id"] == 1
        assert [leg.name for leg in legs] == ["Run", "Run", "Run"]
        assert [medium.activity_id for medium in media] == [parent.id]

    def test_a_multisport_file_whose_listing_starts_elsewhere_than_the_parent_imports_nothing(
        self, sign_in, committed_sessions
    ):
        rows, media, _gear_id = self._import_triathlon(sign_in, committed_sessions, "Jan 15, 2026, 9:00:00 AM")

        assert rows == []
        assert media == []

    def test_an_export_without_a_manifest_fails_the_job_and_imports_nothing(self, sign_in, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db)
            db.commit()
        client = sign_in(user).client
        archive = _zip({"activities/1.gpx": _gpx(datetime(2023, 10, 21, 7, 41, 47, tzinfo=UTC))})

        response = client.post(
            f"{_API}/activities/bulk-import",
            params={"source": "strava"},
            files={"file": ("export.zip", archive, "application/zip")},
        )
        assert response.status_code == 202, response.text
        ingestion_bulk_import.run_bulk_import_job(
            uuid.UUID(response.json()["id"]), platform_runtime.get_active_platform().storage
        )

        job = client.get(f"{_API}/jobs/{response.json()['id']}").json()
        assert job["status"] == "failed"
        with committed_sessions() as db:
            assert (
                db.scalars(select(activity_models.Activity).where(activity_models.Activity.user_id == user.id)).all()
                == []
            )


class TestManifest:
    def _write(self, tmp_path, content: bytes) -> str:
        path = tmp_path / "activities.csv"
        path.write_bytes(content)
        return str(path)

    def test_rows_are_keyed_by_the_files_base_name(self, tmp_path):
        path = self._write(tmp_path, _csv(_row(Filename="activities/123.fit.gz", **{"Activity Name": "Ride"})))

        parsed = strava_bulk.parse_activities_manifest(path)

        assert list(parsed) == ["123.fit.gz"]
        assert parsed["123.fit.gz"]["Activity Name"] == "Ride"

    @pytest.mark.parametrize(
        "content",
        [
            b"Activity ID,Filename\n1,activities/1.fit\n",
            _HEADER.encode() + b"1,Oct 21 2023,Ride\n",
            b"\xff\xfe\x00\x81 not utf-8\n",
        ],
        ids=["missing-headers", "truncated-row", "not-text"],
    )
    def test_a_manifest_that_cannot_be_used_is_refused_not_raised(self, tmp_path, content):
        assert strava_bulk.parse_activities_manifest(self._write(tmp_path, content)) is None

    def test_a_manifest_over_the_size_cap_is_refused_not_raised(self, tmp_path):
        oversized = _csv(_row()) + b"x" * (10 * 1024 * 1024 + 1)

        assert strava_bulk.parse_activities_manifest(self._write(tmp_path, oversized)) is None

    def test_a_manifest_that_cannot_be_opened_is_refused_not_raised(self, tmp_path):
        assert strava_bulk.parse_activities_manifest(str(tmp_path / "missing.csv")) is None


class TestGearNames:
    def test_the_users_gear_is_found_by_nickname_and_by_the_name_strava_exports_for_shoes(self, db):
        user = make_user(db)
        gears_integration.create_multiple_gears(
            [
                gear_payload("Fast Shoes", user_id=user.id, brand="Nike ", model=" Pegasus", gear_type="shoes"),
                gear_payload("Unbranded", user_id=user.id),
            ],
            user.id,
            db,
        )

        names = strava_bulk.create_gear_dictionary_for_bulk_import(user.id, db)

        by_nickname = {g.nickname: g.id for g in gears_integration.get_gear_user(user.id, db)}
        assert names == {
            "Fast Shoes": [by_nickname["Fast Shoes"]],
            "Nike Pegasus Fast Shoes": [by_nickname["Fast Shoes"]],
            "Unbranded": [by_nickname["Unbranded"]],
        }

    def test_a_user_with_no_gear_gets_an_empty_map_not_an_aborted_import(self, db):
        assert strava_bulk.create_gear_dictionary_for_bulk_import(make_user(db).id, db) == {}

    def test_a_gear_name_with_a_plus_resolves_to_the_users_gear(self):
        gear = uuid.uuid4()

        metadata = strava_bulk.build_metadata_dict(
            "a.fit",
            {"a.fit": _row(**{"Activity Gear": "Nike+Pegasus"})},
            "2026-01-01T00:00:00",
            {"Nike Pegasus": [gear]},
        )

        assert metadata["gear_id"] == gear

    @pytest.mark.parametrize(
        ("named", "known"),
        [("Unknown", {"Nike": [uuid.uuid4()]}), ("Nike", None), ("", {"Nike": [uuid.uuid4()]})],
        ids=["not-the-users", "user-without-gear", "no-gear"],
    )
    def test_gear_the_user_does_not_have_leaves_the_activity_without_gear(self, named, known):
        metadata = strava_bulk.build_metadata_dict(
            "a.fit", {"a.fit": _row(**{"Activity Gear": named})}, "2026-01-01T00:00:00", known
        )

        assert metadata["gear_id"] is None


class TestMetadata:
    def test_a_file_without_a_manifest_row_gets_the_plain_import_record(self):
        metadata = strava_bulk.build_metadata_dict("b.gpx", {"a.fit": _row()}, "2026-01-01T00:00:00")

        assert metadata["metadata_found_in_csv"] is False
        assert metadata["import_dict"]["import_source"] == "Basic bulk import"

    def test_the_strava_activity_id_goes_only_in_the_import_record_and_a_bad_one_is_ignored(self):
        good = strava_bulk.build_metadata_dict("a.fit", {"a.fit": _row(**{"Activity ID": "42"})}, "t")
        bad = strava_bulk.build_metadata_dict("a.fit", {"a.fit": _row(**{"Activity ID": "forty-two"})}, "t")

        assert good["import_dict"]["strava_activity_id"] == 42
        assert "strava_activity_id" not in bad["import_dict"]
        assert "strava_activity_id" not in good

    def test_the_source_builds_the_metadata_from_its_manifest_and_applies_it_to_the_activity(self):
        gear = uuid.uuid4()
        source = strava_bulk.StravaBulkImportSource(
            import_initiated_time="2026-07-21T00:00:00",
            strava_activities={"f.fit": _row(**{"Activity Name": "Morning Ride", "Activity Gear": "Bike"})},
            gear_nickname_to_id={"Bike": [gear]},
        )
        activity = activity_contracts.ActivityCore(
            user_id=uuid.uuid4(),
            name="Workout",
            distance=1000,
            activity_type=1,
            start_time="2023-10-21T07:41:47",
            end_time="2023-10-21T08:41:47",
        )

        source.apply_metadata(activity, source.metadata_for("f.fit"))

        assert (activity.name, activity.gear_id) == ("Morning Ride", gear)

    def test_nothing_is_built_without_an_initiated_time(self):
        assert strava_bulk.StravaBulkImportSource(strava_activities={"f.fit": _row()}).metadata_for("f.fit") == {}

    def test_a_source_without_a_manifest_falls_back_to_the_plain_import_record(self):
        source = strava_bulk.StravaBulkImportSource(import_initiated_time="2026-07-21T00:00:00")

        assert source.metadata_for("f.gpx")["import_dict"]["import_source"] == "Basic bulk import"


class TestMultiActivityFiles:
    """Strava lists a multi-activity .fit once per activity it contains, so the listing picks its own."""

    def _activity(self, start: str = "2023-10-21T07:41:47"):
        return activity_contracts.ActivityCore(
            user_id=uuid.uuid4(),
            name="Workout",
            distance=1000,
            activity_type=1,
            start_time=start,
            end_time="2023-10-21T09:00:00",
        )

    def _source(self, **fields):
        return strava_bulk.StravaBulkImportSource(
            import_initiated_time="2026-01-01T00:00:00", strava_activities={"a.fit": _row(**fields)}
        )

    def _metadata(self, source):
        return source.metadata_for("a.fit")

    def test_the_activity_whose_start_matches_the_listing_is_imported_and_the_others_skipped(self):
        source = self._source()
        metadata = self._metadata(source)

        assert source.should_import(self._activity("2023-10-21T07:41:47"), metadata, activities_in_file=5) is True
        assert source.should_import(self._activity("2023-10-21T08:13:28"), metadata, activities_in_file=5) is False

    def test_a_single_activity_file_or_a_file_without_a_listing_is_always_imported(self):
        source = self._source()

        assert (
            source.should_import(self._activity("2024-01-01T00:00:00"), self._metadata(source), activities_in_file=1)
            is True
        )
        assert source.should_import(self._activity(), {"metadata_found_in_csv": False}, activities_in_file=5) is True

    def test_a_listing_date_written_in_another_language_imports_the_activity_rather_than_dropping_it(self):
        source = self._source(**{"Activity Date": "21 oct. 2023 à 08:13:28"})

        assert source.should_import(self._activity(), self._metadata(source), activities_in_file=5) is True

    def test_matching_start_times_are_recognised_whatever_the_time_zone_of_the_parser(self):
        assert strava_bulk.does_activity_start_time_match_the_data_in_strava_activities_csv(
            self._activity("2023-10-21T07:41:47"), {"activity date": _DATE}
        )


class TestPhotos:
    def test_each_listed_photo_is_read_from_the_exports_media_folder_and_attached(self, db):
        user = make_user(db)
        activity = make_activity(db, user.id)
        archive = {"media/a.jpg": _jpeg("red"), "media/b.jpg": _jpeg("blue")}
        rows = {"ride.fit": _row(Media="media/a.jpg|media/b.jpg")}

        strava_bulk.import_media_from_strava_bulk_export(rows, activity, "ride.fit", archive.get, db)

        assert _media_count(db, activity.id) == 2

    def test_a_photo_missing_from_the_export_is_skipped_not_fatal(self, db):
        user = make_user(db)
        activity = make_activity(db, user.id)
        rows = {"ride.fit": _row(Media="media/a.jpg|media/b.jpg")}

        strava_bulk.import_media_from_strava_bulk_export(rows, activity, "ride.fit", {"media/b.jpg": _jpeg()}.get, db)

        assert _media_count(db, activity.id) == 1

    def test_a_row_without_media_reads_nothing(self, db):
        user = make_user(db)
        activity = make_activity(db, user.id)
        read: list[str] = []

        def read_member(name):
            read.append(name)

        strava_bulk.import_media_from_strava_bulk_export(
            {"ride.fit": _row(Media="  ")}, activity, "ride.fit", read_member, db
        )

        assert (read, _media_count(db, activity.id)) == ([], 0)

    def test_a_path_in_the_manifest_cannot_reach_outside_the_media_folder(self, db):
        user = make_user(db)
        activity = make_activity(db, user.id)
        read: list[str] = []

        def read_member(name):
            read.append(name)

        strava_bulk.import_media_from_strava_bulk_export(
            {"ride.fit": _row(Media="../activities/secret.fit")}, activity, "ride.fit", read_member, db
        )

        assert read == ["media/secret.fit"]

    def test_a_photo_that_is_not_an_image_is_rejected_and_the_activity_keeps_its_other_photos(self, db):
        user = make_user(db)
        activity = make_activity(db, user.id)

        strava_bulk.create_activity_media_from_strava_bulk_import(activity.id, "photo.jpg", b"not an image", db)
        strava_bulk.create_activity_media_from_strava_bulk_import(activity.id, "photo.jpg", _jpeg(), db)

        assert _media_count(db, activity.id) == 1

    def test_a_photo_for_an_activity_the_media_module_does_not_know_is_skipped(self, db):
        strava_bulk.create_activity_media_from_strava_bulk_import(uuid.uuid4(), "photo.jpg", _jpeg(), db)

    def test_nothing_is_attached_without_created_activities_or_a_way_to_read_the_archive(self, db):
        user = make_user(db)
        activity = make_activity(db, user.id)
        archive = {"media/a.jpg": _jpeg()}
        manifest = {"a.fit": _row(Media="media/a.jpg")}

        strava_bulk.StravaBulkImportSource(strava_activities=manifest, read_member=archive.get).import_side_artifacts(
            [], "a.fit", db
        )
        strava_bulk.StravaBulkImportSource(strava_activities=manifest).import_side_artifacts([activity], "a.fit", db)

        assert _media_count(db, activity.id) == 0

    def test_the_photos_go_to_the_last_activity_created_from_the_file(self, db):
        user = make_user(db)
        first = make_activity(db, user.id)
        last = make_activity(db, user.id, start_time=first.start_time.replace(hour=12))
        archive = {"media/a.jpg": _jpeg()}
        source = strava_bulk.StravaBulkImportSource(
            strava_activities={"a.fit": _row(Media="media/a.jpg")}, read_member=archive.get
        )

        source.import_side_artifacts([first, last], "a.fit", db)

        assert (_media_count(db, first.id), _media_count(db, last.id)) == (0, 1)


def _media_count(db, activity_id) -> int:
    return len(
        db.scalars(
            select(activity_media_models.ActivityMedia).where(
                activity_media_models.ActivityMedia.activity_id == activity_id
            )
        ).all()
    )


class TestExportLayout:
    def test_activity_files_are_those_directly_in_the_activities_folder(self):
        is_activity = strava_bulk._is_activity_member

        assert is_activity("activities/123.fit.gz")
        assert is_activity("activities/45.gpx")
        assert not is_activity("activities.csv")
        assert not is_activity("media/photo.jpg")
        assert not is_activity("activities/readme.txt")
        assert not is_activity("activities/.DS_Store")

    def test_the_export_is_its_manifest_activities_and_photos_only(self):
        is_export = strava_bulk._is_export_member

        assert is_export("activities.csv")
        assert is_export("activities/1.fit")
        assert is_export("media/p.jpg")
        assert not is_export("notes.txt")
        assert not is_export("bikes.csv")

    def test_the_format_is_registered_under_strava_with_a_directory_per_user(self):
        provider_registry.clear()
        try:
            strava_bulk.register_bulk_import_format()
            registered = provider_registry.get_bulk_format("strava")
            user_id = uuid.uuid4()

            assert registered is not None
            assert registered.drop_directory(user_id) == f"{core_config.settings.FILES_DIR}/strava_import/{user_id}"
        finally:
            provider_registry.clear()


class TestBuildSource:
    def test_it_parses_the_manifest_and_reads_the_users_gear(self, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db)
            gears_integration.create_multiple_gears([gear_payload("Bike", user_id=user.id)], user.id, db)
            db.commit()
        members = {"activities.csv": _csv(_row(Filename="activities/1.fit"))}

        source = strava_bulk._build_source(user.id, "2026-10-15T00:00:00", members.get)

        assert list(source.strava_activities) == ["1.fit"]
        assert list(source.gear_nickname_to_id) == ["Bike"]
        assert (source.user_id, source.import_initiated_time) == (user.id, "2026-10-15T00:00:00")

    def test_an_archive_without_a_manifest_is_not_a_strava_export(self):
        with pytest.raises(core_exceptions.InvalidInputError):
            strava_bulk._build_source(uuid.uuid4(), "t", {}.get)

    def test_an_unreadable_manifest_is_refused(self):
        with pytest.raises(core_exceptions.InvalidInputError):
            strava_bulk._build_source(
                uuid.uuid4(), "t", {"activities.csv": b"Activity ID,Filename\n1,activities/1.fit\n"}.get
            )
