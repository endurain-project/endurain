"""Recording sign-ins against the devices a user is known to sign in from, and forgetting them."""

import threading
import time
import uuid
from datetime import UTC, datetime, timedelta

import jasil.runtime as jasil_runtime
import pytest
import sqlalchemy as sa
from jasil.events import Event

import core.database as core_database
import core.exceptions as core_exceptions
import core.hashing as core_hashing
import core.pagination as core_pagination
import modules.auth.known_devices.events as known_devices_events
import modules.auth.known_devices.models as known_devices_models
import modules.auth.known_devices.service as known_devices_service
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sessions.models as sessions_models
import modules.users.users.schema as users_schema
from tests._factories.devices import make_device_session, make_known_device
from tests._factories.users import make_user

_FIREFOX_ON_LINUX = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
_SAFARI_ON_MAC = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.0 Safari/605.1.15"
)
_DEVICE_ID = "d" * 43
_OTHER_DEVICE_ID = "o" * 43
_PASSWORD = known_devices_events.SignInMethod.PASSWORD
_PAGE = core_pagination.PageParams(1, 10)
_HASH = core_hashing.sha256_hex


@pytest.fixture
def announced() -> list[Event]:
    """The new-device sign-in events published during the test, as the bus delivers them."""
    events: list[Event] = []
    jasil_runtime.get_active_platform().events.subscribe(known_devices_events.NEW_DEVICE_SIGN_IN, events.append)
    return events


def _account(db, *, age: timedelta = timedelta(days=30)) -> users_schema.UserRead:
    """An account whose creation was ``age`` ago."""
    return make_user(db, created_at=datetime.now(UTC) - age)


def _sign_in(db, user, *, device_id=None, user_agent=_FIREFOX_ON_LINUX, method=_PASSWORD):
    """Record a sign-in as its caller does, and commit it."""
    record = known_devices_service.record_sign_in(user.id, device_id, "203.0.113.7", user_agent, method, db)
    db.commit()
    return record


def _hashes(db, user_id) -> set[str]:
    model = known_devices_models.KnownDevice
    return set(db.scalars(sa.select(model.device_hash).where(model.user_id == user_id)))


def _device_row_id(db, user_id, device_id) -> uuid.UUID:
    model = known_devices_models.KnownDevice
    return db.scalars(sa.select(model.id).where(model.user_id == user_id, model.device_hash == _HASH(device_id))).one()


def _session_ids(db) -> set[uuid.UUID]:
    return set(db.scalars(sa.select(sessions_models.UsersSessions.id)))


def _security_change(db, user) -> None:
    security_generation_integration.stage_bump(user.id, db)
    db.flush()


