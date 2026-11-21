"""The user routes, through the production application: real authentication, scopes, handlers and database."""

import uuid

import pytest
import sqlalchemy as sa
from jasil.audit.models import AuditLog

import core.config as core_config
import core.local_pool as core_local_pool
import modules.auth.credentials.integration_service as credentials_integration
import modules.auth.mfa.integration_service as mfa_integration
import modules.auth.sessions.models as sessions_models
import modules.users.users.audit_actions as users_audit_actions
import modules.users.users.deletion_job_service as users_deletion_job_service
import modules.users.users.models as users_models
import modules.users.users_privacy_settings.schema as users_privacy_settings_schema
import modules.users.users_profile.service as users_profile_service
from tests._factories.breach import fake_range_api
from tests._factories.identity_links import make_identity_link, make_identity_provider
from tests._factories.server_settings import edit_mail_settings, edit_server_settings
from tests._factories.tokens import make_mfa
from tests._factories.users import PASSWORD, make_admin, make_sign_up, make_user
from tests._helpers import images

_URL = f"{core_config.ROOT_PATH}/users"
_JOBS = f"{core_config.ROOT_PATH}/jobs"
_STEP_UP = {"current_password": PASSWORD}
_NEW_PASSWORD = "Another-Strong-Password-1!"


def _problem(response) -> str:
    """The short problem type of an error response."""
    return response.json()["type"].rsplit(":", 1)[-1]


def _stored(committed_sessions, user_id) -> users_models.Users | None:
    """Read a user back in a new session, detached, or ``None`` when it is gone."""
    with committed_sessions() as db:
        row = db.get(users_models.Users, user_id)
        if row is not None:
            db.expunge(row)
        return row


def _session_count(committed_sessions, user_id) -> int:
    with committed_sessions() as db:
        return db.scalar(
            sa.select(sa.func.count(sessions_models.UsersSessions.id)).where(
                sessions_models.UsersSessions.user_id == user_id
            )
        )


def _audit_rows(committed_sessions, action) -> list[AuditLog]:
    with committed_sessions() as db:
        rows = list(db.scalars(sa.select(AuditLog).where(AuditLog.action_id == action.id)))
        db.expunge_all()
    return rows


@pytest.fixture
def admin(committed_sessions):
    with committed_sessions() as db:
        created = make_admin(db)
        db.commit()
    return created


@pytest.fixture
def me(sign_in, admin):
    return sign_in(admin)


@pytest.fixture
def subject(committed_sessions):
    """A regular user the administrator manages."""
    with committed_sessions() as db:
        created = make_user(db)
        db.commit()
    return created


@pytest.fixture
def make(committed_sessions):
    """Return a function that commits a user made by one of the factories."""

    def commit(factory, **fields):
        with committed_sessions() as db:
            created = factory(db, **fields)
            db.commit()
        return created

    return commit


def _version(me, user) -> str:
    """The quoted version of a user as the administrator reads it now."""
    return me.client.get(f"{_URL}/{user.id}").headers["ETag"]


class TestListUsers:
    def test_an_administrator_lists_full_records_by_username_in_a_page_envelope(self, me, make):
        make(make_user, username="bruno", city="Porto")
        make(make_user, username="anna")

        body = me.client.get(_URL).json()

        assert [item["username"] for item in body["items"]] == sorted(["anna", "bruno", me.user.username])
        assert (body["total"], body["page"], body["next"]) == (3, 1, None)
        bruno = next(item for item in body["items"] if item["username"] == "bruno")
        assert (bruno["city"], bruno["access_type"], bruno["version"]) == ("Porto", "regular", 1)
        assert {"email", "mfa_enabled", "external_auth_count", "pending_email", "photo_path"} <= set(bruno)

    def test_the_list_carries_each_users_mfa_and_identity_provider_state(self, me, committed_sessions):
        with committed_sessions() as db:
            secured = make_user(db, username="secured")
            make_mfa(db, secured)
            linked = make_user(db, username="linked")
            make_identity_link(db, linked.id, make_identity_provider(db, "router-idp"), "subject")
            db.commit()

        items = {item["username"]: item for item in me.client.get(_URL).json()["items"]}

        assert (items["secured"]["mfa_enabled"], items["linked"]["mfa_enabled"]) == (True, False)
        assert (items["linked"]["external_auth_count"], items["secured"]["external_auth_count"]) == (1, 0)

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("active=false", ["inactive", "waiting"]),
            ("email_verified=false", ["unverified"]),
            ("pending_approval=true", ["waiting"]),
            ("external_auth=true", ["linked"]),
            ("username=ANNA-USER", ["anna-user"]),
            ("username_contains=ANN", ["anna-user"]),
        ],
    )
    def test_each_filter_keeps_only_the_users_in_that_state(self, me, committed_sessions, query, expected):
        with committed_sessions() as db:
            make_user(db, username="anna-user")
            make_user(db, username="inactive", active=False)
            make_user(db, username="unverified", email_verified=False)
            make_sign_up(db, username="waiting", pending_admin_approval=True, email_verified=True)
            linked = make_user(db, username="linked")
            make_identity_link(db, linked.id, make_identity_provider(db, "filter-idp"), "subject")
            db.commit()

        body = me.client.get(f"{_URL}?{query}").json()

        assert [item["username"] for item in body["items"]] == expected
        assert body["total"] == len(expected)

    def test_a_page_size_above_the_servers_is_refused(self, me, committed_sessions):
        with committed_sessions() as db:
            edit_server_settings(db, num_records_per_page=10)
            db.commit()

        response = me.client.get(f"{_URL}?num_records=11")

        assert response.status_code == 422
        assert "num_records" in response.text

    def test_a_page_size_the_server_allows_pages_the_list(self, me, make):
        for _ in range(3):
            make(make_user)

        body = me.client.get(f"{_URL}?num_records=2&page_number=2").json()

        assert (len(body["items"]), body["total"], body["page"]) == (2, 4, 2)


