"""Requesting an email change: the mails each address gets, the pending change and what makes it stale."""

from datetime import UTC, datetime, timedelta

import jasil.events as platform_events
import jasil.runtime as platform_runtime
import pytest
import sqlalchemy as sa
from jasil.providers import StateBackendUnavailableError

import core.config as core_config
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sign_up_tokens.events as sign_up_events
import modules.auth.sign_up_tokens.integration_service as sign_up_integration
import modules.auth.sign_up_tokens.models as sign_up_models
import modules.auth.sign_up_tokens.subscriber_registry as sign_up_subscriber_registry
import modules.users.users.models as users_models
from tests._factories.mail import configure_mail, events, outbox, token_in
from tests._factories.tokens import make_email_change
from tests._factories.users import make_user

_PUBLIC = f"{core_config.ROOT_PATH}/public"
_NEW = "new-address@example.com"
_SUBJECTS = {
    "confirm": "Endurain - Confirm your new email address",
    "requested": "Endurain - A change of your email address was requested",
    "requested_by_admin": "Endurain - An administrator asked to change your email address",
    "changed": "Endurain - Your email address was changed",
    "taken": "Endurain - Someone tried to use your email address",
}


@pytest.fixture
def mail_on(committed_sessions):
    """Mail is configured and the sign-up mail subscribers listen on the bus."""
    configure_mail(committed_sessions)
    sign_up_subscriber_registry.register_bus_subscribers(events())


@pytest.fixture
def seen_events():
    """Every sign-up event the bus carries, oldest first."""
    seen: list[platform_events.Event] = []
    for channel in (
        sign_up_events.EMAIL_CHANGE_REQUESTED,
        sign_up_events.EMAIL_CHANGE_VERIFICATION_REQUESTED,
        sign_up_events.EMAIL_CHANGED,
        sign_up_events.EMAIL_CHANGE_ADDRESS_TAKEN,
    ):
        events().subscribe(channel, seen.append)
    return seen


def _request(committed_sessions, user, address=_NEW, *, own=True):
    """Request the user's change the way an owner (or, with ``own=False``, an administrator) does; commit it."""
    with committed_sessions() as db:
        if own:
            staged = sign_up_integration.request_self_service_email_change(
                user.id, address, user.email, platform_runtime.get_state(), db
            )
        else:
            staged = sign_up_integration.request_email_change(user.id, address, user.email, db)
        db.commit()
    return staged


def _bump(committed_sessions, user) -> None:
    with committed_sessions() as db:
        security_generation_integration.stage_bump(user.id, db)
        db.commit()


def _subjects(address: str) -> list[str]:
    return [message.subject for message in outbox() if message.to == [address]]


def _mail_to(address: str, subject: str):
    (message,) = [m for m in outbox() if m.to == [address] and m.subject == subject]
    return message


def _email_of(committed_sessions, user_id) -> str:
    with committed_sessions() as db:
        return db.scalars(sa.select(users_models.Users.email).where(users_models.Users.id == user_id)).one()


def _user(committed_sessions, **fields):
    with committed_sessions() as db:
        user = make_user(db, **fields)
        db.commit()
    return user


