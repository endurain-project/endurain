"""Administering identity providers over HTTP: listing, creating, deleting and the icon of a provider."""

import io
import uuid
from types import SimpleNamespace

import jasil.runtime as platform_runtime
import pytest
from PIL import Image

import core.config as core_config
import modules.auth.identity_providers.constants as idp_constants
import modules.auth.identity_providers.crud as idp_crud
import modules.auth.identity_providers.scheduled_jobs as idp_scheduled_jobs
import modules.auth.identity_providers.schema as idp_schema
from tests._factories.identity_links import make_identity_link, make_identity_provider
from tests._factories.users import PASSWORD, make_admin, make_user
from tests._helpers.images import png_with_text
from tests.auth.identity_providers.sso_helpers import audit

API = core_config.ROOT_PATH
STEP_UP = {"step_up": {"current_password": PASSWORD}}
CREATE = "auth.identity_provider.create"
UPDATE = "auth.identity_provider.update"
DELETE = "auth.identity_provider.delete"


@pytest.fixture
def ctx(app, committed_sessions, sign_in, provider) -> SimpleNamespace:
    """An administrator and a regular user, signed in, with a provider on the loopback interface."""
    with committed_sessions() as db:
        admin = make_admin(db, timezone="UTC")
        member = make_user(db)
        db.commit()
    return SimpleNamespace(
        sessions=committed_sessions,
        provider=provider,
        admin=sign_in(admin),
        member=sign_in(member),
        member_user=member,
    )


def _body(provider, **fields) -> dict:
    return {
        "name": "Acme",
        "slug": f"acme-{uuid.uuid4().hex[:6]}",
        "provider_type": "oidc",
        "issuer_url": provider.issuer,
        "client_id": "endurain-client",
        "client_secret": "endurain-secret",
        "enabled": True,
        **fields,
        **STEP_UP,
    }


def _create(ctx, **fields):
    return ctx.admin.client.post(f"{API}/identity-providers", json=_body(ctx.provider, **fields))


def _delete(ctx, idp_id, version=1, step_up=STEP_UP):
    return ctx.admin.client.post(
        f"{API}/identity-providers/{idp_id}/delete", json=step_up, headers={"If-Match": f'"{version}"'}
    )


class TestReading:
    def test_the_list_pages_through_the_providers_and_never_shows_a_secret(self, ctx):
        with ctx.sessions() as db:
            for slug in ("a", "b", "c"):
                make_identity_provider(db, slug)
            db.commit()

        first = ctx.admin.client.get(f"{API}/identity-providers", params={"page_number": 1, "num_records": 2})
        second = ctx.admin.client.get(f"{API}/identity-providers", params={"page_number": 2, "num_records": 2})

        assert first.status_code == 200
        assert (len(first.json()["items"]), first.json()["total"]) == (2, 3)
        assert len(second.json()["items"]) == 1
        assert "client_secret" not in first.text

    def test_reading_one_provider_gives_its_version_as_the_etag_and_whether_users_are_linked(self, ctx):
        with ctx.sessions() as db:
            idp_id = make_identity_provider(db, "linked")
            make_identity_link(db, ctx.member_user.id, idp_id, "s")
            db.commit()

        response = ctx.admin.client.get(f"{API}/identity-providers/{idp_id}")

        assert response.status_code == 200
        assert response.headers["ETag"] == '"1"'
        assert response.json()["has_linked_users"] is True
        assert "client_secret" not in response.json()

    def test_an_unknown_provider_is_not_found(self, ctx):
        assert ctx.admin.client.get(f"{API}/identity-providers/{uuid.uuid4()}").status_code == 404

    def test_the_templates_list_the_built_in_provider_presets(self, ctx):
        response = ctx.admin.client.get(f"{API}/identity-providers/templates")

        assert response.status_code == 200
        assert {item["template_id"] for item in response.json()} == set(idp_constants.IDP_TEMPLATES)

    def test_a_regular_user_cannot_read_the_configuration(self, ctx):
        assert ctx.member.client.get(f"{API}/identity-providers").status_code == 403

    def test_the_public_list_shows_only_enabled_providers_and_only_public_fields(self, ctx, client):
        with ctx.sessions() as db:
            make_identity_provider(db, "on")
            off = make_identity_provider(db, "off")
            idp_crud.update_identity_provider(off, idp_schema.IdentityProviderUpdate(enabled=False), db, if_match='"1"')
            db.commit()

        response = client.get(f"{API}/public/idp")

        assert response.status_code == 200
        items = response.json()["items"]
        assert [item["slug"] for item in items] == ["on"]
        assert set(items[0]) == {"id", "name", "slug", "icon", "icon_uploaded"}