class TestSearchWithARegularToken:
    @pytest.fixture
    def reader(self, sign_in, subject):
        return sign_in(subject)

    @pytest.fixture
    def people(self, committed_sessions):
        with committed_sessions() as db:
            make_user(db, username="searchable.person")
            make_user(db, username="searchable.inactive", active=False)
            make_sign_up(db, username="searchable.waiting", pending_admin_approval=True)
            hidden = make_user(db, username="searchable.hidden")
            users_profile_service.edit_privacy_settings(
                hidden.id,
                users_privacy_settings_schema.UserPrivacySettingsUpdate(discoverable=False),
                db,
                if_match='"1"',
            )
            db.commit()

    def test_the_search_finds_active_discoverable_users_as_public_projections(self, reader, people):
        body = reader.client.get(f"{_URL}?username_contains=searchable").json()

        assert [item["username"] for item in body["items"]] == ["searchable.person"]
        assert "email" not in body["items"][0]
        assert body["total"] == 1

    def test_an_exact_username_is_found_even_when_it_is_short(self, reader, make):
        make(make_user, username="al")

        body = reader.client.get(f"{_URL}?username=AL").json()

        assert [item["username"] for item in body["items"]] == ["al"]

    def test_a_request_without_a_search_term_is_refused(self, reader):
        response = reader.client.get(_URL)

        assert response.status_code == 422
        assert "username" in response.text

    def test_a_contains_term_shorter_than_three_characters_is_refused(self, reader):
        assert reader.client.get(f"{_URL}?username_contains=ab").status_code == 422

    @pytest.mark.parametrize(
        "query", ["active=true", "email_verified=true", "pending_approval=false", "external_auth=false"]
    )
    def test_a_state_filter_needs_the_read_all_scope(self, reader, query):
        response = reader.client.get(f"{_URL}?username=x&{query}")

        assert response.status_code == 403

    def test_a_page_size_above_the_servers_is_refused(self, reader, committed_sessions):
        with committed_sessions() as db:
            edit_server_settings(db, num_records_per_page=10)
            db.commit()

        assert reader.client.get(f"{_URL}?username_contains=abc&num_records=11").status_code == 422


class TestReadUser:
    def test_an_administrator_reads_the_full_record_with_its_version_as_the_etag(self, me, subject):
        response = me.client.get(f"{_URL}/{subject.id}")

        assert response.status_code == 200
        assert response.headers["ETag"] == '"1"'
        body = response.json()
        assert (body["id"], body["email"], body["version"], body["mfa_enabled"]) == (
            str(subject.id),
            subject.email,
            1,
            False,
        )

    def test_the_record_carries_the_email_change_waiting_for_confirmation(self, me, committed_sessions, subject):
        with committed_sessions() as db:
            edit_mail_settings(
                db, host="smtp.example.com", port=587, security="starttls", username=None, from_address=None
            )
            db.commit()
        me.client.patch(
            f"{_URL}/{subject.id}",
            json={"email": "changed@example.com", "step_up": _STEP_UP},
            headers={"If-Match": '"1"'},
        )

        body = me.client.get(f"{_URL}/{subject.id}").json()

        assert (body["pending_email"], body["email"]) == ("changed@example.com", subject.email)
        assert body["pending_email_expires_at"] is not None

    def test_a_regular_token_reads_the_public_projection_without_an_etag(self, sign_in, subject, make):
        other = make(make_user, city="Porto")

        response = sign_in(subject).client.get(f"{_URL}/{other.id}")

        assert response.status_code == 200
        assert "ETag" not in response.headers
        body = response.json()
        assert body["id"] == str(other.id)
        assert not {"email", "access_type", "active"} & set(body)

    @pytest.mark.parametrize("state", ["inactive", "pending", "missing"])
    def test_a_regular_token_cannot_look_up_an_inactive_pending_or_missing_user(self, sign_in, subject, make, state):
        target = {
            "inactive": lambda: make(make_user, active=False).id,
            "pending": lambda: make(make_sign_up, pending_admin_approval=True).id,
            "missing": uuid.uuid4,
        }[state]()

        response = sign_in(subject).client.get(f"{_URL}/{target}")

        assert (response.status_code, _problem(response)) == (404, "not-found")

    def test_an_administrator_reads_an_inactive_user_in_full(self, me, make):
        inactive = make(make_user, active=False)

        body = me.client.get(f"{_URL}/{inactive.id}").json()

        assert (body["active"], body["id"]) == (False, str(inactive.id))

    def test_a_missing_user_is_not_found_for_an_administrator(self, me):
        assert me.client.get(f"{_URL}/{uuid.uuid4()}").status_code == 404