class TestAnOwnersChangeToAFreeAddress:
    def test_each_address_gets_its_mail_and_the_links_carry_the_change_through(
        self, client, committed_sessions, mail_on
    ):
        user = _user(committed_sessions)

        assert _request(committed_sessions, user) is True

        confirm = _mail_to(_NEW, _SUBJECTS["confirm"])
        notice = _mail_to(user.email, _SUBJECTS["requested"])
        assert "/confirm-email-change#token=" in (confirm.text or "")
        assert "/cancel-email-change#token=" in (notice.text or "")
        assert client.post(f"{_PUBLIC}/email-change/confirm", json={"token": token_in(confirm)}).status_code == 204
        assert _email_of(committed_sessions, user.id) == _NEW
        changed = _mail_to(user.email, _SUBJECTS["changed"])
        assert token_in(changed, "/cancel-email-change#token=") == token_in(notice, "/cancel-email-change#token=")
        revert = client.post(
            f"{_PUBLIC}/email-change/cancel", json={"token": token_in(notice, "/cancel-email-change#token=")}
        )
        assert revert.json() == {"change_applied": True, "email_restored": True}
        assert _email_of(committed_sessions, user.id) == user.email

    def test_the_events_carry_ids_only(self, committed_sessions, mail_on, seen_events):
        user = _user(committed_sessions)

        _request(committed_sessions, user)

        assert {event.event_type for event in seen_events} == {
            sign_up_events.EMAIL_CHANGE_REQUESTED,
            sign_up_events.EMAIL_CHANGE_VERIFICATION_REQUESTED,
        }
        assert [event.payload for event in seen_events] == [{"user_id": str(user.id)}] * 2

    def test_a_replaced_request_voids_the_earlier_link(self, client, committed_sessions, mail_on):
        user = _user(committed_sessions)
        _request(committed_sessions, user, "first@example.com")
        _request(committed_sessions, user, "second@example.com")

        first = _mail_to("first@example.com", _SUBJECTS["confirm"])
        second = _mail_to("second@example.com", _SUBJECTS["confirm"])

        assert client.post(f"{_PUBLIC}/email-change/confirm", json={"token": token_in(first)}).status_code == 400
        assert client.post(f"{_PUBLIC}/email-change/confirm", json={"token": token_in(second)}).status_code == 204
        assert _email_of(committed_sessions, user.id) == "second@example.com"

    def test_without_a_mail_server_nothing_is_staged(self, committed_sessions):
        user = _user(committed_sessions)

        assert _request(committed_sessions, user) is False

        with committed_sessions() as db:
            assert db.scalars(sa.select(sign_up_models.SignUpToken)).all() == []
        assert outbox() == []


class TestAnOwnersChangeToAHeldAddress:
    def _held(self, committed_sessions):
        owner = _user(committed_sessions)
        holder = _user(committed_sessions, email="held@example.com")
        return owner, holder

    def test_it_is_staged_like_a_free_one_but_only_the_holder_is_told_and_no_link_is_made(
        self, committed_sessions, mail_on, seen_events
    ):
        owner, holder = self._held(committed_sessions)

        assert _request(committed_sessions, owner, holder.email) is True

        assert _subjects(holder.email) == [_SUBJECTS["taken"]]
        assert _subjects(owner.email) == [_SUBJECTS["requested"]]
        assert sign_up_events.EMAIL_CHANGE_VERIFICATION_REQUESTED not in {e.event_type for e in seen_events}
        with committed_sessions() as db:
            pending = sign_up_integration.get_pending_email_changes([owner.id], db)
        assert pending[owner.id].email == holder.email

    def test_a_second_attempt_inside_the_cooldown_tells_nobody_again(self, committed_sessions, mail_on):
        owner, holder = self._held(committed_sessions)

        _request(committed_sessions, owner, holder.email)
        _request(committed_sessions, owner, holder.email)

        assert _subjects(holder.email) == [_SUBJECTS["taken"]]

    def test_an_unreachable_cooldown_store_tells_nobody_and_the_request_is_still_staged(
        self, committed_sessions, mail_on, monkeypatch
    ):
        owner, holder = self._held(committed_sessions)

        def down(*_args, **_kwargs):
            raise StateBackendUnavailableError("down")

        monkeypatch.setattr(platform_runtime.get_state(), "set_if_absent", down)

        assert _request(committed_sessions, owner, holder.email) is True
        assert _subjects(holder.email) == []

    def test_a_resend_tells_the_holder_never_mails_a_link_and_shares_the_cooldown(self, committed_sessions, mail_on):
        owner, holder = self._held(committed_sessions)
        _request(committed_sessions, owner, holder.email)

        with committed_sessions() as db:
            sign_up_integration.request_email_change_resend(owner.id, platform_runtime.get_state(), db)
            db.commit()

        assert _subjects(holder.email) == [_SUBJECTS["taken"]]
        assert all(_SUBJECTS["confirm"] not in _subjects(address) for address in (holder.email, owner.email))

    def test_the_account_never_moves_to_a_held_address(self, client, committed_sessions, mail_on):
        owner, holder = self._held(committed_sessions)
        _request(committed_sessions, owner, holder.email)
        with committed_sessions() as db:
            token = db.scalars(sa.select(sign_up_models.SignUpToken)).one()
            assert token.email == holder.email

        assert _email_of(committed_sessions, owner.id) == owner.email

    def test_an_address_reserved_for_a_revert_window_is_treated_as_held(self, client, committed_sessions, mail_on):
        owner = _user(committed_sessions)
        other = _user(committed_sessions)
        with committed_sessions() as db:
            change = make_email_change(db, owner, "moved@example.com")
            db.commit()
        assert client.post(f"{_PUBLIC}/email-change/confirm", json={"token": change.token}).status_code == 204

        _request(committed_sessions, other, owner.email)

        assert _subjects("moved@example.com") == [_SUBJECTS["taken"]]
        with committed_sessions() as db:
            assert sign_up_integration.get_email_reserver_id(owner.email, None, db) == owner.id
            assert sign_up_integration.get_email_reserver_id(owner.email, owner.id, db) is None