class TestSignIn:
    def test_a_known_device_is_seen_again_without_an_event(self, db, announced):
        user = _account(db)
        make_known_device(db, user.id, _HASH(_DEVICE_ID))
        old = datetime.now(UTC) - timedelta(days=30)
        db.execute(sa.update(known_devices_models.KnownDevice).values(last_seen_at=old))

        record = _sign_in(db, user, device_id=_DEVICE_ID)

        assert (record.device_id, record.new_device) == (_DEVICE_ID, False)
        assert announced == []
        db.expire_all()
        assert db.scalars(sa.select(known_devices_models.KnownDevice.last_seen_at)).one() > old + timedelta(days=29)

    def test_a_cookie_new_to_the_user_is_registered_as_is_and_announced(self, db, announced):
        user = _account(db)
        make_known_device(db, user.id, _HASH(_OTHER_DEVICE_ID))

        record = _sign_in(db, user, device_id=_DEVICE_ID)

        assert (record.device_id, record.new_device) == (_DEVICE_ID, True)
        assert _hashes(db, user.id) == {_HASH(_OTHER_DEVICE_ID), _HASH(_DEVICE_ID)}
        assert len(announced) == 1

    def test_another_users_browser_keeps_its_id_and_is_announced_without_touching_theirs(self, db, announced):
        user, other = _account(db), _account(db)
        make_known_device(db, user.id, _HASH(_OTHER_DEVICE_ID))
        make_known_device(db, other.id, _HASH(_DEVICE_ID))

        record = _sign_in(db, user, device_id=_DEVICE_ID)

        assert (record.device_id, record.new_device) == (_DEVICE_ID, True)
        assert _hashes(db, user.id) == {_HASH(_OTHER_DEVICE_ID), _HASH(_DEVICE_ID)}
        assert _hashes(db, other.id) == {_HASH(_DEVICE_ID)}

    def test_a_browser_without_a_cookie_gets_a_new_id_that_is_stored_only_as_a_hash(self, db, announced):
        user = _account(db)
        make_known_device(db, user.id, _HASH(_OTHER_DEVICE_ID))

        record = _sign_in(db, user)

        assert len(record.device_id) == 43
        assert set(record.device_id) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
        assert _HASH(record.device_id) in _hashes(db, user.id)
        assert record.device_id not in _hashes(db, user.id)
        assert (record.new_device, len(announced)) == (True, 1)

    def test_each_browser_without_a_cookie_gets_its_own_id(self, db, announced):
        user = _account(db)

        assert _sign_in(db, user).device_id != _sign_in(db, user).device_id

    def test_the_first_device_of_a_new_account_is_registered_without_an_event(self, db, announced):
        user = _account(db, age=timedelta(hours=23))

        record = _sign_in(db, user, device_id=_DEVICE_ID)

        assert (record.device_id, record.new_device) == (_DEVICE_ID, False)
        assert _hashes(db, user.id) == {_HASH(_DEVICE_ID)}
        assert announced == []

    def test_the_first_device_of_an_account_older_than_a_day_is_announced(self, db, announced):
        user = _account(db, age=timedelta(hours=25))

        record = _sign_in(db, user, device_id=_DEVICE_ID)

        assert _hashes(db, user.id) == {_HASH(_DEVICE_ID)}
        assert (record.new_device, len(announced)) == (True, 1)

    def test_a_user_whose_devices_were_all_forgotten_is_announced_on_the_next_device(self, db, announced):
        user = _account(db, age=timedelta(days=500))
        make_known_device(db, user.id, _HASH(_OTHER_DEVICE_ID))
        known_devices_service.forget_other_devices(user.id, None, db)
        assert _hashes(db, user.id) == set()

        record = _sign_in(db, user, device_id=_DEVICE_ID)

        assert (record.new_device, len(announced)) == (True, 1)

    def test_the_event_names_the_browser_the_address_and_the_method_but_no_device_id(self, db, announced):
        user = _account(db)
        make_known_device(db, user.id, _HASH(_OTHER_DEVICE_ID))

        _sign_in(db, user, device_id=_DEVICE_ID, method=known_devices_events.SignInMethod.IDENTITY_PROVIDER)

        (event,) = announced
        assert event.event_type == known_devices_events.NEW_DEVICE_SIGN_IN
        payload = dict(event.payload)
        assert abs(datetime.now(UTC) - datetime.fromisoformat(payload.pop("signed_in_at"))) < timedelta(minutes=1)
        assert payload == {
            "user_id": str(user.id),
            "browser": "Firefox",
            "operating_system": "Linux",
            "device_type": "PC",
            "ip_address": "203.0.113.7",
            "method": "identity_provider",
        }
        assert _DEVICE_ID not in repr(event) and _HASH(_DEVICE_ID) not in repr(event)

    def test_a_device_is_described_by_the_user_agent_at_creation_and_at_each_sign_in(self, db, announced):
        user = _account(db)
        _sign_in(db, user, device_id=_DEVICE_ID)
        model = known_devices_models.KnownDevice
        row = db.scalars(sa.select(model)).one()
        assert (row.browser, row.operating_system, row.device_type) == ("Firefox", "Linux", "PC")

        _sign_in(db, user, device_id=_DEVICE_ID, user_agent=_SAFARI_ON_MAC)
        db.refresh(row)

        assert (row.browser, row.operating_system) == ("Safari", "Mac OS X")