class TestCreateUser:
    @staticmethod
    def _body(**fields) -> dict:
        return {
            "name": "New User",
            "username": "New.User",
            "email": "New.User@Example.com",
            "password": PASSWORD,
            "access_type": "regular",
            "active": True,
        } | fields

    def test_a_regular_user_is_created_with_a_location_an_etag_and_normalized_names(self, me, committed_sessions):
        response = me.client.post(_URL, json=self._body())

        assert response.status_code == 201
        body = response.json()
        assert response.headers["Location"].endswith(f"{_URL}/{body['id']}")
        assert response.headers["ETag"] == '"1"'
        assert (body["username"], body["email"], body["access_type"]) == ("new.user", "new.user@example.com", "regular")
        row = _stored(committed_sessions, uuid.UUID(body["id"]))
        assert (row.username, row.email, row.active) == ("new.user", "new.user@example.com", True)
        with committed_sessions() as db:
            assert credentials_integration.is_password_change_required(row.id, db) is True

    def test_the_creation_is_audited_as_an_administrators_with_no_value(self, me, committed_sessions):
        created = me.client.post(_URL, json=self._body()).json()

        [row] = _audit_rows(committed_sessions, users_audit_actions.USER_CREATE)
        assert (row.target_id, row.actor_id) == (created["id"], str(me.user.id))
        assert row.details["method"] == "admin"
        assert "new.user" not in str(row.details)

    @pytest.mark.parametrize(
        "field",
        ["pending_admin_approval", "mfa_enabled", "id", "version", "created_at", "photo_path", "external_auth_count"],
    )
    def test_a_field_the_server_owns_is_not_accepted_in_the_body(self, me, committed_sessions, field):
        response = me.client.post(_URL, json=self._body(**{field: True}))

        assert response.status_code == 422
        with committed_sessions() as db:
            assert db.scalar(sa.select(sa.func.count(users_models.Users.id))) == 1

    def test_an_administrator_account_is_refused_without_the_creating_administrators_step_up(
        self, me, committed_sessions
    ):
        for step_up in (None, {"current_password": "wrong-password"}):
            response = me.client.post(_URL, json=self._body(access_type="admin", step_up=step_up))

            assert (response.status_code, _problem(response)) == (403, "step-up-failed")
        with committed_sessions() as db:
            assert db.scalar(sa.select(sa.func.count(users_models.Users.id))) == 1

    def test_an_administrator_account_is_created_with_the_step_up_and_the_step_up_is_not_a_user_field(
        self, me, committed_sessions
    ):
        response = me.client.post(_URL, json=self._body(access_type="admin", step_up=_STEP_UP))

        assert response.status_code == 201
        assert "step_up" not in response.json()
        assert _stored(committed_sessions, uuid.UUID(response.json()["id"])).access_type == "admin"

    def test_a_regular_account_ignores_a_step_up_it_does_not_need(self, me):
        assert me.client.post(_URL, json=self._body(step_up=_STEP_UP)).status_code == 201

    def test_a_taken_username_or_email_is_a_conflict(self, me, subject):
        by_email = me.client.post(_URL, json=self._body(email=subject.email))
        by_username = me.client.post(_URL, json=self._body(username=subject.username))

        assert (by_email.status_code, _problem(by_email)) == (409, "conflict")
        assert by_username.status_code == 409

    def test_a_password_below_the_policy_is_refused(self, me):
        response = me.client.post(_URL, json=self._body(password="short"))

        assert (response.status_code, _problem(response)) == (422, "password-too-short")

    def test_a_password_in_a_known_breach_is_refused_and_no_account_is_created(
        self, me, committed_sessions, monkeypatch
    ):
        """With the breach check on, an administrator cannot give a new account a breached password."""
        with committed_sessions() as db:
            edit_server_settings(db, password_breach_check_enabled=True)
            db.commit()
        breached = "correct horse battery staple 2026"
        range_api = fake_range_api(monkeypatch)
        range_api.breach(breached)

        response = me.client.post(_URL, json=self._body(password=breached))

        assert (response.status_code, _problem(response)) == (422, "password-breached")
        assert len(range_api.requests) == 1
        with committed_sessions() as db:
            assert db.scalar(sa.select(users_models.Users).where(users_models.Users.username == "new.user")) is None

    def test_a_missing_password_is_refused_without_mail(self, me):
        response = me.client.post(_URL, json=self._body(password=None))

        assert (response.status_code, _problem(response)) == (400, "password-required")

    def test_a_missing_password_invites_the_user_when_mail_is_configured(self, me, committed_sessions):
        with committed_sessions() as db:
            edit_mail_settings(
                db, host="smtp.example.com", port=587, security="starttls", username=None, from_address=None
            )
            db.commit()

        response = me.client.post(_URL, json=self._body(password=None))

        assert response.status_code == 201
        with committed_sessions() as db:
            assert credentials_integration.get_password_hash(uuid.UUID(response.json()["id"]), db) is None