class TestCreating:
    def test_a_created_provider_is_stored_encrypted_audited_and_located(self, ctx):
        response = _create(ctx, slug="acme-one")

        assert response.status_code == 201, response.text
        assert response.headers["ETag"] == '"1"'
        body = response.json()
        assert body["slug"] == "acme-one"
        assert response.headers["Location"].endswith(f"/identity-providers/{body['id']}")
        assert "client_secret" not in body
        with ctx.sessions() as db:
            stored = idp_crud.get_identity_provider(uuid.UUID(body["id"]), db)
        assert stored.client_secret != "endurain-secret"
        assert stored.client_id != "endurain-client"
        (row,) = audit(ctx.sessions, CREATE)
        assert row.details == {"provider_type": "oidc"}
        assert row.target_id == body["id"]

    def test_a_failed_step_up_creates_nothing(self, ctx):
        response = ctx.admin.client.post(
            f"{API}/identity-providers",
            json={**_body(ctx.provider), "step_up": {"current_password": "wrong"}},
        )

        assert response.status_code == 403
        assert audit(ctx.sessions, CREATE) == []

    def test_a_slug_in_use_is_a_conflict(self, ctx):
        _create(ctx, slug="same")

        response = _create(ctx, slug="same", issuer_url=None, provider_type="oauth2", scopes="profile")

        assert response.status_code == 409

    def test_an_issuer_another_provider_uses_is_refused_with_its_own_problem_type(self, ctx):
        assert _create(ctx).status_code == 201

        response = _create(ctx)

        assert response.status_code == 409
        assert response.json()["type"].endswith("issuer-in-use")

    @pytest.mark.parametrize("field", ["issuer_url", "token_endpoint", "authorization_endpoint", "userinfo_endpoint"])
    def test_a_plain_http_url_outside_the_allowed_hosts_is_refused(self, field, ctx, monkeypatch):
        monkeypatch.setattr(core_config.settings, "SSRF_ALLOWED_HOSTS", [])
        body = _body(ctx.provider, issuer_url=None, provider_type="oauth2", scopes="profile")
        body[field] = f"http://{uuid.uuid4().hex[:6]}.example.org/x"

        response = ctx.admin.client.post(f"{API}/identity-providers", json=body)

        assert response.status_code == 400, response.text
        assert field in response.json()["detail"]

    def test_an_address_on_a_private_network_is_refused_unless_the_host_is_allowed(self, ctx, monkeypatch):
        monkeypatch.setattr(core_config.settings, "SSRF_ALLOWED_HOSTS", [])

        response = ctx.admin.client.post(f"{API}/identity-providers", json=_body(ctx.provider))

        assert response.status_code == 400

    def test_an_oidc_provider_needs_an_issuer_and_the_openid_scope(self, ctx):
        no_issuer = _create(ctx, issuer_url=None)
        no_scope = _create(ctx, scopes="profile email")

        assert (no_issuer.status_code, no_scope.status_code) == (422, 422)


