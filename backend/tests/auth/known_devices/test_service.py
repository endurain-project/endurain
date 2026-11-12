"""Tests for recording sign-ins against the devices a user is known to sign in from."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select

import core.exceptions as core_exceptions
import core.hashing as core_hashing
import core.pagination as core_pagination
import modules.auth.known_devices.contracts as known_devices_contracts
import modules.auth.known_devices.crud as known_devices_crud
import modules.auth.known_devices.events as known_devices_events
import modules.auth.known_devices.models as known_devices_models
import modules.auth.known_devices.service as known_devices_service
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sessions.models as sessions_models
import modules.users.users.models as users_models
from tests._helpers.db import create_sqlite_session

_PUBLISH = "modules.auth.known_devices.event_publishers.platform_publisher.publish_on_commit"
_PUBLISH_REVOKED = "modules.auth.sessions.event_publishers.platform_publisher.publish_on_commit"
_FIREFOX_ON_LINUX = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
_DEVICE_ID = "d" * 43
_OTHER_DEVICE_ID = "o" * 43
_PASSWORD = known_devices_events.SignInMethod.PASSWORD
_DESCRIPTION = known_devices_contracts.DeviceDescription(browser="Firefox", operating_system="Linux", device_type="PC")


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
    known_devices_crud.create_device(
        user_id, core_hashing.sha256_hex(device_id), 0, datetime.now(UTC), _DESCRIPTION, db
    )


def _session(db, session_id, user_id, device_hash):
    now = datetime.now(UTC)
    db.add(
        sessions_models.UsersSessions(
            id=session_id,
            user_id=user_id,
            refresh_token="hashed",
            ip_address="203.0.113.7",
            device_type="PC",
            operating_system="Linux",
            operating_system_version="1",
            browser="Firefox",
            browser_version="1",
            created_at=now,
            last_activity_at=now,
            expires_at=now + timedelta(days=1),
            tokens_exchanged=True,
            token_family_id=session_id,
            rotation_count=0,
            client_type="web",
            auth_time=now,
            amr=["pwd"],
            device_hash=device_hash,
        )
    )
    db.flush()


def _session_ids(db):
    return set(db.execute(select(sessions_models.UsersSessions.id)).scalars())


class TestWebSignIn:
    def test_a_known_device_is_seen_again_without_an_event(self, db, publish):
        old = datetime.now(UTC) - timedelta(days=30)
        known_devices_crud.create_device(1, core_hashing.sha256_hex(_DEVICE_ID), 0, old, _DESCRIPTION, db)

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
        known_devices_crud.create_device(1, core_hashing.sha256_hex(_DEVICE_ID), 0, old, _DESCRIPTION, db)

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
        known_devices_crud.create_device(1, "a" * 64, 0, now - timedelta(days=401), _DESCRIPTION, db)
        known_devices_crud.create_device(1, "b" * 64, 0, now - timedelta(days=399), _DESCRIPTION, db)
        db.commit()

        assert known_devices_service.delete_unseen_devices(now, db) == 1
        assert _hashes(db, 1) == {"b" * 64}


def _security_change(db, user_id=1):
    """Advance the account's security generation, as every security change does."""
    security_generation_integration.stage_bump(user_id, db)


class TestSecurityChange:
    def test_a_device_known_before_a_security_change_is_no_longer_known(self, db, publish):
        _account(db, age=timedelta(days=30))
        _record(db, device_id=_DEVICE_ID)
        assert known_devices_service.is_known_device(1, _DEVICE_ID, db) is True

        _security_change(db)

        assert known_devices_service.is_known_device(1, _DEVICE_ID, db) is False

    def test_a_sign_in_from_a_device_known_before_a_security_change_is_announced_and_restamps_it(self, db, publish):
        _account(db, age=timedelta(days=30))
        _record(db, device_id=_DEVICE_ID)
        publish.reset_mock()
        _security_change(db)

        record = _sign_in(db, device_id=_DEVICE_ID)

        assert record.new_device is True
        publish.assert_called_once()
        assert known_devices_service.is_known_device(1, _DEVICE_ID, db) is True
        assert len(_hashes(db, 1)) == 1
        publish.reset_mock()
        assert _sign_in(db, device_id=_DEVICE_ID).new_device is False
        publish.assert_not_called()

    def test_a_new_account_announces_a_new_device_after_a_security_change(self, db, publish):
        _account(db, age=timedelta(hours=1))
        _record(db, device_id=_DEVICE_ID)
        publish.reset_mock()
        _security_change(db)

        record = _sign_in(db, device_id="another-device-id")

        assert record.new_device is True
        publish.assert_called_once()