class TestEditUser:
    def _patch(self, me, user, **changes):
        step_up = changes.pop("step_up", None)
        body = changes | ({"step_up": step_up} if step_up is not None else {})
        return me.client.patch(f"{_URL}/{user.id}", json=body, headers={"If-Match": _version(me, user)})

    def test_the_edit_answers_the_user_with_the_new_version_as_the_etag(self, me, subject):
        response = self._patch(me, subject, city="Faro", height=181)

        assert response.status_code == 200
        assert response.headers["ETag"] == '"2"'
        body = response.json()
        assert (body["city"], body["height"], body["version"], body["name"]) == ("Faro", 181, 2, subject.name)

    def test_a_stale_version_is_refused_and_the_user_is_unchanged(self, me, committed_sessions, subject):
        response = me.client.patch(f"{_URL}/{subject.id}", json={"city": "Faro"}, headers={"If-Match": '"99"'})

        assert response.status_code == 412
        assert _stored(committed_sessions, subject.id).city is None

    @pytest.mark.parametrize(
        "field", ["id", "version", "created_at", "pending_admin_approval", "mfa_enabled", "photo_path"]
    )
    def test_a_field_the_server_owns_is_not_accepted_in_the_body(self, me, subject, field):
        response = self._patch(me, subject, **{field: "x"})

        assert response.status_code == 422

    @pytest.mark.parametrize(
        "changes",
        [{"email": "other@example.com"}, {"access_type": "admin"}, {"active": False}, {"username": "renamed"}],
        ids=["email", "access_type", "active", "username"],
    )
    def test_a_security_field_without_the_administrators_step_up_is_the_uniform_403_and_changes_nothing(
        self, me, committed_sessions, subject, changes
    ):
        response = self._patch(me, subject, **changes)

        assert (response.status_code, _problem(response)) == (403, "step-up-failed")
        row = _stored(committed_sessions, subject.id)
        assert (row.email, row.access_type, row.active, row.username) == (
            subject.email,
            "regular",
            True,
            subject.username,
        )

    def test_an_edit_with_the_step_up_ends_the_users_sessions_and_a_plain_edit_does_not(
        self, me, sign_in, committed_sessions, subject
    ):
        victim = sign_in(subject)
        self._patch(me, subject, city="Faro")
        assert _session_count(committed_sessions, subject.id) == 1
        assert victim.client.get(f"{_URL}/{subject.id}").status_code == 200

        response = self._patch(me, subject, access_type="admin", step_up=_STEP_UP)

        assert response.status_code == 200
        assert _session_count(committed_sessions, subject.id) == 0
        assert victim.client.get(f"{_URL}/{subject.id}").status_code == 401

    def test_a_new_username_keeps_the_users_sessions(self, me, sign_in, committed_sessions, subject):
        sign_in(subject)

        response = self._patch(me, subject, username="renamed", step_up=_STEP_UP)

        assert response.status_code == 200
        assert _session_count(committed_sessions, subject.id) == 1

    def test_an_administrator_editing_themselves_stays_signed_in(self, me, make, committed_sessions):
        make(make_admin)

        response = self._patch(me, me.user, access_type="regular", step_up=_STEP_UP)

        assert response.status_code == 200
        assert _session_count(committed_sessions, me.user.id) == 1

    def test_an_administrator_cannot_change_their_own_email_here(self, me):
        response = self._patch(me, me.user, email="mine@example.com", step_up=_STEP_UP)

        assert response.status_code == 403
        assert _problem(response) == "permission-denied"

    def test_demoting_or_deactivating_the_only_administrator_is_a_last_administrator_conflict(
        self, me, committed_sessions
    ):
        for changes in ({"access_type": "regular"}, {"active": False}):
            response = self._patch(me, me.user, **changes, step_up=_STEP_UP)

            assert (response.status_code, _problem(response)) == (409, "last-administrator")
        row = _stored(committed_sessions, me.user.id)
        assert (row.access_type, row.active) == ("admin", True)

    def test_an_edit_cannot_activate_a_user_awaiting_approval(self, me, make, committed_sessions):
        waiting = make(make_sign_up, pending_admin_approval=True)

        response = self._patch(me, waiting, active=True, step_up=_STEP_UP)

        assert (response.status_code, _problem(response)) == (409, "approval-pending")
        assert _stored(committed_sessions, waiting.id).pending_admin_approval is True

    def test_an_address_is_requested_not_applied_when_mail_is_configured(self, me, committed_sessions, subject):
        with committed_sessions() as db:
            edit_mail_settings(
                db, host="smtp.example.com", port=587, security="starttls", username=None, from_address=None
            )
            db.commit()

        body = self._patch(me, subject, email="Changed@Example.com", step_up=_STEP_UP).json()

        assert (body["email"], body["pending_email"]) == (subject.email, "changed@example.com")

    def test_an_address_is_applied_unverified_without_mail_and_verified_when_the_administrator_says_so(
        self, me, subject, make
    ):
        applied = self._patch(me, subject, email="Changed@Example.com", step_up=_STEP_UP).json()
        other = make(make_user)
        verified = self._patch(me, other, email="verified@example.com", email_verified=True, step_up=_STEP_UP).json()

        assert (applied["email"], applied["email_verified"], applied["pending_email"]) == (
            "changed@example.com",
            False,
            None,
        )
        assert (verified["email"], verified["email_verified"]) == ("verified@example.com", True)

    def test_a_taken_address_is_a_conflict_and_nothing_changes(self, me, make, subject, committed_sessions):
        other = make(make_user)

        response = self._patch(me, subject, email=other.email, email_verified=True, step_up=_STEP_UP)

        assert response.status_code == 409
        assert _stored(committed_sessions, subject.id).email == subject.email

    def test_the_audit_names_the_changed_fields_and_never_their_values(self, me, committed_sessions, subject):
        self._patch(me, subject, city="Faro", height=181)

        [row] = _audit_rows(committed_sessions, users_audit_actions.USER_UPDATE)
        assert row.details["changed_fields"] == ["city", "height"]
        assert (row.target_id, row.actor_id) == (str(subject.id), str(me.user.id))
        assert "Faro" not in str(row.details)

    def test_an_unknown_user_is_not_found(self, me):
        response = me.client.patch(f"{_URL}/{uuid.uuid4()}", json={"city": "Faro"}, headers={"If-Match": '"1"'})

        assert response.status_code == 404


