"""The signed-in user's own sessions: listing them, ending one, ending the others and signing out everywhere."""

import uuid

import core.config as core_config
import modules.auth.security_generation.integration_service as security_generation_integration
import modules.auth.sessions.audit_actions as sessions_audit_actions
from tests._factories.account_security import session_ids
from tests._factories.tokens import audit_rows
from tests._factories.users import make_user

_SESSIONS = f"{core_config.ROOT_PATH}/profile/sessions"


def _owner(committed_sessions, sign_in, sessions: int = 2):
    with committed_sessions() as db:
        user = make_user(db)
        db.commit()
    return [sign_in(user) for _ in range(sessions)]


def _generation(committed_sessions, user_id: uuid.UUID) -> int:
    with committed_sessions() as db:
        return security_generation_integration.current_generation(user_id, db)


class TestList:
    def test_the_session_the_request_comes_from_is_marked_current(self, committed_sessions, sign_in):
        here, there = _owner(committed_sessions, sign_in)

        body = here.client.get(_SESSIONS).json()

        assert body["total"] == 2
        assert {item["id"]: item["is_current"] for item in body["items"]} == {
            str(here.session_id): True,
            str(there.session_id): False,
        }
        assert all(item["user_id"] == str(here.user.id) for item in body["items"])

    def test_another_users_sessions_are_not_listed(self, committed_sessions, sign_in):
        (here,) = _owner(committed_sessions, sign_in, 1)
        _owner(committed_sessions, sign_in)

        assert [item["id"] for item in here.client.get(_SESSIONS).json()["items"]] == [str(here.session_id)]

    def test_the_list_is_paged(self, committed_sessions, sign_in):
        sessions = _owner(committed_sessions, sign_in, 3)

        page = sessions[0].client.get(_SESSIONS, params={"page_number": 2, "num_records": 2}).json()

        assert (page["total"], len(page["items"])) == (3, 1)


class TestDeleteOne:
    def test_the_session_ends_is_audited_and_its_tokens_stop_working(self, committed_sessions, sign_in):
        here, there = _owner(committed_sessions, sign_in)

        response = here.client.delete(f"{_SESSIONS}/{there.session_id}")

        assert response.status_code == 204
        assert session_ids(committed_sessions, here.user.id) == {here.session_id}
        (row,) = audit_rows(committed_sessions, sessions_audit_actions.SESSION_REVOKE)
        assert (row.outcome, row.target_type, row.target_id, row.target_owner_id, row.details["sessions_revoked"]) == (
            "success",
            "session",
            str(there.session_id),
            str(here.user.id),
            1,
        )
        assert there.client.get(_SESSIONS).status_code == 401

    def test_the_raw_session_id_is_not_logged(self, committed_sessions, sign_in, caplog):
        here, there = _owner(committed_sessions, sign_in)

        with caplog.at_level("DEBUG"):
            here.client.delete(f"{_SESSIONS}/{there.session_id}")

        ours = [record for record in caplog.records if record.name.startswith("main_logger")]
        assert ours and str(there.session_id) not in " ".join(str(record.__dict__) for record in ours)

    def test_the_callers_own_session_can_be_ended(self, committed_sessions, sign_in):
        here, there = _owner(committed_sessions, sign_in)

        assert here.client.delete(f"{_SESSIONS}/{here.session_id}").status_code == 204

        assert session_ids(committed_sessions, here.user.id) == {there.session_id}

    def test_another_users_session_is_not_found_and_stays(self, committed_sessions, sign_in):
        (here,) = _owner(committed_sessions, sign_in, 1)
        (stranger,) = _owner(committed_sessions, sign_in, 1)

        response = here.client.delete(f"{_SESSIONS}/{stranger.session_id}")

        assert response.status_code == 404
        assert session_ids(committed_sessions, stranger.user.id) == {stranger.session_id}
        assert audit_rows(committed_sessions, sessions_audit_actions.SESSION_REVOKE) == []

    def test_an_unknown_session_is_not_found(self, committed_sessions, sign_in):
        (here,) = _owner(committed_sessions, sign_in, 1)

        assert here.client.delete(f"{_SESSIONS}/{uuid.uuid4()}").status_code == 404

    def test_a_malformed_session_id_is_refused(self, committed_sessions, sign_in):
        (here,) = _owner(committed_sessions, sign_in, 1)

        assert here.client.delete(f"{_SESSIONS}/not-a-uuid").status_code == 422


class TestSignOutEverywhere:
    def test_every_session_ends_the_cookie_is_cleared_and_the_generation_moves_on(self, committed_sessions, sign_in):
        here, there = _owner(committed_sessions, sign_in)
        before = _generation(committed_sessions, here.user.id)

        response = here.client.post(f"{_SESSIONS}/revoke")

        assert response.status_code == 204
        assert session_ids(committed_sessions, here.user.id) == set()
        assert "max-age=0" in response.headers["set-cookie"].lower()
        assert _generation(committed_sessions, here.user.id) > before
        (row,) = audit_rows(committed_sessions, sessions_audit_actions.SESSION_REVOKE)
        assert (row.target_type, row.details["sessions_revoked"]) == ("user", 2)
        assert there.client.get(_SESSIONS).status_code == 401

    def test_keep_current_ends_only_the_others_and_leaves_the_cookie(self, committed_sessions, sign_in):
        here = _owner(committed_sessions, sign_in, 3)[0]
        before = _generation(committed_sessions, here.user.id)

        response = here.client.post(f"{_SESSIONS}/revoke", params={"keep_current": "true"})

        assert response.status_code == 204
        assert session_ids(committed_sessions, here.user.id) == {here.session_id}
        assert "set-cookie" not in response.headers
        assert _generation(committed_sessions, here.user.id) == before
        (row,) = audit_rows(committed_sessions, sessions_audit_actions.SESSION_REVOKE)
        assert row.details["sessions_revoked"] == 2
        assert here.client.get(_SESSIONS).status_code == 200

    def test_keep_current_with_no_other_session_audits_nothing(self, committed_sessions, sign_in):
        (here,) = _owner(committed_sessions, sign_in, 1)

        assert here.client.post(f"{_SESSIONS}/revoke", params={"keep_current": "true"}).status_code == 204

        assert audit_rows(committed_sessions, sessions_audit_actions.SESSION_REVOKE) == []

    def test_another_users_sessions_are_untouched(self, committed_sessions, sign_in):
        (here,) = _owner(committed_sessions, sign_in, 1)
        (stranger,) = _owner(committed_sessions, sign_in, 1)

        here.client.post(f"{_SESSIONS}/revoke")

        assert session_ids(committed_sessions, stranger.user.id) == {stranger.session_id}