class TestKnownDevice:
    def test_a_device_the_user_signed_in_from_is_known(self, db):
        user = _account(db)
        make_known_device(db, user.id, _HASH(_DEVICE_ID))

        assert known_devices_service.is_known_device(user.id, _DEVICE_ID, db) is True

    def test_another_users_device_and_no_device_id_are_not_known(self, db):
        user, other = _account(db), _account(db)
        make_known_device(db, other.id, _HASH(_DEVICE_ID))

        assert known_devices_service.is_known_device(user.id, _DEVICE_ID, db) is False
        assert known_devices_service.is_known_device(other.id, None, db) is False

    def test_looking_a_device_up_registers_and_touches_nothing(self, db, announced):
        user = _account(db)
        make_known_device(db, user.id, _HASH(_DEVICE_ID))
        old = datetime.now(UTC) - timedelta(days=30)
        db.execute(sa.update(known_devices_models.KnownDevice).values(last_seen_at=old))
        db.expire_all()

        known_devices_service.is_known_device(user.id, _DEVICE_ID, db)
        known_devices_service.is_known_device(user.id, _OTHER_DEVICE_ID, db)

        assert db.scalars(sa.select(known_devices_models.KnownDevice.last_seen_at)).one() == old
        assert _hashes(db, user.id) == {_HASH(_DEVICE_ID)}
        assert announced == []


class TestSecurityChange:
    def test_a_device_known_before_a_security_change_is_no_longer_known(self, db):
        user = _account(db)
        _sign_in(db, user, device_id=_DEVICE_ID)
        assert known_devices_service.is_known_device(user.id, _DEVICE_ID, db) is True

        _security_change(db, user)

        assert known_devices_service.is_known_device(user.id, _DEVICE_ID, db) is False

    def test_a_sign_in_from_such_a_device_is_announced_and_restamps_it(self, db, announced):
        user = _account(db)
        _sign_in(db, user, device_id=_DEVICE_ID)
        announced.clear()
        _security_change(db, user)

        record = _sign_in(db, user, device_id=_DEVICE_ID)

        assert (record.new_device, len(announced)) == (True, 1)
        assert known_devices_service.is_known_device(user.id, _DEVICE_ID, db) is True
        assert len(_hashes(db, user.id)) == 1
        assert _sign_in(db, user, device_id=_DEVICE_ID).new_device is False
        assert len(announced) == 1

    def test_a_new_account_announces_a_new_device_after_a_security_change(self, db, announced):
        user = _account(db, age=timedelta(hours=1))
        _sign_in(db, user, device_id=_DEVICE_ID)
        _security_change(db, user)

        record = _sign_in(db, user, device_id=_OTHER_DEVICE_ID)

        assert (record.new_device, len(announced)) == (True, 1)


class TestList:
    def test_the_list_holds_only_devices_of_the_current_generation_and_marks_the_current_one(self, db):
        user = _account(db)
        _sign_in(db, user, device_id=_OTHER_DEVICE_ID)
        _security_change(db, user)
        _sign_in(db, user, device_id=_DEVICE_ID)

        page = known_devices_service.list_devices(user.id, _DEVICE_ID, _PAGE, db)

        assert page.total == 1
        (item,) = page.items
        assert item.is_current is True
        assert (item.browser, item.operating_system, item.device_type) == ("Firefox", "Linux", "PC")

    def test_another_device_is_listed_as_not_current(self, db):
        user = _account(db)
        _sign_in(db, user, device_id=_OTHER_DEVICE_ID)

        page = known_devices_service.list_devices(user.id, _DEVICE_ID, _PAGE, db)

        assert [item.is_current for item in page.items] == [False]
        assert [item.is_current for item in known_devices_service.list_devices(user.id, None, _PAGE, db).items] == [
            False
        ]

    def test_the_pages_split_the_devices(self, db):
        user = _account(db)
        for index in range(3):
            make_known_device(db, user.id, _HASH(f"{index}" * 43))

        first = known_devices_service.list_devices(user.id, None, core_pagination.PageParams(1, 2), db)
        second = known_devices_service.list_devices(user.id, None, core_pagination.PageParams(2, 2), db)

        assert (len(first.items), len(second.items), first.total) == (2, 1, 3)