class TestDescription:
    def test_a_device_is_described_by_the_user_agent_at_creation_and_at_each_sign_in(self, db, publish):
        _account(db, age=timedelta(days=30))
        _record(db, device_id=_DEVICE_ID)
        model = known_devices_models.KnownDevice
        row = db.execute(select(model)).scalar_one()
        assert (row.browser, row.operating_system, row.device_type) == ("Firefox", "Linux", "PC")

        known_devices_service.record_sign_in(
            1,
            _DEVICE_ID,
            "203.0.113.7",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.0 Safari/605.1.15",
            _PASSWORD,
            db,
        )
        db.refresh(row)

        assert (row.browser, row.operating_system) == ("Safari", "Mac OS X")


class TestListAndForget:
    def test_the_list_holds_only_devices_of_the_current_generation_and_marks_the_current_one(self, db, publish):
        _account(db, age=timedelta(days=30))
        _record(db, device_id=_OTHER_DEVICE_ID)
        _security_change(db)
        _record(db, device_id=_DEVICE_ID)

        page = known_devices_service.list_devices(1, _DEVICE_ID, core_pagination.PageParams(1, 10), db)

        assert page.total == 1
        assert [item.current for item in page.items] == [True]
        assert (page.items[0].browser, page.items[0].operating_system, page.items[0].device_type) == (
            "Firefox",
            "Linux",
            "PC",
        )

    def test_another_device_is_listed_as_not_current(self, db, publish):
        _account(db, age=timedelta(days=30))
        _record(db, device_id=_OTHER_DEVICE_ID)

        page = known_devices_service.list_devices(1, _DEVICE_ID, core_pagination.PageParams(1, 10), db)

        assert [item.current for item in page.items] == [False]

    def test_a_forgotten_device_is_no_longer_known(self, db, publish):
        _account(db, age=timedelta(days=30))
        _record(db, device_id=_DEVICE_ID)
        device_id = known_devices_service.list_devices(1, None, core_pagination.PageParams(1, 10), db).items[0].id

        known_devices_service.forget_device(device_id, 1, _OTHER_DEVICE_ID, db)

        assert known_devices_service.is_known_device(1, _DEVICE_ID, db) is False

    def test_the_device_the_request_comes_from_cannot_be_forgotten(self, db, publish):
        _account(db, age=timedelta(days=30))
        _record(db, device_id=_DEVICE_ID)
        device_id = known_devices_service.list_devices(1, None, core_pagination.PageParams(1, 10), db).items[0].id

        with pytest.raises(core_exceptions.ConflictError):
            known_devices_service.forget_device(device_id, 1, _DEVICE_ID, db)

        assert known_devices_service.is_known_device(1, _DEVICE_ID, db) is True

    def test_another_users_device_and_an_unknown_id_are_not_found(self, db, publish):
        _account(db, age=timedelta(days=30))
        _record(db, device_id=_DEVICE_ID)
        device_id = known_devices_service.list_devices(1, None, core_pagination.PageParams(1, 10), db).items[0].id

        with pytest.raises(core_exceptions.NotFoundError):
            known_devices_service.forget_device(device_id, 2, None, db)
        with pytest.raises(core_exceptions.NotFoundError):
            known_devices_service.forget_device(uuid.uuid4(), 1, None, db)
        assert known_devices_service.is_known_device(1, _DEVICE_ID, db) is True

    def test_forgetting_a_device_ends_its_sessions_and_only_those(self, db, publish):
        _account(db, age=timedelta(days=30))
        _account(db, user_id=2, age=timedelta(days=30))
        _record(db, device_id=_DEVICE_ID)
        _record(db, device_id=_OTHER_DEVICE_ID)
        device_hash = core_hashing.sha256_hex(_DEVICE_ID)
        _session(db, "on-device-1", 1, device_hash)
        _session(db, "on-device-2", 1, device_hash)
        _session(db, "on-other-device", 1, core_hashing.sha256_hex(_OTHER_DEVICE_ID))
        _session(db, "before-the-migration", 1, None)
        _session(db, "another-user", 2, device_hash)
        device_id = known_devices_service.list_devices(1, _DEVICE_ID, core_pagination.PageParams(1, 10), db)
        device_id = next(item.id for item in device_id.items if item.current)

        with patch(_PUBLISH_REVOKED) as revoked:
            ended = known_devices_service.forget_device(device_id, 1, _OTHER_DEVICE_ID, db)

        assert ended == 2
        assert _session_ids(db) == {"on-other-device", "before-the-migration", "another-user"}
        assert revoked.call_count == 2

    def test_forgetting_the_other_devices_keeps_the_current_one_and_ends_only_the_sessions_of_the_rest(
        self, db, publish
    ):
        _account(db, age=timedelta(days=30))
        _account(db, user_id=2, age=timedelta(days=30))
        _record(db, device_id=_DEVICE_ID)
        _record(db, device_id=_OTHER_DEVICE_ID)
        current_hash, other_hash = core_hashing.sha256_hex(_DEVICE_ID), core_hashing.sha256_hex(_OTHER_DEVICE_ID)
        _session(db, "on-current", 1, current_hash)
        _session(db, "on-other-1", 1, other_hash)
        _session(db, "on-other-2", 1, other_hash)
        _session(db, "before-the-migration", 1, None)
        _session(db, "another-user", 2, other_hash)

        with patch(_PUBLISH_REVOKED):
            ended = known_devices_service.forget_other_devices(1, _DEVICE_ID, db)

        assert ended == 2
        assert known_devices_service.is_known_device(1, _DEVICE_ID, db) is True
        assert known_devices_service.is_known_device(1, _OTHER_DEVICE_ID, db) is False
        assert _session_ids(db) == {"on-current", "before-the-migration", "another-user"}

    def test_forgetting_the_other_devices_without_a_current_device_forgets_them_all(self, db, publish):
        _account(db, age=timedelta(days=30))
        _record(db, device_id=_DEVICE_ID)
        _record(db, device_id=_OTHER_DEVICE_ID)

        assert known_devices_service.forget_other_devices(1, None, db) == 0

        assert known_devices_service.list_devices(1, None, core_pagination.PageParams(1, 10), db).total == 0

    def test_forgetting_the_other_devices_leaves_another_users_devices(self, db, publish):
        _account(db, age=timedelta(days=30))
        _account(db, user_id=2, age=timedelta(days=30))
        _record(db, device_id=_DEVICE_ID, user_id=2)

        known_devices_service.forget_other_devices(1, _OTHER_DEVICE_ID, db)

        assert known_devices_service.is_known_device(2, _DEVICE_ID, db) is True

    def test_a_device_nothing_signed_in_from_ends_no_session(self, db, publish):
        _account(db, age=timedelta(days=30))
        _record(db, device_id=_DEVICE_ID)
        device_id = known_devices_service.list_devices(1, None, core_pagination.PageParams(1, 10), db).items[0].id

        assert known_devices_service.forget_device(device_id, 1, _OTHER_DEVICE_ID, db) == 0

    def test_a_missing_device_ends_no_session(self, db, publish):
        _account(db, age=timedelta(days=30))
        _record(db, device_id=_DEVICE_ID)
        _session(db, "kept", 1, core_hashing.sha256_hex(_DEVICE_ID))

        with pytest.raises(core_exceptions.NotFoundError):
            known_devices_service.forget_device(uuid.uuid4(), 1, None, db)

        assert _session_ids(db) == {"kept"}

    def test_a_device_of_an_older_generation_cannot_be_forgotten_through_the_api(self, db, publish):
        _account(db, age=timedelta(days=30))
        _record(db, device_id=_DEVICE_ID)
        device_id = known_devices_service.list_devices(1, None, core_pagination.PageParams(1, 10), db).items[0].id
        _security_change(db)

        with pytest.raises(core_exceptions.NotFoundError):
            known_devices_service.forget_device(device_id, 1, None, db)