class TestApproveUser:
    def test_a_waiting_user_is_approved_and_activated(self, me, make, committed_sessions):
        waiting = make(make_sign_up, pending_admin_approval=True, email_verified=True)

        response = me.client.post(f"{_URL}/{waiting.id}/approve")

        assert response.status_code == 204
        row = _stored(committed_sessions, waiting.id)
        assert (row.active, row.pending_admin_approval) == (True, False)
        [audit] = _audit_rows(committed_sessions, users_audit_actions.USER_APPROVE)
        assert (audit.target_id, audit.actor_id) == (str(waiting.id), str(me.user.id))

    def test_an_unverified_address_is_a_conflict_while_sign_up_requires_verification(
        self, me, make, committed_sessions
    ):
        with committed_sessions() as db:
            edit_server_settings(db, signup_require_email_verification=True)
            db.commit()
        waiting = make(make_sign_up, pending_admin_approval=True)

        response = me.client.post(f"{_URL}/{waiting.id}/approve")

        assert response.status_code == 409
        assert _stored(committed_sessions, waiting.id).pending_admin_approval is True

    def test_a_user_not_awaiting_approval_is_a_conflict_and_unchanged(self, me, subject, committed_sessions):
        response = me.client.post(f"{_URL}/{subject.id}/approve")

        assert response.status_code == 409
        assert _stored(committed_sessions, subject.id).version == 1

    def test_an_unknown_user_is_not_found(self, me):
        assert me.client.post(f"{_URL}/{uuid.uuid4()}/approve").status_code == 404