class TestForget:
    def test_forgetting_a_device_ends_its_sessions_and_only_those(self, db):
        user, other = _account(db), _account(db)
        _sign_in(db, user, device_id=_DEVICE_ID)
        _sign_in(db, user, device_id=_OTHER_DEVICE_ID)
        on_device = {make_device_session(db, user, _HASH(_DEVICE_ID)) for _ in range(2)}
        kept = {
            make_device_session(db, user, _HASH(_OTHER_DEVICE_ID)),
            make_device_session(db, user, None),
            make_device_session(db, other, _HASH(_DEVICE_ID)),
        }

        ended = known_devices_service.forget_device(
            _device_row_id(db, user.id, _DEVICE_ID), user.id, _OTHER_DEVICE_ID, db
        )

        assert ended == 2
        assert _session_ids(db) == kept
        assert on_device.isdisjoint(_session_ids(db))
        assert known_devices_service.is_known_device(user.id, _DEVICE_ID, db) is False
        assert known_devices_service.is_known_device(user.id, _OTHER_DEVICE_ID, db) is True

    def test_a_device_nothing_signed_in_from_ends_no_session(self, db):
        user = _account(db)
        _sign_in(db, user, device_id=_DEVICE_ID)

        assert (
            known_devices_service.forget_device(_device_row_id(db, user.id, _DEVICE_ID), user.id, _OTHER_DEVICE_ID, db)
            == 0
        )

    def test_the_device_the_request_comes_from_cannot_be_forgotten(self, db):
        user = _account(db)
        _sign_in(db, user, device_id=_DEVICE_ID)

        with pytest.raises(core_exceptions.ConflictError):
            known_devices_service.forget_device(_device_row_id(db, user.id, _DEVICE_ID), user.id, _DEVICE_ID, db)

        assert known_devices_service.is_known_device(user.id, _DEVICE_ID, db) is True

    def test_another_users_device_and_an_unknown_id_are_not_found_and_end_no_session(self, db):
        user, other = _account(db), _account(db)
        _sign_in(db, user, device_id=_DEVICE_ID)
        kept = make_device_session(db, user, _HASH(_DEVICE_ID))
        row_id = _device_row_id(db, user.id, _DEVICE_ID)

        with pytest.raises(core_exceptions.NotFoundError):
            known_devices_service.forget_device(row_id, other.id, None, db)
        with pytest.raises(core_exceptions.NotFoundError):
            known_devices_service.forget_device(uuid.uuid4(), user.id, None, db)

        assert known_devices_service.is_known_device(user.id, _DEVICE_ID, db) is True
        assert _session_ids(db) == {kept}

    def test_a_device_of_an_older_generation_cannot_be_forgotten_by_id(self, db):
        user = _account(db)
        _sign_in(db, user, device_id=_DEVICE_ID)
        row_id = _device_row_id(db, user.id, _DEVICE_ID)
        _security_change(db, user)

        with pytest.raises(core_exceptions.NotFoundError):
            known_devices_service.forget_device(row_id, user.id, None, db)

    def test_forgetting_the_others_keeps_the_current_one_and_ends_only_the_sessions_of_the_rest(self, db):
        user, other = _account(db), _account(db)
        _sign_in(db, user, device_id=_DEVICE_ID)
        _sign_in(db, user, device_id=_OTHER_DEVICE_ID)
        _sign_in(db, other, device_id=_OTHER_DEVICE_ID)
        kept = {
            make_device_session(db, user, _HASH(_DEVICE_ID)),
            make_device_session(db, user, None),
            make_device_session(db, other, _HASH(_OTHER_DEVICE_ID)),
        }
        for _ in range(2):
            make_device_session(db, user, _HASH(_OTHER_DEVICE_ID))

        ended = known_devices_service.forget_other_devices(user.id, _DEVICE_ID, db)

        assert ended == 2
        assert known_devices_service.is_known_device(user.id, _DEVICE_ID, db) is True
        assert known_devices_service.is_known_device(user.id, _OTHER_DEVICE_ID, db) is False
        assert known_devices_service.is_known_device(other.id, _OTHER_DEVICE_ID, db) is True
        assert _session_ids(db) == kept

    def test_forgetting_the_others_without_a_current_device_forgets_them_all(self, db):
        user = _account(db)
        _sign_in(db, user, device_id=_DEVICE_ID)
        _sign_in(db, user, device_id=_OTHER_DEVICE_ID)

        assert known_devices_service.forget_other_devices(user.id, None, db) == 0

        assert known_devices_service.list_devices(user.id, None, _PAGE, db).total == 0

    def test_forgetting_the_others_after_a_security_change_ends_the_sessions_of_every_generation(self, db):
        user = _account(db)
        _sign_in(db, user, device_id=_DEVICE_ID)
        _sign_in(db, user, device_id=_OTHER_DEVICE_ID)
        kept = make_device_session(db, user, _HASH(_DEVICE_ID))
        make_device_session(db, user, _HASH(_OTHER_DEVICE_ID))
        _security_change(db, user)
        _sign_in(db, user, device_id=_DEVICE_ID)

        ended = known_devices_service.forget_other_devices(user.id, _DEVICE_ID, db)

        assert ended == 1
        assert _hashes(db, user.id) == {_HASH(_DEVICE_ID)}
        assert _session_ids(db) == {kept}

    def test_forgetting_all_devices_after_a_security_change_ends_every_session_that_has_a_device(self, db):
        user = _account(db)
        _sign_in(db, user, device_id=_DEVICE_ID)
        _sign_in(db, user, device_id=_OTHER_DEVICE_ID)
        predates_tracking = make_device_session(db, user, None)
        make_device_session(db, user, _HASH(_DEVICE_ID))
        make_device_session(db, user, _HASH(_OTHER_DEVICE_ID))
        _security_change(db, user)
        _sign_in(db, user, device_id=_DEVICE_ID)

        ended = known_devices_service.forget_other_devices(user.id, None, db)

        assert ended == 2
        assert _hashes(db, user.id) == set()
        assert _session_ids(db) == {predates_tracking}


