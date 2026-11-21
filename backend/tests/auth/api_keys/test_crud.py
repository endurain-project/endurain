"""API-key persistence on PostgreSQL: owner scoping, revocation, the active count, the stale purge and constraints."""

import uuid
from datetime import UTC, datetime, timedelta

import psycopg.errors
import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

import core.exceptions as core_exceptions
import modules.auth.api_keys.constants as api_keys_constants
import modules.auth.api_keys.crud as api_keys_crud
import modules.auth.api_keys.integration_service as api_keys_integration
import modules.auth.api_keys.models as api_keys_models
import modules.auth.api_keys.schema as api_keys_schema
import modules.users.users.crud as users_crud
from tests._factories.api_keys import make_api_key
from tests._factories.users import make_user

_SCOPES = [api_keys_constants.ApiKeyScope.ACTIVITIES_UPLOAD]


def _key(db, user, **options) -> api_keys_schema.UserApiKeyRead:
    return make_api_key(db, user, scopes=_SCOPES, **options)[0]


def _set(db, key_id: uuid.UUID, **values: object) -> None:
    """Rewrite columns of a stored key, to arrange a state that only time produces."""
    db.execute(
        sa.update(api_keys_models.UsersApiKeys).where(api_keys_models.UsersApiKeys.id == key_id).values(**values)
    )
    db.flush()
    db.expire_all()


def _row(db, key_id: uuid.UUID) -> api_keys_models.UsersApiKeys | None:
    return db.get(api_keys_models.UsersApiKeys, key_id)


class TestReads:
    def test_a_page_lists_the_owners_keys_newest_first_and_ties_break_on_the_id(self, db):
        user, other = make_user(db), make_user(db)
        oldest, middle, newest = (_key(db, user, name=name) for name in ("oldest", "middle", "newest"))
        _key(db, other, name="not mine")
        base = datetime.now(UTC)
        _set(db, oldest.id, created_at=base - timedelta(days=2))
        _set(db, middle.id, created_at=base - timedelta(days=1))
        _set(db, newest.id, created_at=base)

        page = api_keys_crud.get_api_keys_page(user.id, db, limit=10, offset=0)

        assert [key.name for key in page] == ["newest", "middle", "oldest"]

        twins = [_key(db, user, name="twin") for _ in range(2)]
        for twin in twins:
            _set(db, twin.id, created_at=base + timedelta(days=1))
        tied = api_keys_crud.get_api_keys_page(user.id, db, limit=2, offset=0)
        assert [key.id for key in tied] == sorted(twin.id for twin in twins)

    def test_a_page_honours_the_limit_and_offset_and_the_count_covers_every_page(self, db):
        user = make_user(db)
        for _ in range(3):
            _key(db, user)

        first = api_keys_crud.get_api_keys_page(user.id, db, limit=2, offset=0)
        rest = api_keys_crud.get_api_keys_page(user.id, db, limit=2, offset=2)

        assert (len(first), len(rest)) == (2, 1)
        assert {key.id for key in first}.isdisjoint(key.id for key in rest)
        assert api_keys_crud.count_api_keys(user.id, db) == 3
        assert api_keys_crud.count_api_keys(make_user(db).id, db) == 0

    def test_a_key_is_found_by_id_only_for_its_owner_and_by_hash_for_anyone(self, db):
        user, other = make_user(db), make_user(db)
        key, raw_key = make_api_key(db, user, scopes=_SCOPES)

        assert api_keys_crud.get_api_key_by_id(key.id, user.id, db) == key
        assert api_keys_crud.get_api_key_by_id(key.id, other.id, db) is None
        assert api_keys_crud.get_api_key_by_id(uuid.uuid4(), user.id, db) is None
        assert api_keys_integration.get_api_key_by_hash(api_keys_integration.hash_api_key(raw_key), db) == key
        assert api_keys_crud.get_api_key_by_hash("0" * 64, db) is None


class TestCreate:
    def test_a_stored_key_keeps_the_hash_and_a_prefix_never_the_raw_key(self, db):
        user = make_user(db)
        key, raw_key = make_api_key(db, user, scopes=_SCOPES, name="CLI")

        stored = _row(db, key.id)

        assert stored is not None
        assert stored.key_hash == api_keys_integration.hash_api_key(raw_key)
        assert stored.key_prefix == raw_key[9:17]
        assert raw_key not in (stored.scopes, stored.key_hash, stored.key_prefix, stored.name)
        assert (stored.is_active, stored.revoked_at, stored.last_used_at) == (True, None, None)
        assert key.scopes == _SCOPES

    def test_two_keys_cannot_share_a_hash(self, db):
        user = make_user(db)
        first, _ = make_api_key(db, user, scopes=_SCOPES)
        duplicate = api_keys_models.UsersApiKeys(
            user_id=user.id,
            name="dup",
            key_prefix="abcdefgh",
            key_hash=_row(db, first.id).key_hash,
            scopes="[]",
            expires_at=datetime.now(UTC) + timedelta(days=1),
            created_at=datetime.now(UTC),
            is_active=True,
        )
        db.add(duplicate)

        with pytest.raises(IntegrityError) as exc_info:
            db.flush()

        assert isinstance(exc_info.value.orig, psycopg.errors.UniqueViolation)

    def test_deleting_a_user_deletes_their_keys(self, db):
        user, other = make_user(db), make_user(db)
        key, kept = _key(db, user), _key(db, other)

        users_crud.delete_user(user.id, db)
        db.flush()
        db.expire_all()

        assert _row(db, key.id) is None
        assert _row(db, kept.id) is not None