class TestAdministratorCredentialRoutes:
    def test_a_password_set_by_an_administrator_ends_the_users_sessions_and_replaces_the_password(
        self, me, sign_in, committed_sessions, subject
    ):
        sign_in(subject)

        response = me.client.post(
            f"{_URL}/{subject.id}/password/change", json={"password": _NEW_PASSWORD, "step_up": _STEP_UP}
        )

        assert response.status_code == 204
        assert _session_count(committed_sessions, subject.id) == 0
        with committed_sessions() as db:
            stored = credentials_integration.get_password_hash(subject.id, db)
            hasher = credentials_integration.get_password_hasher()
            assert credentials_integration.verify_and_update_password(_NEW_PASSWORD, stored, hasher)[0] is True
            assert credentials_integration.is_password_change_required(subject.id, db) is True

    def test_a_refused_step_up_changes_nothing_and_a_body_without_it_is_invalid(
        self, me, sign_in, committed_sessions, subject
    ):
        sign_in(subject)

        refused = me.client.post(
            f"{_URL}/{subject.id}/password/change",
            json={"password": _NEW_PASSWORD, "step_up": {"current_password": "wrong-password"}},
        )
        missing = me.client.post(f"{_URL}/{subject.id}/password/change", json={"password": _NEW_PASSWORD})

        assert (refused.status_code, _problem(refused)) == (403, "step-up-failed")
        assert missing.status_code == 422
        assert _session_count(committed_sessions, subject.id) == 1

    def test_a_password_below_the_policy_is_refused(self, me, subject):
        response = me.client.post(
            f"{_URL}/{subject.id}/password/change", json={"password": "short", "step_up": _STEP_UP}
        )

        assert response.status_code in {400, 422}

    @pytest.mark.parametrize("path", ["password/change", "mfa/reset", "password/require-change"])
    def test_an_administrator_cannot_use_these_routes_on_their_own_account(self, me, path):
        body = {"step_up": _STEP_UP} | ({"password": _NEW_PASSWORD} if path == "password/change" else {})

        response = me.client.post(f"{_URL}/{me.user.id}/{path}", json=body)

        assert (response.status_code, _problem(response)) == (403, "permission-denied")

    def test_an_mfa_reset_removes_the_factors_and_ends_the_users_sessions(
        self, me, sign_in, committed_sessions, subject
    ):
        with committed_sessions() as db:
            make_mfa(db, subject)
            db.commit()
        sign_in(subject)

        response = me.client.post(f"{_URL}/{subject.id}/mfa/reset", json={"step_up": _STEP_UP})

        assert response.status_code == 204
        assert _session_count(committed_sessions, subject.id) == 0
        with committed_sessions() as db:
            assert mfa_integration.is_mfa_enabled_for_user(subject.id, db) is False

    def test_resetting_the_mfa_of_a_user_without_it_is_a_conflict(self, me, subject):
        response = me.client.post(f"{_URL}/{subject.id}/mfa/reset", json={"step_up": _STEP_UP})

        assert response.status_code == 409

    def test_requiring_a_password_change_keeps_the_password_and_ends_the_sessions(
        self, me, sign_in, committed_sessions, subject
    ):
        sign_in(subject)

        response = me.client.post(f"{_URL}/{subject.id}/password/require-change", json={"step_up": _STEP_UP})

        assert response.status_code == 204
        assert _session_count(committed_sessions, subject.id) == 0
        with committed_sessions() as db:
            assert credentials_integration.is_password_change_required(subject.id, db) is True

    def test_requiring_a_password_change_of_a_user_without_a_password_is_a_conflict(self, me, make):
        passwordless = make(make_user, with_password=False)

        response = me.client.post(f"{_URL}/{passwordless.id}/password/require-change", json={"step_up": _STEP_UP})

        assert response.status_code == 409

    def test_a_body_with_an_unknown_field_is_refused(self, me, subject):
        response = me.client.post(
            f"{_URL}/{subject.id}/mfa/reset", json={"step_up": _STEP_UP, "current_password": PASSWORD}
        )

        assert response.status_code == 422


