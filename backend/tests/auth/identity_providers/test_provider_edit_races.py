"""Edits of a provider that overlap each other, or a sign-in, against real PostgreSQL rows and row locks."""

import threading
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

import modules.auth.identity_provider_links.models as links_models
import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.models as idp_models
import modules.auth.sessions.models as sessions_models
from tests._factories.users import PASSWORD, make_admin
from tests.auth.identity_providers.conftest import API
from tests.auth.identity_providers.sso_helpers import audit, wait_until_a_session_waits_for_a_lock

STEP_UP = {"step_up": {"current_password": PASSWORD}}
UPDATE = "auth.identity_provider.update"


@pytest.fixture
def ctx(app, committed_sessions, sign_in, provider, make_provider) -> SimpleNamespace:
    """An administrator, signed in twice, and one provider."""
    with committed_sessions() as db:
        admin = make_admin(db, timezone="UTC")
        db.commit()
    return SimpleNamespace(
        sessions=committed_sessions,
        admin=sign_in(admin),
        other_admin=sign_in(admin),
        provider=provider,
        idp_id=make_provider("acme"),
    )


def _patch(client, idp_id, body, version=1):
    return client.patch(
        f"{API}/identity-providers/{idp_id}", json={**body, **STEP_UP}, headers={"If-Match": f'"{version}"'}
    )


def _in_thread(call):
    """Start a call on its own thread; the returned function joins it and gives its result."""
    box = []
    thread = threading.Thread(target=lambda: box.append(call()))
    thread.start()

    def join():
        thread.join(timeout=30)
        return box[0]

    return join


def _live_sessions(sessions) -> int:
    """Count the sessions that signed in through a provider and have not ended."""
    with sessions() as db:
        return db.scalar(
            sa.select(sa.func.count())
            .select_from(sessions_models.UsersSessions)
            .join(
                links_models.IdpSessionToken,
                links_models.IdpSessionToken.session_id == sessions_models.UsersSessions.id,
            )
        )


class TestVersions:
    def test_an_edit_needs_the_version_it_read_and_increments_it(self, ctx):
        first = _patch(ctx.admin.client, ctx.idp_id, {"name": "Renamed"})
        stale = _patch(ctx.admin.client, ctx.idp_id, {"name": "Stale"}, version=1)

        assert (first.status_code, first.headers["ETag"], first.json()["version"]) == (200, '"2"', 2)
        assert stale.status_code == 412

    def test_two_edits_that_read_the_same_version_apply_once(self, ctx):
        outcomes = []
        barrier = threading.Barrier(2)

        def edit(client, name):
            barrier.wait()
            outcomes.append(_patch(client, ctx.idp_id, {"name": name}))

        threads = [
            threading.Thread(target=edit, args=(ctx.admin.client, "One")),
            threading.Thread(target=edit, args=(ctx.other_admin.client, "Two")),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert sorted(response.status_code for response in outcomes) == [200, 412]
        with ctx.sessions() as db:
            assert idp_crud.get_identity_provider(ctx.idp_id, db).version == 2

    def test_an_edit_that_waits_for_a_competing_edit_is_refused_once_that_commits(self, ctx):
        with ctx.sessions() as holder:
            holder.execute(
                sa.select(idp_models.IdentityProvider)
                .where(idp_models.IdentityProvider.id == ctx.idp_id)
                .with_for_update()
            )
            waiting = _in_thread(lambda: _patch(ctx.admin.client, ctx.idp_id, {"name": "Late"}))
            wait_until_a_session_waits_for_a_lock(ctx.sessions)
            holder.execute(sa.update(idp_models.IdentityProvider).values(name="Competing", version=2))
            holder.commit()

        assert waiting().status_code == 412
        with ctx.sessions() as db:
            assert idp_crud.get_identity_provider(ctx.idp_id, db).name == "Competing"

    def test_an_edit_that_waits_while_the_provider_is_deleted_is_not_found(self, ctx):
        with ctx.sessions() as holder:
            holder.execute(
                sa.select(idp_models.IdentityProvider)
                .where(idp_models.IdentityProvider.id == ctx.idp_id)
                .with_for_update()
            )
            waiting = _in_thread(lambda: _patch(ctx.admin.client, ctx.idp_id, {"name": "Late"}))
            wait_until_a_session_waits_for_a_lock(ctx.sessions)
            holder.execute(sa.delete(idp_models.IdentityProvider).where(idp_models.IdentityProvider.id == ctx.idp_id))
            holder.commit()

        assert waiting().status_code == 404


class TestDisablingWhileSigningIn:
    @pytest.fixture(autouse=True)
    def _sign_up(self, sso_sign_up) -> None:
        pass

    def test_a_callback_for_a_provider_disabled_meanwhile_creates_no_session(self, ctx, browser):
        ctx.provider.claims = {"email": "raced@example.com", "email_verified": True}
        started = browser.start_login("acme")
        code, state = ctx.provider.authorize(started.authorization_url)
        # The provider is disabled while it redeems the code, after the callback has found it enabled.
        ctx.provider.on_token_request = lambda: _patch(ctx.admin.client, ctx.idp_id, {"enabled": False})

        finished = browser.callback("acme", state=state, code=code, binding=started.binding)

        assert finished.query["error"] == "sso_failed"
        assert _live_sessions(ctx.sessions) == 0

    def test_a_disable_waits_for_a_callback_holding_the_provider_and_then_ends_its_session(self, ctx, browser):
        with ctx.sessions() as callback:
            assert idp_crud.lock_provider_enabled(ctx.idp_id, callback) is True
            disabling = _in_thread(lambda: _patch(ctx.admin.client, ctx.idp_id, {"enabled": False}))
            wait_until_a_session_waits_for_a_lock(ctx.sessions)
            with ctx.sessions() as reader:
                assert idp_crud.get_identity_provider(ctx.idp_id, reader).enabled is True
            callback.rollback()

        assert disabling().status_code == 200
        with ctx.sessions() as reader:
            assert idp_crud.get_identity_provider(ctx.idp_id, reader).enabled is False

    def test_sessions_a_disable_ended_stay_gone_when_the_provider_is_enabled_again(self, ctx, browser):
        ctx.provider.claims = {"email": "again@example.com", "email_verified": True}
        _, finished = browser.sign_in("acme")
        assert browser.exchange(finished.session_id).status_code == 200
        assert _live_sessions(ctx.sessions) == 1

        assert _patch(ctx.admin.client, ctx.idp_id, {"enabled": False}).status_code == 200
        assert _live_sessions(ctx.sessions) == 0
        assert _patch(ctx.admin.client, ctx.idp_id, {"enabled": True}, version=2).status_code == 200

        assert _live_sessions(ctx.sessions) == 0
        _, again = browser.sign_in("acme")
        assert again.query["sso"] == "success"
        rows = audit(ctx.sessions, UPDATE)
        assert [row.details["sessions_ended"] for row in rows] == [1, 0]
