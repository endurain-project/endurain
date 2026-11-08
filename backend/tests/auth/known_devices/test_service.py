"""Tests for recording sign-ins against the devices a user is known to sign in from."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select

import core.exceptions as core_exceptions
import core.hashing as core_hashing
import modules.auth.known_devices.crud as known_devices_crud
import modules.auth.known_devices.events as known_devices_events
import modules.auth.known_devices.models as known_devices_models
import modules.auth.known_devices.service as known_devices_service
import modules.users.users.models as users_models
from tests._helpers.db import create_sqlite_session

_PUBLISH = "modules.auth.known_devices.event_publishers.platform_publisher.publish_on_commit"
_FIREFOX_ON_LINUX = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
_DEVICE_ID = "d" * 43
_OTHER_DEVICE_ID = "o" * 43
_PASSWORD = known_devices_events.SignInMethod.PASSWORD


@pytest.fixture
def db():
    session = create_sqlite_session()
    yield session
    session.close()


@pytest.fixture
def publish():
    with patch(_PUBLISH) as publish_on_commit:
        yield publish_on_commit


def _account(db, *, user_id=1, age=timedelta(hours=1)):
    """Create a user row whose account is ``age`` old."""
    db.add(
        users_models.Users(
            id=user_id,
            name=f"User {user_id}",
            username=f"user{user_id}",
            email=f"user{user_id}@example.com",
            preferred_language="en",
            access_type="regular",
            created_at=datetime.now(UTC) - age,
        )
    )
    db.flush()


def _record(db, *, user_id=1, device_id=None, method=_PASSWORD):
    """Record a sign-in and return the device id it answers."""
    return _sign_in(db, user_id=user_id, device_id=device_id, method=method).device_id


def _sign_in(db, *, user_id=1, device_id=None, method=_PASSWORD):
    return known_devices_service.record_sign_in(user_id, device_id, "203.0.113.7", _FIREFOX_ON_LINUX, method, db)


def _hashes(db, user_id):
    model = known_devices_models.KnownDevice
    return set(db.execute(select(model.device_hash).where(model.user_id == user_id)).scalars())


def _known(db, user_id, device_id):
    known_devices_crud.create_device(user_id, core_hashing.sha256_hex(device_id), datetime.now(UTC), db)


class TestWebSignIn:
    def test_a_known_device_is_seen_again_without_an_event(self, db, publish):
        old = datetime.now(UTC) - timedelta(days=30)
        known_devices_crud.create_device(1, core_hashing.sha256_hex(_DEVICE_ID), old, db)

        record = _sign_in(db, device_id=_DEVICE_ID)

        assert record.device_id == _DEVICE_ID
        publish.assert_not_called()
        assert record.new_device is False
        model = known_devices_models.KnownDevice
        last_seen = db.execute(select(model.last_seen_at)).scalar_one().replace(tzinfo=UTC)
        assert last_seen > old + timedelta(days=29)

    def test_a_cookie_new_to_the_user_is_registered_as_is_and_announced(self, db, publish):
        _known(db, 1, _OTHER_DEVICE_ID)

        record = _sign_in(db, device_id=_DEVICE_ID)

        assert record.device_id == _DEVICE_ID
        assert core_hashing.sha256_hex(_DEVICE_ID) in _hashes(db, 1)
        publish.assert_called_once()
        assert record.new_device is True

    def test_another_users_browser_keeps_its_id_and_is_announced(self, db, publish):
        _known(db, 1, _OTHER_DEVICE_ID)
        _known(db, 2, _DEVICE_ID)

        issued = _record(db, device_id=_DEVICE_ID)

        assert issued == _DEVICE_ID
        assert _hashes(db, 1) == {core_hashing.sha256_hex(_OTHER_DEVICE_ID), core_hashing.sha256_hex(_DEVICE_ID)}
        assert _hashes(db, 2) == {core_hashing.sha256_hex(_DEVICE_ID)}
        publish.assert_called_once()

    def test_a_browser_without_a_cookie_gets_a_new_id_that_is_stored_only_as_a_hash(self, db, publish):
        _known(db, 1, _OTHER_DEVICE_ID)

        issued = _record(db)

        assert issued is not None
        assert len(issued) == 43
        assert set(issued) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
        assert core_hashing.sha256_hex(issued) in _hashes(db, 1)
        assert issued not in _hashes(db, 1)
        publish.assert_called_once()

    def test_each_browser_without_a_cookie_gets_its_own_id(self, db, publish):
        _account(db)

        assert _record(db) != _record(db)

    def test_the_first_device_of_a_new_account_is_registered_without_an_event(self, db, publish):
        _account(db, age=timedelta(hours=23))
        _known(db, 2, _DEVICE_ID)

        record = _sign_in(db, device_id=_DEVICE_ID)

        assert record.device_id == _DEVICE_ID
        assert _hashes(db, 1) == {core_hashing.sha256_hex(_DEVICE_ID)}
        publish.assert_not_called()
        assert record.new_device is False

    def test_the_first_device_of_an_account_older_than_a_day_is_announced(self, db, publish):
        _account(db, age=timedelta(hours=25))

        record = _sign_in(db, device_id=_DEVICE_ID)

        assert _hashes(db, 1) == {core_hashing.sha256_hex(_DEVICE_ID)}
        publish.assert_called_once()
        assert record.new_device is True

    def test_a_user_whose_devices_were_all_forgotten_is_announced_on_the_next_device(self, db, publish):
        _account(db, age=timedelta(days=500))
        _known(db, 1, _OTHER_DEVICE_ID)
        known_devices_service.delete_unseen_devices(datetime.now(UTC) + timedelta(days=401), db)
        assert _hashes(db, 1) == set()

        record = _sign_in(db, device_id=_DEVICE_ID)

        publish.assert_called_once()
        assert record.new_device is True

    def test_a_concurrent_first_sign_in_of_an_old_account_announces_it_once(self, db, publish):
        _account(db, age=timedelta(days=30))

        with patch.object(
            known_devices_service.known_devices_crud, "create_device", side_effect=core_exceptions.ConflictError("x")
        ):
            record = _sign_in(db, device_id=_DEVICE_ID)

        publish.assert_not_called()
        assert record.new_device is False

    def test_a_concurrent_sign_in_that_registered_the_device_first_announces_it_alone(self, db, publish):
        _known(db, 1, _OTHER_DEVICE_ID)

        with patch.object(
            known_devices_service.known_devices_crud, "create_device", side_effect=core_exceptions.ConflictError("x")
        ):
            record = _sign_in(db, device_id=_DEVICE_ID)

        assert record.device_id == _DEVICE_ID
        publish.assert_not_called()
        assert record.new_device is False

    def test_nothing_is_committed(self, mock_db, publish):
        mock_db.execute.return_value.rowcount = 0
        mock_db.execute.return_value.scalar.return_value = True

        _record(mock_db, device_id=_DEVICE_ID)

        mock_db.commit.assert_not_called()


class TestKnownDevice:
    def test_a_device_the_user_signed_in_from_is_known(self, db):
        _known(db, 1, _DEVICE_ID)

        assert known_devices_service.is_known_device(1, _DEVICE_ID, db) is True

    def test_another_users_device_is_not_known(self, db):
        _known(db, 2, _DEVICE_ID)

        assert known_devices_service.is_known_device(1, _DEVICE_ID, db) is False

    def test_no_device_id_is_never_known(self, db):
        _known(db, 1, _DEVICE_ID)

        assert known_devices_service.is_known_device(1, None, db) is False

    def test_looking_a_device_up_registers_and_touches_nothing(self, db, publish):
        old = datetime.now(UTC) - timedelta(days=30)
        known_devices_crud.create_device(1, core_hashing.sha256_hex(_DEVICE_ID), old, db)

        known_devices_service.is_known_device(1, _DEVICE_ID, db)
        known_devices_service.is_known_device(1, _OTHER_DEVICE_ID, db)

        model = known_devices_models.KnownDevice
        assert db.execute(select(model.last_seen_at)).scalar_one().replace(tzinfo=UTC) == old
        assert _hashes(db, 1) == {core_hashing.sha256_hex(_DEVICE_ID)}
        publish.assert_not_called()


class TestEvent:
    def test_the_event_names_the_browser_the_address_and_the_method_but_no_device_id(self, db, publish):
        _known(db, 1, _OTHER_DEVICE_ID)

        _record(db, device_id=_DEVICE_ID, method=known_devices_events.SignInMethod.IDENTITY_PROVIDER)

        event_type, payload = publish.call_args.args
        assert event_type == known_devices_events.NEW_DEVICE_SIGN_IN
        assert publish.call_args.kwargs["db"] is db
        signed_in_at = datetime.fromisoformat(payload.pop("signed_in_at"))
        assert abs(datetime.now(UTC) - signed_in_at) < timedelta(minutes=1)
        assert payload == {
            "user_id": 1,
            "browser": "Firefox",
            "operating_system": "Linux",
            "device_type": "PC",
            "ip_address": "203.0.113.7",
            "method": "identity_provider",
        }
        assert _DEVICE_ID not in repr(publish.call_args)
        assert core_hashing.sha256_hex(_DEVICE_ID) not in repr(publish.call_args)


class TestPrune:
    def test_devices_unseen_for_400_days_are_deleted(self, db):
        now = datetime(2026, 11, 1, tzinfo=UTC)
        known_devices_crud.create_device(1, "a" * 64, now - timedelta(days=401), db)
        known_devices_crud.create_device(1, "b" * 64, now - timedelta(days=399), db)
        db.commit()

        assert known_devices_service.delete_unseen_devices(now, db) == 1
        assert _hashes(db, 1) == {"b" * 64}