class TestIdentityProviders:
    def test_an_administrator_lists_a_users_links_a_page_at_a_time(self, me, committed_sessions, subject):
        with committed_sessions() as db:
            for slug in ("one", "two", "three"):
                make_identity_link(db, subject.id, make_identity_provider(db, f"idp-{slug}"), f"subject-{slug}")
            db.commit()

        body = me.client.get(f"{_URL}/{subject.id}/identity-providers?page_number=2&num_records=2").json()

        assert (len(body["items"]), body["total"], body["page"]) == (1, 3, 2)

    def test_a_link_is_removed_after_the_step_up(self, me, committed_sessions, subject):
        with committed_sessions() as db:
            idp = make_identity_provider(db, "unlink-idp")
            make_identity_link(db, subject.id, idp, "subject")
            db.commit()

        response = me.client.post(f"{_URL}/{subject.id}/identity-providers/{idp}/unlink", json={"step_up": _STEP_UP})

        assert response.status_code == 204
        assert me.client.get(f"{_URL}/{subject.id}/identity-providers").json()["total"] == 0

    def test_the_last_way_to_sign_in_cannot_be_unlinked(self, me, make, committed_sessions):
        passwordless = make(make_user, with_password=False)
        with committed_sessions() as db:
            idp = make_identity_provider(db, "last-idp")
            make_identity_link(db, passwordless.id, idp, "subject")
            db.commit()

        response = me.client.post(
            f"{_URL}/{passwordless.id}/identity-providers/{idp}/unlink", json={"step_up": _STEP_UP}
        )

        assert (response.status_code, _problem(response)) == (409, "last-sign-in-method")

    def test_a_refused_step_up_and_a_malformed_provider_id_unlink_nothing(self, me, committed_sessions, subject):
        with committed_sessions() as db:
            idp = make_identity_provider(db, "refused-idp")
            make_identity_link(db, subject.id, idp, "subject")
            db.commit()

        refused = me.client.post(
            f"{_URL}/{subject.id}/identity-providers/{idp}/unlink",
            json={"step_up": {"current_password": "wrong-password"}},
        )
        malformed = me.client.post(
            f"{_URL}/{subject.id}/identity-providers/not-a-uuid/unlink", json={"step_up": _STEP_UP}
        )

        assert (refused.status_code, malformed.status_code) == (403, 422)
        assert me.client.get(f"{_URL}/{subject.id}/identity-providers").json()["total"] == 1

    def test_a_provider_the_user_is_not_linked_to_is_not_found(self, me, subject, committed_sessions):
        with committed_sessions() as db:
            idp = make_identity_provider(db, "stranger-idp")
            db.commit()

        response = me.client.post(f"{_URL}/{subject.id}/identity-providers/{idp}/unlink", json={"step_up": _STEP_UP})

        assert response.status_code == 404


class TestDeleteUser:
    @pytest.fixture
    def deletion_pool(self, monkeypatch):
        pool = core_local_pool.BoundedPool("user-deletion-router-test", workers=1, max_pending=5)
        monkeypatch.setattr(users_deletion_job_service, "_deletion_pool", pool)
        yield pool
        pool.shutdown(wait=True)

    @pytest.fixture
    def durable(self, monkeypatch):
        """Run as the durable profile does, so a request publishes its work and nothing runs in the test."""
        monkeypatch.setattr(core_config.settings, "JOBS_ENABLED", True)

    @staticmethod
    def _delete(me, user, *, step_up=_STEP_UP, version='"1"'):
        return me.client.post(f"{_URL}/{user.id}/delete", json={"step_up": step_up}, headers={"If-Match": version})

    def test_the_deletion_is_accepted_as_a_job_and_the_account_is_deactivated_and_signed_out_at_once(
        self, me, sign_in, committed_sessions, durable, subject
    ):
        sign_in(subject)

        response = self._delete(me, subject)

        assert response.status_code == 202
        body = response.json()
        assert (body["kind"], body["status"]) == ("user_deletion", "queued")
        assert response.headers["Content-Location"] == f"{_JOBS}/{body['id']}"
        assert response.headers["Retry-After"] == "10"
        assert _session_count(committed_sessions, subject.id) == 0
        [audit] = _audit_rows(committed_sessions, users_audit_actions.USER_DELETE)
        assert (audit.target_id, audit.actor_id) == (str(subject.id), str(me.user.id))

    def test_the_job_is_polled_to_its_outcome_and_the_account_is_gone(
        self, me, committed_sessions, deletion_pool, subject
    ):
        body = self._delete(me, subject).json()
        deletion_pool.shutdown(wait=True)

        job = me.client.get(f"{_JOBS}/{body['id']}")

        assert (job.status_code, job.json()["status"]) == (200, "succeeded")
        assert _stored(committed_sessions, subject.id) is None

    def test_a_stale_version_queues_nothing(self, me, committed_sessions, durable, subject):
        response = self._delete(me, subject, version='"99"')

        assert response.status_code == 412
        assert _stored(committed_sessions, subject.id).deletion_requested_at is None

    def test_a_refused_step_up_queues_nothing(self, me, committed_sessions, durable, subject):
        response = self._delete(me, subject, step_up={"current_password": "wrong-password"})

        assert (response.status_code, _problem(response)) == (403, "step-up-failed")
        assert _stored(committed_sessions, subject.id).deletion_requested_at is None

    def test_an_administrator_cannot_delete_their_own_account_here(self, me, durable):
        response = self._delete(me, me.user)

        assert (response.status_code, _problem(response)) == (403, "permission-denied")

    def test_an_unknown_user_is_not_found(self, me, durable):
        response = me.client.post(
            f"{_URL}/{uuid.uuid4()}/delete", json={"step_up": _STEP_UP}, headers={"If-Match": '"1"'}
        )

        assert response.status_code == 404

    def test_a_deletion_already_pending_is_a_conflict_naming_the_running_job(self, me, durable, subject):
        first = self._delete(me, subject).json()

        again = self._delete(me, subject, version=_version(me, subject))

        assert (again.status_code, _problem(again)) == (409, "conflict")
        assert again.json()["job_id"] == first["id"]

    def test_a_body_with_an_unknown_field_is_refused(self, me, subject, durable):
        response = me.client.post(
            f"{_URL}/{subject.id}/delete",
            json={"step_up": _STEP_UP, "force": True},
            headers={"If-Match": '"1"'},
        )

        assert response.status_code == 422