class TestLastUsed:
    def test_the_stamp_is_the_current_time(self, db):
        key = _key(db, make_user(db))
        before = datetime.now(UTC)

        api_keys_crud.update_last_used(key.id, db)

        stamped = _row(db, key.id).last_used_at
        assert stamped is not None and before <= stamped <= datetime.now(UTC)

    def test_stamping_a_missing_key_is_not_found(self, db):
        with pytest.raises(core_exceptions.NotFoundError):
            api_keys_crud.update_last_used(uuid.uuid4(), db)


class TestRevokeAndDelete:
    def test_revoking_a_key_deactivates_it_and_keeps_the_first_revocation_time(self, db):
        user = make_user(db)
        key = _key(db, user)

        api_keys_crud.revoke_api_key(key.id, user.id, db)
        first = _row(db, key.id).revoked_at
        _set(db, key.id, revoked_at=first - timedelta(days=3))
        earlier = _row(db, key.id).revoked_at
        api_keys_crud.revoke_api_key(key.id, user.id, db)

        row = _row(db, key.id)
        assert row.is_active is False
        assert first is not None
        assert row.revoked_at == earlier

    def test_another_users_key_and_a_missing_key_are_not_found_and_stay_untouched(self, db):
        user, other = make_user(db), make_user(db)
        key = _key(db, user)

        for target in (key.id, uuid.uuid4()):
            with pytest.raises(core_exceptions.NotFoundError):
                api_keys_crud.revoke_api_key(target, other.id, db)
            with pytest.raises(core_exceptions.NotFoundError):
                api_keys_crud.delete_api_key(target, other.id, db)

        row = _row(db, key.id)
        assert (row.is_active, row.revoked_at) == (True, None)

    def test_deleting_a_key_removes_only_that_key(self, db):
        user = make_user(db)
        gone, kept = _key(db, user), _key(db, user)

        api_keys_crud.delete_api_key(gone.id, user.id, db)
        db.expire_all()

        assert _row(db, gone.id) is None
        assert _row(db, kept.id) is not None

    def test_revoking_every_key_of_a_user_deactivates_only_their_active_keys(self, db):
        user, other = make_user(db), make_user(db)
        active_a, active_b, already = _key(db, user), _key(db, user), _key(db, user)
        api_keys_crud.revoke_api_key(already.id, user.id, db)
        untouched = _key(db, other)

        revoked = api_keys_crud.revoke_all_api_keys_for_user(user.id, db)
        db.expire_all()

        assert revoked == 2
        assert [_row(db, key.id).is_active for key in (active_a, active_b, already)] == [False, False, False]
        assert _row(db, active_a.id).revoked_at is not None
        assert _row(db, untouched.id).is_active is True


class TestActiveCount:
    def test_revoked_expired_and_other_users_keys_do_not_count(self, db):
        user, other = make_user(db), make_user(db)
        now = datetime.now(UTC)
        _key(db, user, expires_at=now + timedelta(days=1))
        _key(db, user, expires_at=now + timedelta(days=2))
        revoked = _key(db, user)
        api_keys_crud.revoke_api_key(revoked.id, user.id, db)
        _key(db, user, expires_at=now + timedelta(seconds=1))
        _key(db, other)

        assert api_keys_crud.count_active_api_keys(user.id, now + timedelta(seconds=2), db) == 2
        assert api_keys_crud.count_active_api_keys(user.id, now, db) == 3
        assert api_keys_integration.count_active_api_keys(user.id, db) == 3


class TestStalePurge:
    def _arrange(self, db):
        user = make_user(db)
        now = datetime.now(UTC)
        cutoff = now - timedelta(days=30)
        live = _key(db, user)
        revoked_recently = _key(db, user)
        api_keys_crud.revoke_api_key(revoked_recently.id, user.id, db)
        expired_recently = _key(db, user)
        _set(db, expired_recently.id, expires_at=now - timedelta(days=1))
        revoked_long_ago = _key(db, user)
        api_keys_crud.revoke_api_key(revoked_long_ago.id, user.id, db)
        _set(db, revoked_long_ago.id, revoked_at=cutoff - timedelta(days=1))
        expired_long_ago = _key(db, user)
        _set(db, expired_long_ago.id, expires_at=cutoff - timedelta(days=1))
        kept = {live.id, revoked_recently.id, expired_recently.id}
        stale = {revoked_long_ago.id, expired_long_ago.id}
        return cutoff, kept, stale

    def _remaining(self, db, ids: set[uuid.UUID]) -> set[uuid.UUID]:
        return set(
            db.scalars(sa.select(api_keys_models.UsersApiKeys.id).where(api_keys_models.UsersApiKeys.id.in_(ids)))
        )

    def test_only_keys_revoked_or_expired_before_the_cutoff_are_deleted(self, db):
        cutoff, kept, stale = self._arrange(db)

        assert api_keys_crud.delete_stale_api_keys(cutoff, 100, db) == 2

        assert self._remaining(db, kept | stale) == kept

    def test_a_purge_deletes_at_most_the_batch_limit(self, db):
        cutoff, _kept, stale = self._arrange(db)

        assert api_keys_crud.delete_stale_api_keys(cutoff, 1, db) == 1

        assert len(self._remaining(db, stale)) == 1