class TestUpdating:
    def test_disabling_a_provider_ends_the_sessions_it_signed_in_and_audits_how_many(self, ctx, browser, sso_sign_up):
        created = _create(ctx, slug="acme").json()
        browser.provider.claims = {"email": "member@example.com", "email_verified": True}
        _, finished = browser.sign_in("acme")
        token = browser.exchange(finished.session_id).json()["access_token"]
        assert browser.client.get(f"{API}/profile", headers={"Authorization": f"Bearer {token}"}).status_code == 200

        response = ctx.admin.client.patch(
            f"{API}/identity-providers/{created['id']}",
            json={"enabled": False, **STEP_UP},
            headers={"If-Match": '"1"'},
        )

        assert response.status_code == 200, response.text
        assert browser.client.get(f"{API}/profile", headers={"Authorization": f"Bearer {token}"}).status_code == 401
        (row,) = audit(ctx.sessions, UPDATE)
        assert row.details == {"changed_fields": ["enabled"], "sessions_ended": 1}

    def test_a_disabled_provider_signs_nobody_in(self, ctx, browser):
        created = _create(ctx, slug="acme").json()
        ctx.admin.client.patch(
            f"{API}/identity-providers/{created['id']}", json={"enabled": False, **STEP_UP}, headers={"If-Match": '"1"'}
        )

        response = browser.client.get(
            f"{API}/public/idp/login/acme",
            params={"code_challenge": "c" * 43, "code_challenge_method": "S256"},
            follow_redirects=False,
        )

        assert response.status_code == 404

    def test_an_edit_drops_the_cached_discovery_document(self, ctx, browser):
        created = _create(ctx, slug="acme").json()
        browser.start_login("acme")
        ctx.provider.discovery = {"authorization_endpoint": f"{ctx.provider.issuer}/moved"}
        assert browser.start_login("acme").authorization_url.startswith(ctx.provider.authorization_endpoint)

        ctx.admin.client.patch(
            f"{API}/identity-providers/{created['id']}",
            json={"name": "Renamed", **STEP_UP},
            headers={"If-Match": '"1"'},
        )

        assert browser.start_login("acme").authorization_url.startswith(f"{ctx.provider.issuer}/moved")

    def test_a_change_of_credentials_is_audited_by_field_name_never_by_value(self, ctx):
        created = _create(ctx, slug="acme").json()

        ctx.admin.client.patch(
            f"{API}/identity-providers/{created['id']}",
            json={"client_secret": "rotated", "name": "Renamed", **STEP_UP},
            headers={"If-Match": '"1"'},
        )

        (row,) = audit(ctx.sessions, UPDATE)
        assert row.details["changed_fields"] == ["client_secret", "name"]
        assert "rotated" not in repr(row.details)

    def test_a_patch_that_changes_nothing_writes_no_audit_row(self, ctx):
        created = _create(ctx, slug="acme").json()

        ctx.admin.client.patch(
            f"{API}/identity-providers/{created['id']}", json={"name": "Acme", **STEP_UP}, headers={"If-Match": '"1"'}
        )

        assert audit(ctx.sessions, UPDATE) == []

    def test_a_slug_another_provider_holds_is_a_conflict(self, ctx):
        _create(ctx, slug="taken")
        other = _create(ctx, slug="other", issuer_url=None, provider_type="oauth2", scopes="profile").json()

        response = ctx.admin.client.patch(
            f"{API}/identity-providers/{other['id']}", json={"slug": "taken", **STEP_UP}, headers={"If-Match": '"1"'}
        )

        assert response.status_code == 409

    def test_a_provider_without_links_may_change_its_slug_endpoints_and_issuer(self, ctx):
        plain = _create(ctx, slug="plain", issuer_url=None, provider_type="oauth2", scopes="profile").json()

        response = ctx.admin.client.patch(
            f"{API}/identity-providers/{plain['id']}",
            json={
                "slug": "renamed",
                "issuer_url": ctx.provider.issuer,
                "token_endpoint": ctx.provider.token_endpoint,
                **STEP_UP,
            },
            headers={"If-Match": '"1"'},
        )

        assert response.status_code == 200, response.text
        assert (response.json()["slug"], response.json()["issuer_url"]) == ("renamed", ctx.provider.issuer)
        rows = audit(ctx.sessions, UPDATE)
        assert rows[0].details["changed_fields"] == ["issuer_url", "slug", "token_endpoint"]

    def test_an_unknown_provider_is_not_found(self, ctx):
        response = ctx.admin.client.patch(
            f"{API}/identity-providers/{uuid.uuid4()}", json={"name": "x", **STEP_UP}, headers={"If-Match": '"1"'}
        )

        assert response.status_code == 404

    def test_a_failed_step_up_changes_nothing(self, ctx):
        created = _create(ctx, slug="acme").json()

        response = ctx.admin.client.patch(
            f"{API}/identity-providers/{created['id']}",
            json={"name": "x", "step_up": {"current_password": "wrong"}},
            headers={"If-Match": '"1"'},
        )

        assert response.status_code == 403
        assert ctx.admin.client.get(f"{API}/identity-providers/{created['id']}").json()["name"] == "Acme"