class TestUserPhotos:
    _PNG = images.png_with_text()

    def _put(self, me, user, name="me.png", data=None, content_type="image/png"):
        return me.client.put(f"{_URL}/{user.id}/photo", files={"file": (name, data or self._PNG, content_type)})

    def test_a_photo_is_created_then_replaced_and_the_answer_is_a_signed_address(self, me, subject):
        created = self._put(me, subject)
        replaced = self._put(me, subject)

        assert (created.status_code, replaced.status_code) == (201, 200)
        path = created.json()["photo_path"]
        assert f"/users/{subject.id}/photo?t=" in path

    def test_the_signed_address_serves_the_photo_to_anyone_and_a_forged_token_is_not_found(self, me, client, subject):
        path = self._put(me, subject).json()["photo_path"]

        served = client.get(path)
        forged = client.get(f"{_URL}/{subject.id}/photo?t=forged")

        assert served.status_code == 200
        assert served.headers["content-type"] == "image/png"
        assert served.headers["Cache-Control"] == "private, max-age=3600"
        assert not images.has_metadata(served.content)
        assert forged.status_code == 404

    def test_a_token_minted_for_another_user_is_not_found(self, me, client, make, subject):
        other = make(make_user)
        self._put(me, subject)
        other_path = self._put(me, other).json()["photo_path"]
        token = other_path.split("?t=")[1]

        assert client.get(f"{_URL}/{subject.id}/photo?t={token}").status_code == 404

    def test_a_malformed_user_id_is_invalid_and_a_missing_token_is_invalid(self, client, subject):
        assert client.get(f"{_URL}/7/photo?t=tok").status_code == 422
        assert client.get(f"{_URL}/{subject.id}/photo").status_code == 422

    def test_a_user_without_a_photo_is_not_found_even_with_a_valid_token(self, client, subject):
        import modules.users.users.signing as users_signing

        token = users_signing.sign_user_image_token(subject.id)

        assert client.get(f"{_URL}/{subject.id}/photo?t={token}").status_code == 404

    def test_a_file_that_is_not_an_image_is_refused_and_nothing_is_stored(self, me, committed_sessions, subject):
        response = self._put(me, subject, name="me.png", data=b"not an image")

        assert response.status_code in {400, 415}
        assert _stored(committed_sessions, subject.id).photo_path is None

    def test_an_extension_that_is_not_an_image_is_unsupported(self, me, subject):
        assert self._put(me, subject, name="me.exe").status_code == 415

    def test_an_upload_for_a_missing_user_is_not_found(self, me):
        assert self._put(me, type("U", (), {"id": uuid.uuid4()})()).status_code == 404

    def test_an_administrators_upload_and_delete_are_audited_with_the_changed_field(
        self, me, committed_sessions, subject
    ):
        self._put(me, subject)
        deleted = me.client.delete(f"{_URL}/{subject.id}/photo")

        assert deleted.status_code == 204
        assert _stored(committed_sessions, subject.id).photo_path is None
        rows = _audit_rows(committed_sessions, users_audit_actions.USER_UPDATE)
        assert [row.details["changed_fields"] for row in rows] == [["photo_path"], ["photo_path"]]

    def test_deleting_a_photo_that_does_not_exist_is_idempotent_and_writes_no_row(
        self, me, committed_sessions, subject
    ):
        response = me.client.delete(f"{_URL}/{subject.id}/photo")

        assert response.status_code == 204
        assert _audit_rows(committed_sessions, users_audit_actions.USER_UPDATE) == []