class TestAnAdministratorsChange:
    def test_the_current_address_is_told_without_a_revert_link_and_the_new_one_gets_the_link(
        self, client, committed_sessions, mail_on
    ):
        user = _user(committed_sessions)

        assert _request(committed_sessions, user, own=False) is True

        notice = _mail_to(user.email, _SUBJECTS["requested_by_admin"])
        assert "cancel-email-change" not in (notice.text or "")
        confirm = _mail_to(_NEW, _SUBJECTS["confirm"])
        assert client.post(f"{_PUBLIC}/email-change/confirm", json={"token": token_in(confirm)}).status_code == 204
        changed = _mail_to(user.email, _SUBJECTS["changed"])
        assert "cancel-email-change" not in (changed.text or "")

    def test_without_a_mail_server_nothing_is_staged(self, committed_sessions):
        user = _user(committed_sessions)

        assert _request(committed_sessions, user, own=False) is False

    def test_a_security_change_since_the_request_stops_both_mails(self, committed_sessions, mail_on):
        user = _user(committed_sessions)
        with committed_sessions() as db:
            sign_up_integration.request_email_change(user.id, _NEW, user.email, db)
            _bump(committed_sessions, user)
            db.commit()

        assert outbox() == []


class TestASecurityChangeSinceTheRequest:
    def test_a_change_requested_before_it_cannot_be_confirmed(self, client, committed_sessions):
        user = _user(committed_sessions)
        with committed_sessions() as db:
            change = make_email_change(db, user, _NEW)
            db.commit()
        _bump(committed_sessions, user)

        response = client.post(f"{_PUBLIC}/email-change/confirm", json={"token": change.token})

        assert response.status_code == 400
        assert _email_of(committed_sessions, user.id) == user.email

    def test_a_change_requested_after_it_is_confirmed(self, client, committed_sessions, mail_on):
        user = _user(committed_sessions)
        _bump(committed_sessions, user)

        _request(committed_sessions, user)

        confirm = _mail_to(_NEW, _SUBJECTS["confirm"])
        assert client.post(f"{_PUBLIC}/email-change/confirm", json={"token": token_in(confirm)}).status_code == 204

    def test_the_mails_of_a_request_made_stale_before_delivery_are_not_sent(self, committed_sessions):
        user = _user(committed_sessions)
        configure_mail(committed_sessions)
        _request(committed_sessions, user)
        _bump(committed_sessions, user)
        sign_up_subscriber_registry.register_bus_subscribers(events())
        import modules.auth.sign_up_tokens.subscribers as sign_up_subscribers

        sign_up_subscribers.send_email_change_verification_email_for_event(
            platform_events.new_event(
                sign_up_events.EMAIL_CHANGE_VERIFICATION_REQUESTED, {"user_id": str(user.id)}, source="test"
            )
        )
        sign_up_subscribers.send_email_change_requested_email_for_event(
            platform_events.new_event(sign_up_events.EMAIL_CHANGE_REQUESTED, {"user_id": str(user.id)}, source="test")
        )

        assert outbox() == []