class TestDeleting:
    def test_a_provider_without_links_is_deleted_and_audited(self, ctx):
        created = _create(ctx).json()

        response = _delete(ctx, created["id"])

        assert response.status_code == 204, response.text
        assert ctx.admin.client.get(f"{API}/identity-providers/{created['id']}").status_code == 404
        (row,) = audit(ctx.sessions, DELETE)
        assert row.target_id == created["id"]

    def test_a_provider_with_linked_users_is_a_conflict_and_stays(self, ctx):
        with ctx.sessions() as db:
            idp_id = make_identity_provider(db, "linked")
            make_identity_link(db, ctx.member_user.id, idp_id, "s")
            db.commit()

        response = _delete(ctx, idp_id)

        assert response.status_code == 409
        assert ctx.admin.client.get(f"{API}/identity-providers/{idp_id}").status_code == 200

    def test_a_stale_version_is_refused_and_a_missing_one_is_required(self, ctx):
        created = _create(ctx).json()

        stale = _delete(ctx, created["id"], version=9)
        missing = ctx.admin.client.post(f"{API}/identity-providers/{created['id']}/delete", json=STEP_UP)

        assert (stale.status_code, missing.status_code) == (412, 428)

    def test_an_unknown_provider_is_not_found(self, ctx):
        assert _delete(ctx, uuid.uuid4()).status_code == 404

    def test_a_failed_step_up_deletes_nothing(self, ctx):
        created = _create(ctx).json()

        response = _delete(ctx, created["id"], step_up={"step_up": {"current_password": "wrong"}})

        assert response.status_code == 403
        assert ctx.admin.client.get(f"{API}/identity-providers/{created['id']}").status_code == 200

    def test_the_icon_goes_with_the_provider(self, ctx):
        created = _create(ctx).json()
        ctx.admin.client.put(
            f"{API}/identity-providers/{created['id']}/icon", files={"file": ("i.png", png_with_text(), "image/png")}
        )
        storage = platform_runtime.get_active_platform().storage
        assert storage.get(idp_constants.ICON_STORAGE_AREA, created["id"]) is not None

        version = ctx.admin.client.get(f"{API}/identity-providers/{created['id']}").headers["ETag"]
        assert _delete(ctx, created["id"], version=int(version.strip('"'))).status_code == 204

        assert storage.get(idp_constants.ICON_STORAGE_AREA, created["id"]) is None


