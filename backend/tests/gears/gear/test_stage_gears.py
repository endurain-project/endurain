"""Staging gears in bulk skips a nickname the user already has, whatever its case, against real PostgreSQL.

``stage_gears`` inserts each gear with ``INSERT ... ON CONFLICT DO NOTHING`` on the ``(user_id, lower(nickname))``
unique index, so PostgreSQL alone decides what counts as the same nickname, including for ``İ`` and ``Σ``.
"""

import pytest

import core.exceptions as core_exceptions
import modules.gears.gear.crud as gears_crud
import modules.gears.gear.service as gears_service
from tests._factories.gears import gear_payload
from tests._factories.users import make_user


@pytest.fixture
def user_id(db):
    return make_user(db).id


def _nicknames(db, user_id) -> list[str]:
    return sorted(gear.nickname for gear in gears_crud.get_gear_user(user_id, db))


class TestStageGears:
    @pytest.mark.parametrize("existing", ["Road Bike", "İstanbul Shoes", "ΣΑΣ Racquet", "Ärzte Bike"])
    def test_a_nickname_the_user_has_in_another_case_is_skipped(self, db, user_id, existing):
        gears_crud.create_gear(gear_payload(existing), user_id, db)

        gears_service.stage_gears([gear_payload(existing.upper()), gear_payload("Fresh")], user_id, db)

        assert _nicknames(db, user_id) == sorted([existing, "Fresh"])

    @pytest.mark.parametrize("nickname", ["Road Bike", "İstanbul Shoes", "ΣΑΣ Racquet"])
    def test_a_nickname_repeated_in_the_batch_is_staged_once(self, db, user_id, nickname):
        gears_service.stage_gears(
            [gear_payload(nickname), gear_payload(nickname.upper()), gear_payload("Other")], user_id, db
        )

        assert _nicknames(db, user_id) == sorted([nickname, "Other"])

    def test_the_same_nickname_is_staged_for_another_user(self, db, user_id):
        other_id = make_user(db).id
        gears_crud.create_gear(gear_payload("Road Bike"), other_id, db)

        gears_service.stage_gears([gear_payload("road bike")], user_id, db)

        assert _nicknames(db, user_id) == ["road bike"]

    def test_a_taken_provider_id_is_still_a_conflict(self, db, user_id):
        gears_crud.create_gear(gear_payload("One", strava_gear_id="b1"), user_id, db)

        with pytest.raises(core_exceptions.ConflictError, match="Strava or Garmin Connect ID"):
            gears_service.stage_gears([gear_payload("Two", strava_gear_id="b1")], user_id, db)

    def test_a_provider_id_repeated_in_the_batch_is_a_conflict(self, db, user_id):
        with pytest.raises(core_exceptions.ConflictError, match="Strava or Garmin Connect ID"):
            gears_service.stage_gears(
                [gear_payload("One", garminconnect_gear_id="g1"), gear_payload("Two", garminconnect_gear_id="g1")],
                user_id,
                db,
            )

    @pytest.mark.parametrize("order", ["provider-gear-first", "plain-gear-first"])
    def test_each_gear_keeps_the_fields_it_sent_whatever_the_others_send(self, db, user_id, order):
        """Payloads set different fields; one gear's omissions must not drop or refuse another's."""
        plain = gear_payload("Plain")
        provider = gear_payload("Provider", brand="Trek", strava_gear_id="b7")
        batch = [provider, plain] if order == "provider-gear-first" else [plain, provider]

        gears_service.stage_gears(batch, user_id, db)

        stored = {gear.nickname: (gear.brand, gear.strava_gear_id) for gear in gears_crud.get_gear_user(user_id, db)}
        assert stored == {"Plain": (None, None), "Provider": ("Trek", "b7")}

    def test_inserted_rows_read_back_complete(self, db, user_id):
        gears_service.stage_gears(
            [gear_payload("  Road Bike ", brand=" Trek ", strava_gear_id="b1", initial_distance=1500.0)], user_id, db
        )
        db.commit()

        (gear,) = gears_crud.get_gear_user(user_id, db)
        assert (gear.nickname, gear.brand, gear.strava_gear_id, gear.initial_distance) == (
            "Road Bike",
            "Trek",
            "b1",
            1500.0,
        )
        assert (gear.user_id, gear.version, gear.active) == (user_id, 1, True)
        assert gear.id is not None
        assert gear.updated_at is not None
        assert gear.acquired_on is not None
