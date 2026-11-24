"""The "this wasn't me" link of an email change: how it reverts runs of changes and when it is refused."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

import core.config as core_config
import modules.auth.sign_up_tokens.audit_actions as sign_up_audit_actions
import modules.auth.sign_up_tokens.integration_service as sign_up_integration
import modules.auth.sign_up_tokens.models as sign_up_models
import modules.auth.sign_up_tokens.service as sign_up_service
import modules.users.users.models as users_models
from tests._factories.tokens import audit_rows, make_email_change
from tests._factories.users import make_user

_PUBLIC = f"{core_config.ROOT_PATH}/public"
_PROFILE = f"{core_config.ROOT_PATH}/profile"
_FIRST, _SECOND = "first-address@example.com", "second-address@example.com"


def _confirm(client, token: str):
    return client.post(f"{_PUBLIC}/email-change/confirm", json={"token": token})


def _cancel(client, token: str):
    return client.post(f"{_PUBLIC}/email-change/cancel", json={"token": token})


def _email_of(committed_sessions, user_id) -> str:
    with committed_sessions() as db:
        return db.scalars(sa.select(users_models.Users.email).where(users_models.Users.id == user_id)).one()


def _two_changes(client, committed_sessions, *, confirm_second: bool):
    """A user whose address moved to ``_FIRST`` and is moving, or has moved, on to ``_SECOND``."""
    with committed_sessions() as db:
        user = make_user(db)
        first = make_email_change(db, user, _FIRST)
        db.commit()
    assert _confirm(client, first.token).status_code == 204
    with committed_sessions() as db:
        second = make_email_change(db, user.model_copy(update={"email": _FIRST}), _SECOND)
        db.commit()
    if confirm_second:
        assert _confirm(client, second.token).status_code == 204
    return user, first, second


class TestRunsOfChanges:
    def test_the_first_link_reverts_every_later_change_and_restores_the_address_it_was_mailed_to(
        self, client, committed_sessions
    ):
        user, first, second = _two_changes(client, committed_sessions, confirm_second=True)
        assert _email_of(committed_sessions, user.id) == _SECOND

        response = _cancel(client, first.revert_token)

        assert response.json() == {"change_applied": True, "email_restored": True}
        assert _email_of(committed_sessions, user.id) == user.email
        assert _cancel(client, second.revert_token).status_code == 400

    def test_a_later_changes_link_reverts_only_its_own_change(self, client, committed_sessions):
        user, first, second = _two_changes(client, committed_sessions, confirm_second=True)

        response = _cancel(client, second.revert_token)

        assert response.json() == {"change_applied": True, "email_restored": True}
        assert _email_of(committed_sessions, user.id) == _FIRST
        assert _cancel(client, first.revert_token).json() == {"change_applied": True, "email_restored": True}
        assert _email_of(committed_sessions, user.id) == user.email

    def test_a_revert_while_a_later_change_is_pending_voids_it(self, client, committed_sessions):
        user, first, second = _two_changes(client, committed_sessions, confirm_second=False)

        response = _cancel(client, first.revert_token)

        assert response.json() == {"change_applied": True, "email_restored": True}
        assert _confirm(client, second.token).status_code == 400
        assert _email_of(committed_sessions, user.id) == user.email

    def test_the_link_of_a_replaced_change_still_works_and_voids_its_replacement(self, client, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db)
            replaced = make_email_change(db, user, _FIRST)
            replacement = make_email_change(db, user, _SECOND)
            db.commit()

        response = _cancel(client, replaced.revert_token)

        assert response.json() == {"change_applied": False, "email_restored": False}
        assert _confirm(client, replacement.token).status_code == 400
        assert _email_of(committed_sessions, user.id) == user.email

    def test_an_expired_unconfirmed_change_is_still_reported_and_secures_the_account(
        self, client, committed_sessions, sign_in
    ):
        with committed_sessions() as db:
            user = make_user(db)
            change = make_email_change(db, user, _FIRST, expires_at=datetime.now(UTC) - timedelta(hours=1))
            db.commit()
        holder = sign_in(user)

        response = _cancel(client, change.revert_token)

        assert response.json() == {"change_applied": False, "email_restored": False}
        assert holder.client.get(_PROFILE).status_code == 401

    def test_the_link_still_works_six_days_after_the_request_and_not_after_seven(self, client, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db)
            inside = make_email_change(db, user, _FIRST, revert_window=timedelta(days=1))
            db.commit()
        with committed_sessions() as db:
            late = make_email_change(db, user, _SECOND, revert_window=-timedelta(seconds=1))
            db.commit()

        assert _cancel(client, late.revert_token).status_code == 400
        assert _cancel(client, inside.revert_token).status_code == 200

    def test_an_address_an_administrator_gave_the_account_since_is_replaced_by_the_restored_one(
        self, client, committed_sessions
    ):
        with committed_sessions() as db:
            user = make_user(db)
            change = make_email_change(db, user, _FIRST)
            db.commit()
        assert _confirm(client, change.token).status_code == 204
        with committed_sessions() as db:
            db.execute(sa.update(users_models.Users).where(users_models.Users.id == user.id).values(email=_SECOND))
            db.commit()

        response = _cancel(client, change.revert_token)

        assert response.json() == {"change_applied": True, "email_restored": True}
        assert _email_of(committed_sessions, user.id) == user.email


class TestRefusedLinks:
    @pytest.mark.parametrize(
        "link",
        ["no-dot", ".proof", "identifier.", "not-a-uuid.proof", f"{uuid.uuid4()}.proof", "é.é"],
        ids=["no-dot", "no-id", "no-proof", "not-a-uuid", "unknown-change", "non-ascii"],
    )
    def test_a_malformed_or_unknown_link_is_refused_and_audited_and_changes_nothing(
        self, client, committed_sessions, sign_in, link
    ):
        with committed_sessions() as db:
            user = make_user(db)
            db.commit()
        holder = sign_in(user)

        response = _cancel(client, link)

        assert response.status_code == 400
        assert response.json()["type"] == "urn:endurain:error:invalid-input"
        assert holder.client.get(_PROFILE).status_code == 200
        rows = audit_rows(committed_sessions, sign_up_audit_actions.EMAIL_CHANGE_CANCEL)
        assert [(row.outcome, row.target_id) for row in rows] == [("failure", None)]

    def test_a_forged_proof_for_a_real_change_is_refused(self, client, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db)
            change = make_email_change(db, user, _FIRST)
            db.commit()

        assert _cancel(client, f"{change.change_id}.{'0' * 43}").status_code == 400
        assert _cancel(client, f"{change.change_id}.{change.revert_token.split('.')[1][::-1]}").status_code == 400
        assert _cancel(client, change.revert_token).status_code == 200

    def test_a_change_that_records_no_previous_address_is_refused_and_secures_nothing(
        self, client, committed_sessions, sign_in
    ):
        change_id, revert_until = uuid.uuid4(), datetime.now(UTC) + timedelta(days=1)
        with committed_sessions() as db:
            user = make_user(db)
            db.add(
                sign_up_models.SignUpToken(
                    user_id=user.id,
                    token_hash="forged-change-row",
                    created_at=datetime.now(UTC),
                    expires_at=revert_until,
                    used=False,
                    email=_FIRST,
                    change_id=change_id,
                    revert_until=revert_until,
                )
            )
            db.commit()
        holder = sign_in(user)

        response = _cancel(client, f"{change_id}.{sign_up_service._revert_mac(change_id, revert_until)}")

        assert response.status_code == 400
        assert holder.client.get(_PROFILE).status_code == 200

    def test_an_extra_or_missing_field_is_422(self, client):
        assert client.post(f"{_PUBLIC}/email-change/cancel", json={}).status_code == 422
        assert client.post(f"{_PUBLIC}/email-change/cancel", json={"token": "a.b", "extra": 1}).status_code == 422


class TestTheReservedAddress:
    def test_it_is_reserved_only_after_the_change_is_confirmed_and_until_it_is_reverted(
        self, client, committed_sessions
    ):
        with committed_sessions() as db:
            user = make_user(db)
            change = make_email_change(db, user, _FIRST)
            db.commit()

        def reserver():
            with committed_sessions() as db:
                return sign_up_integration.get_email_reserver_id(user.email, None, db)

        assert reserver() is None
        assert _confirm(client, change.token).status_code == 204
        assert reserver() == user.id
        assert _cancel(client, change.revert_token).status_code == 200
        assert reserver() is None

    def test_an_address_is_not_reserved_past_its_window_or_for_the_account_that_asks(self, client, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db)
            change = make_email_change(db, user, _FIRST)
            db.commit()
        _confirm(client, change.token)
        with committed_sessions() as db:
            assert sign_up_integration.get_email_reserver_id(user.email, user.id, db) is None
            db.execute(sa.update(sign_up_models.SignUpToken).values(revert_until=datetime.now(UTC) - timedelta(1)))
            db.commit()
        with committed_sessions() as db:
            assert sign_up_integration.get_email_reserver_id(user.email, None, db) is None

    def test_a_change_an_administrator_made_reserves_nothing(self, client, committed_sessions):
        with committed_sessions() as db:
            user = make_user(db)
            db.commit()
        with committed_sessions() as db:
            sign_up_service.stage_email_changed_notice(user.id, _FIRST, user.email, db)
            db.commit()

        with committed_sessions() as db:
            assert sign_up_integration.get_email_reserver_id(user.email, None, db) is None