class TestIcon:
    def _put(self, ctx, idp_id, data=None, content_type="image/png", name="i.png"):
        return ctx.admin.client.put(
            f"{API}/identity-providers/{idp_id}/icon", files={"file": (name, data or png_with_text(), content_type)}
        )

    def test_an_uploaded_icon_is_served_publicly_with_a_version_tag_and_revalidation(self, ctx, client):
        created = _create(ctx, slug="acme").json()

        put = self._put(ctx, created["id"])
        served = client.get(f"{API}/public/idp/acme/icon")

        assert put.status_code == 201
        assert served.status_code == 200
        assert served.headers["Content-Type"] == "image/png"
        assert served.headers["Cache-Control"] == "public, no-cache"
        assert served.headers["ETag"] == f'"{put.json()["version"]}"'
        assert Image.open(io.BytesIO(served.content)).size == (8, 8)

    def test_a_client_holding_the_current_version_gets_a_304_without_the_image(self, ctx, client):
        created = _create(ctx, slug="acme").json()
        version = self._put(ctx, created["id"]).json()["version"]

        response = client.get(f"{API}/public/idp/acme/icon", headers={"If-None-Match": f'"{version}"'})

        assert response.status_code == 304
        assert response.content == b""

    def test_replacing_the_icon_answers_200_and_a_new_version_so_clients_refetch(self, ctx, client):
        created = _create(ctx, slug="acme").json()
        first = self._put(ctx, created["id"])

        second = self._put(ctx, created["id"])
        stale = client.get(f"{API}/public/idp/acme/icon", headers={"If-None-Match": f'"{first.json()["version"]}"'})

        assert second.status_code == 200
        assert second.json()["version"] > first.json()["version"]
        assert stale.status_code == 200

    def test_the_stored_icon_has_its_metadata_removed(self, ctx, client):
        created = _create(ctx, slug="acme").json()
        self._put(ctx, created["id"], png_with_text())

        served = client.get(f"{API}/public/idp/acme/icon")

        assert "Location" not in Image.open(io.BytesIO(served.content)).info

    def test_a_deleted_icon_is_no_longer_served_and_the_blob_is_gone(self, ctx, client):
        created = _create(ctx, slug="acme").json()
        self._put(ctx, created["id"])

        response = ctx.admin.client.delete(f"{API}/identity-providers/{created['id']}/icon")

        assert response.status_code == 204
        assert client.get(f"{API}/public/idp/acme/icon").status_code == 404
        storage = platform_runtime.get_active_platform().storage
        assert storage.get(idp_constants.ICON_STORAGE_AREA, created["id"]) is None

    def test_a_storage_outage_while_deleting_the_icon_still_stops_serving_it(self, ctx, client, monkeypatch):
        from jasil.providers import StorageBackendUnavailableError

        created = _create(ctx, slug="acme").json()
        self._put(ctx, created["id"])
        storage = platform_runtime.get_active_platform().storage

        def down(area, key):
            raise StorageBackendUnavailableError("down")

        monkeypatch.setattr(storage, "delete", down)

        response = ctx.admin.client.delete(f"{API}/identity-providers/{created['id']}/icon")

        assert response.status_code == 204
        assert client.get(f"{API}/public/idp/acme/icon").status_code == 404

    def test_an_icon_whose_provider_is_deleted_while_the_blob_is_written_is_not_found_and_leaves_no_blob(
        self, ctx, monkeypatch
    ):
        import sqlalchemy as sa

        import modules.auth.identity_providers.models as idp_models

        created = _create(ctx, slug="acme").json()
        storage = platform_runtime.get_active_platform().storage
        original = storage.save

        def save_then_lose_the_provider(area, key, data, content_type):
            original(area, key, data, content_type)
            with ctx.sessions() as db:
                db.execute(sa.delete(idp_models.IdentityProvider))
                db.commit()

        monkeypatch.setattr(storage, "save", save_then_lose_the_provider)

        response = self._put(ctx, created["id"])

        assert response.status_code == 404
        assert storage.get(idp_constants.ICON_STORAGE_AREA, created["id"]) is None

    def test_an_icon_flag_without_a_blob_serves_none(self, ctx, client):
        created = _create(ctx, slug="acme").json()
        self._put(ctx, created["id"])
        platform_runtime.get_active_platform().storage.delete(idp_constants.ICON_STORAGE_AREA, created["id"])

        assert client.get(f"{API}/public/idp/acme/icon").status_code == 404

    def test_a_provider_without_an_icon_serves_none(self, ctx, client):
        _create(ctx, slug="acme")

        assert client.get(f"{API}/public/idp/acme/icon").status_code == 404
        assert client.get(f"{API}/public/idp/nobody/icon").status_code == 404

    def test_an_icon_change_is_audited_as_a_provider_update(self, ctx):
        created = _create(ctx, slug="acme").json()

        self._put(ctx, created["id"])
        ctx.admin.client.delete(f"{API}/identity-providers/{created['id']}/icon")

        rows = audit(ctx.sessions, UPDATE)
        assert [row.details["changed_fields"] for row in rows] == [["icon_uploaded"], ["icon_uploaded"]]

    @pytest.mark.parametrize(
        ("data", "content_type", "status"),
        [(b"not an image", "image/png", 415), (b"<svg xmlns='http://www.w3.org/2000/svg'/>", "image/svg+xml", 415)],
    )
    def test_something_that_is_not_a_raster_image_is_refused(self, data, content_type, status, ctx):
        created = _create(ctx, slug="acme").json()

        response = self._put(ctx, created["id"], data, content_type)

        assert response.status_code in (400, status), response.text

    def test_an_icon_over_the_size_cap_is_refused(self, ctx):
        created = _create(ctx, slug="acme").json()
        big = png_with_text(size=(1200, 1200)) + b"\x00" * idp_constants.ICON_MAX_BYTES

        response = self._put(ctx, created["id"], big)

        assert response.status_code == 413

    def test_an_icon_for_an_unknown_provider_is_not_found(self, ctx):
        assert self._put(ctx, uuid.uuid4()).status_code == 404
        assert ctx.admin.client.delete(f"{API}/identity-providers/{uuid.uuid4()}/icon").status_code == 404

    def test_a_regular_user_cannot_change_an_icon(self, ctx):
        created = _create(ctx, slug="acme").json()

        response = ctx.member.client.put(
            f"{API}/identity-providers/{created['id']}/icon", files={"file": ("i.png", png_with_text(), "image/png")}
        )

        assert response.status_code == 403

    def test_the_sweep_removes_blobs_no_provider_names_and_keeps_the_rest(self, ctx, monkeypatch):
        import time

        import core.blob_sweep as core_blob_sweep

        kept = _create(ctx, slug="acme").json()
        self._put(ctx, kept["id"])
        storage = platform_runtime.get_active_platform().storage
        orphan = str(uuid.uuid4())
        storage.save(idp_constants.ICON_STORAGE_AREA, orphan, png_with_text(), "image/png")
        storage.save(idp_constants.ICON_STORAGE_AREA, "not-a-provider-id", png_with_text(), "image/png")

        # a blob younger than an hour is never swept, so the clock moves past that
        monkeypatch.setattr(core_blob_sweep, "time", lambda: time.time() + 2 * core_blob_sweep.MIN_AGE_SECONDS)

        idp_scheduled_jobs.sweep_unreferenced_icons()

        assert storage.get(idp_constants.ICON_STORAGE_AREA, orphan) is None
        assert storage.get(idp_constants.ICON_STORAGE_AREA, kept["id"]) is not None
        assert storage.get(idp_constants.ICON_STORAGE_AREA, "not-a-provider-id") is not None