class TestThePendingChange:
    def test_each_users_unexpired_unused_change_is_listed_with_its_expiry(self, committed_sessions):
        with committed_sessions() as db:
            pending, expired, confirmed, none = make_user(db), make_user(db), make_user(db), make_user(db)
            live = make_email_change(db, pending, "pending@example.com")
            make_email_change(db, expired, "expired@example.com", expires_at=datetime.now(UTC) - timedelta(seconds=1))
            used = make_email_change(db, confirmed, "confirmed@example.com")
            db.commit()
        assert live.token
        with committed_sessions() as db:
            db.execute(
                sa.update(sign_up_models.SignUpToken)
                .where(sign_up_models.SignUpToken.user_id == confirmed.id)
                .values(used=True)
            )
            db.commit()
        assert used.token

        with committed_sessions() as db:
            listed = sign_up_integration.get_pending_email_changes([pending.id, expired.id, confirmed.id, none.id], db)

        assert {user_id: change.email for user_id, change in listed.items()} == {pending.id: "pending@example.com"}
        assert listed[pending.id].expires_at > datetime.now(UTC)

    def test_no_users_is_an_empty_result(self, db):
        assert sign_up_integration.get_pending_email_changes([], db) == {}


class TestResendingTheConfirmation:
    def test_it_mails_a_new_link_once_per_cooldown_and_the_old_link_stops_working(
        self, client, committed_sessions, mail_on
    ):
        user = _user(committed_sessions)
        _request(committed_sessions, user)
        old = token_in(_mail_to(_NEW, _SUBJECTS["confirm"]))

        for _ in range(2):
            with committed_sessions() as db:
                sign_up_integration.request_email_change_resend(user.id, platform_runtime.get_state(), db)
                db.commit()

        confirmations = [m for m in outbox() if m.to == [_NEW]]
        assert len(confirmations) == 2
        assert token_in(confirmations[1]) != old
        assert client.post(f"{_PUBLIC}/email-change/confirm", json={"token": old}).status_code == 400
        assert (
            client.post(f"{_PUBLIC}/email-change/confirm", json={"token": token_in(confirmations[1])}).status_code
            == 204
        )

    def test_it_keeps_the_revert_link_of_the_original_request(self, client, committed_sessions, mail_on):
        user = _user(committed_sessions)
        _request(committed_sessions, user)
        revert = token_in(_mail_to(user.email, _SUBJECTS["requested"]), "/cancel-email-change#token=")

        with committed_sessions() as db:
            sign_up_integration.request_email_change_resend(user.id, platform_runtime.get_state(), db)
            db.commit()
        confirm = [m for m in outbox() if m.to == [_NEW]][-1]
        client.post(f"{_PUBLIC}/email-change/confirm", json={"token": token_in(confirm)})

        response = client.post(f"{_PUBLIC}/email-change/cancel", json={"token": revert})
        assert response.json() == {"change_applied": True, "email_restored": True}

    def test_with_nothing_pending_or_without_a_mail_server_it_does_nothing(self, committed_sessions, mail_on):
        user = _user(committed_sessions)

        with committed_sessions() as db:
            sign_up_integration.request_email_change_resend(user.id, platform_runtime.get_state(), db)
            db.commit()

        assert outbox() == []

    def test_an_unreachable_cooldown_store_skips_the_resend(self, committed_sessions, mail_on, monkeypatch):
        user = _user(committed_sessions)
        _request(committed_sessions, user)
        before = len(outbox())

        def down(*_args, **_kwargs):
            raise StateBackendUnavailableError("down")

        monkeypatch.setattr(platform_runtime.get_state(), "set_if_absent", down)
        with committed_sessions() as db:
            sign_up_integration.request_email_change_resend(user.id, platform_runtime.get_state(), db)
            db.commit()

        assert len(outbox()) == before


class TestAChangeAnotherWriterApplied:
    def test_the_previous_address_is_told_without_a_revert_link_and_earlier_links_are_used_up(
        self, client, committed_sessions, mail_on
    ):
        user = _user(committed_sessions)
        with committed_sessions() as db:
            pending = make_email_change(db, user, "pending@example.com")
            db.commit()

        with committed_sessions() as db:
            sign_up_integration.stage_email_changed_notice(user.id, "synced@example.com", user.email, db)
            db.commit()

        notice = _mail_to(user.email, _SUBJECTS["changed"])
        assert "cancel-email-change" not in (notice.text or "")
        response = client.post(f"{_PUBLIC}/email-change/confirm", json={"token": pending.token})
        assert response.status_code == 400
