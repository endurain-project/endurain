"""The ids a job created are kept in a ``jsonb`` column, against real PostgreSQL (other databases use ``json``)."""

import uuid

from sqlalchemy import text
from tests._factories.users import make_user

import modules.activities.activity_ingestion.constants as ingestion_constants
import modules.activities.activity_ingestion.crud as ingestion_crud


def _pending_job(factory) -> tuple[uuid.UUID, uuid.UUID]:
    job_id = uuid.uuid4()
    with factory() as db:
        user_id = make_user(db).id
        ingestion_crud.create_ingestion_job(
            job_id, user_id, ingestion_constants.IngestionJobKind.UPLOAD, db, filename="ride.gpx", staged_key="key"
        )
        db.commit()
    return job_id, user_id


def _complete(factory, job_id: uuid.UUID, activity_ids: list[uuid.UUID]) -> None:
    with factory() as db:
        ingestion_crud.mark_completed(job_id, activity_ids, db)
        db.commit()


def test_the_column_is_jsonb(committed_sessions):
    with committed_sessions() as db:
        column_type = db.execute(
            text(
                "SELECT data_type FROM information_schema.columns"
                " WHERE table_name = 'activity_ingestion_jobs' AND column_name = 'activity_ids'"
            )
        ).scalar_one()

    assert column_type == "jsonb"


def test_a_job_that_created_nothing_yet_has_no_ids_and_a_completed_one_lists_them_in_order(committed_sessions):
    job_id, user_id = _pending_job(committed_sessions)
    with committed_sessions() as db:
        assert ingestion_crud.get_ingestion_job(job_id, user_id, db).activity_ids == []
        assert db.execute(text("SELECT activity_ids IS NULL FROM activity_ingestion_jobs")).scalar_one() is True
    created = [uuid.uuid4() for _ in range(3)]

    _complete(committed_sessions, job_id, created)

    with committed_sessions() as db:
        assert ingestion_crud.get_ingestion_job(job_id, user_id, db).activity_ids == created


def test_a_long_list_keeps_its_length_and_order(committed_sessions):
    job_id, user_id = _pending_job(committed_sessions)
    created = [uuid.uuid4() for _ in range(2500)]

    _complete(committed_sessions, job_id, created)

    with committed_sessions() as db:
        assert ingestion_crud.get_ingestion_job(job_id, user_id, db).activity_ids == created


def test_the_stored_ids_can_be_searched_as_a_json_array(committed_sessions):
    job_id, _user_id = _pending_job(committed_sessions)
    created = [uuid.uuid4(), uuid.uuid4()]
    _complete(committed_sessions, job_id, created)

    with committed_sessions() as db:
        statement = text(
            "SELECT id FROM activity_ingestion_jobs WHERE jsonb_typeof(activity_ids) = 'array'"
            " AND activity_ids @> CAST(:wanted AS jsonb)"
        )
        found = db.execute(statement, {"wanted": f'["{created[1]}"]'}).scalars().all()
        missing = db.execute(statement, {"wanted": f'["{uuid.uuid4()}"]'}).scalars().all()

    assert found == [job_id]
    assert missing == []


def test_a_completed_job_does_not_take_a_second_list(committed_sessions):
    job_id, user_id = _pending_job(committed_sessions)
    first = [uuid.uuid4()]
    _complete(committed_sessions, job_id, first)

    _complete(committed_sessions, job_id, [uuid.uuid4()])

    with committed_sessions() as db:
        assert ingestion_crud.get_ingestion_job(job_id, user_id, db).activity_ids == first