class TestForgetCommitted:
    def test_forgetting_the_others_after_a_generation_bump_survives_the_commit(self, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db)
            kept_hash, forgotten_hash = _HASH("k" * 43), _HASH("f" * 43)
            make_known_device(db, user.id, kept_hash)
            make_known_device(db, user.id, forgotten_hash)
            kept = make_device_session(db, user, kept_hash)
            make_device_session(db, user, forgotten_hash)
            security_generation_integration.stage_bump(user.id, db)
            db.commit()

        with committed_sessions() as db:
            assert known_devices_service.forget_other_devices(user.id, "k" * 43, db) == 1
            db.commit()

        with committed_sessions() as db:
            assert _session_ids(db) == {kept}
            assert _hashes(db, user.id) == {kept_hash}


class TestConcurrentSignIn:
    def test_a_sign_in_that_loses_the_race_to_register_a_device_announces_nothing(self, committed_sessions, announced):
        with committed_sessions() as db:
            user = _account(db)
            make_known_device(db, user.id, _HASH(_OTHER_DEVICE_ID))
            db.commit()
        outcome: list[object] = []

        with (
            committed_sessions() as first,
            core_database.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as monitor,
        ):
            known_devices_service.record_sign_in(
                user.id, _DEVICE_ID, "203.0.113.7", _FIREFOX_ON_LINUX, _PASSWORD, first
            )

            def second_sign_in() -> None:
                with committed_sessions() as db:
                    record = known_devices_service.record_sign_in(
                        user.id, _DEVICE_ID, "203.0.113.8", _FIREFOX_ON_LINUX, _PASSWORD, db
                    )
                    db.commit()
                    outcome.append(record)

            thread = threading.Thread(target=second_sign_in)
            thread.start()
            deadline = time.monotonic() + 30
            while thread.is_alive() and not _insert_is_waiting(monitor) and time.monotonic() < deadline:
                thread.join(timeout=0.05)
            first.commit()
            thread.join(timeout=30)

        (record,) = outcome
        assert (record.device_id, record.new_device) == (_DEVICE_ID, False)
        assert len(announced) == 1
        with committed_sessions() as db:
            assert _hashes(db, user.id) == {_HASH(_OTHER_DEVICE_ID), _HASH(_DEVICE_ID)}


def _insert_is_waiting(monitor) -> bool:
    """Whether another session is blocked on a lock, read on an AUTOCOMMIT connection so each poll sees fresh state."""
    return bool(
        monitor.execute(
            sa.text("SELECT 1 FROM pg_stat_activity WHERE datname = current_database() AND wait_event_type = 'Lock'")
        ).first()
    )


class TestPrune:
    def test_devices_unseen_for_the_retention_are_deleted_and_the_rest_kept(self, db):
        user = _account(db)
        now = datetime(2026, 11, 1, tzinfo=UTC)
        make_known_device(db, user.id, "a" * 64)
        make_known_device(db, user.id, "b" * 64)
        for device_hash, seen in (("a" * 64, now - timedelta(days=401)), ("b" * 64, now - timedelta(days=399))):
            db.execute(
                sa.update(known_devices_models.KnownDevice)
                .where(known_devices_models.KnownDevice.device_hash == device_hash)
                .values(last_seen_at=seen)
            )
        db.flush()

        assert known_devices_service.delete_unseen_devices(now, db) == 1
        assert _hashes(db, user.id) == {"b" * 64}
