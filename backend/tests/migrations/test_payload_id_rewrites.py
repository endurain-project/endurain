"""Every event payload and audit detail that carries an integer id is covered by a conversion revision.

The UUID conversion revisions rewrite the integer ids stored inside event payloads in place. A conversion revision
that does so declares a module-level constant::

    PAYLOAD_ID_REWRITES = (
        ("modules.activities.activity.events.ActivityCreatedPayload", "activity_id",
         ("activity.created",), "activities"),
    )

Each entry is ``(payload_class, field, stored_under, parent_table)``:

* ``payload_class`` is the dotted path of the payload class.
* ``field`` is the payload key holding the id.
* ``stored_under`` is a tuple of the event types, or of the audit action ids for audit details, under which rows
  carry that class.
* ``parent_table`` is the table whose ids the field holds.

The revision's own rewrite SQL iterates that constant, so what is declared is what is rewritten.

The ``*Details`` classes of the audit trail are not event payloads and are not rewritten: no production database has
audit rows yet and a signed checkpoint covers the ones that exist. A revision that changes the type of an audit
detail id declares it in a second constant of the same entry shape, ``AUDIT_DETAIL_ID_CHANGES``, whose
``stored_under`` holds the audit action ids. This test reads both constants.

This test discovers every ``VersionedPayload`` subclass of the ``modules`` and ``core`` packages and every one of
its integer id fields (named ``id`` or ending in ``_id`` or ``_ids``). Each must be declared by a revision or sit in
``_NOT_YET_REWRITTEN``. That list only shrinks: the revision that converts an entry declares it and deletes it from
the list in the same change.
"""

import importlib
import pkgutil
import types
import typing
import uuid
from collections.abc import Iterable

import pytest
from jasil.event_versioning import VersionedPayload
from pydantic import BaseModel
from tests._helpers import alembic_chain

from core.database import Base

_PACKAGES = ("modules", "core")
_OWNED_PREFIXES = tuple(f"{package}." for package in _PACKAGES)

#: Integer id fields of payload classes that no revision converts yet, as (dotted class, field).
#: Step 9 requires this list to be empty.
_NOT_YET_REWRITTEN: frozenset[tuple[str, str]] = frozenset()

#: Every integer id field of a payload class as the v0.21 code had them, as (dotted class, field). It is fixed and
#: never shrinks: each pair must be declared in PAYLOAD_ID_REWRITES or still sit in _NOT_YET_REWRITTEN, so emptying
#: the allowlist without a rewrite spec fails.
_BASELINE: frozenset[tuple[str, str]] = frozenset(
    {
        # modules.activities.activity.events
        ("modules.activities.activity.events.ActivityCreatedPayload", "activity_id"),
        ("modules.activities.activity.events.ActivityCreatedPayload", "user_id"),
        ("modules.activities.activity.events.ActivityDeletedPayload", "activity_id"),
        ("modules.activities.activity.events.ActivityUpdatedPayload", "activity_id"),
        ("modules.activities.activity.events.ActivityUpdatedPayload", "user_id"),
        ("modules.activities.activity.events.VisibilityEditRequestedPayload", "user_id"),
        # modules.auth.account_security.audit_actions (audit details)
        ("modules.auth.account_security.audit_actions.IdentityLinkDetails", "idp_id"),
        # modules.auth.account_security.events
        ("modules.auth.account_security.events.AccountSecurityChangedPayload", "user_id"),
        ("modules.auth.account_security.events.AccountSecurityChangedPayload", "idp_id"),
        ("modules.auth.account_security.events.StepUpLockedPayload", "user_id"),
        ("modules.auth.account_security.events.StepUpSessionEndedPayload", "user_id"),
        # modules.auth.authentication.events
        ("modules.auth.authentication.events.AccountLockedPayload", "user_id"),
        ("modules.auth.authentication.events.MfaLockedPayload", "user_id"),
        ("modules.auth.authentication.events.RefreshReuseDetectedPayload", "user_id"),
        # modules.auth.identity_providers.audit_actions (audit details)
        ("modules.auth.identity_providers.audit_actions.BackchannelLogoutRefusalDetails", "idp_id"),
        ("modules.auth.identity_providers.audit_actions.IdentityLinkDetails", "idp_id"),
        # modules.auth.identity_providers.events
        ("modules.auth.identity_providers.events.IdpLinkedPayload", "user_id"),
        ("modules.auth.identity_providers.events.IdpLinkedPayload", "idp_id"),
        ("modules.auth.identity_providers.events.IdpTokenRefreshPayload", "user_id"),
        # modules.auth.known_devices.events
        ("modules.auth.known_devices.events.NewDeviceSignInPayload", "user_id"),
        # modules.auth.mfa_backup_codes.events
        ("modules.auth.mfa_backup_codes.events.BackupCodeUsedPayload", "user_id"),
        # modules.auth.password_reset_tokens.events
        ("modules.auth.password_reset_tokens.events.PasswordResetCompletedPayload", "user_id"),
        ("modules.auth.password_reset_tokens.events.PasswordResetRequestedPayload", "user_id"),
        # modules.auth.sessions.events
        ("modules.auth.sessions.events.SessionsRevokedPayload", "user_id"),
        # modules.auth.sign_up_tokens.events
        ("modules.auth.sign_up_tokens.events.EmailChangedPayload", "user_id"),
        ("modules.auth.sign_up_tokens.events.SignUpApprovalRequestedPayload", "user_id"),
        ("modules.auth.sign_up_tokens.events.SignUpApprovalRequestedPayload", "admin_user_id"),
        ("modules.auth.sign_up_tokens.events.SignUpUserPayload", "user_id"),
        # modules.followers.events
        ("modules.followers.events.FollowerAcceptedPayload", "accepter_user_id"),
        ("modules.followers.events.FollowerAcceptedPayload", "requester_user_id"),
        ("modules.followers.events.FollowerRequestRemovedPayload", "requester_user_id"),
        ("modules.followers.events.FollowerRequestRemovedPayload", "target_user_id"),
        ("modules.followers.events.FollowerRequestedPayload", "requester_user_id"),
        ("modules.followers.events.FollowerRequestedPayload", "target_user_id"),
        # modules.garmin.events
        ("modules.garmin.events.SyncRequestedPayload", "user_id"),
        # modules.strava.events
        ("modules.strava.events.SyncRequestedPayload", "user_id"),
        # modules.users.users.events
        ("modules.users.users.events.AdminPromotedPayload", "user_id"),
        ("modules.users.users.events.AdminPromotedPayload", "admin_user_id"),
        ("modules.users.users.events.DeletionRequestedPayload", "user_id"),
        # modules.users.users_profile.events
        ("modules.users.users_profile.events.ProfileExportRequestedPayload", "user_id"),
        ("modules.users.users_profile.events.ProfileImportRequestedPayload", "user_id"),
    }
)

_FIX_THE_LIST = (
    "Add the field to PAYLOAD_ID_REWRITES in the revision that converts it, and delete it from _NOT_YET_REWRITTEN "
    "in tests/migrations/test_payload_id_rewrites.py."
)


def _import_packages() -> None:
    for package_name in _PACKAGES:
        package = importlib.import_module(package_name)
        for module in pkgutil.walk_packages(package.__path__, prefix=f"{package_name}."):
            importlib.import_module(module.name)


def _subclasses(base: type) -> set[type]:
    found: set[type] = set()
    for subclass in base.__subclasses__():
        found.add(subclass)
        found |= _subclasses(subclass)
    return found


def _dotted(cls: type) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


def _annotation_types(annotation: object) -> set[object]:
    """Flatten an annotation into every type it names, through unions, generics and ``Annotated``."""
    found: set[object] = {annotation}
    if isinstance(annotation, types.UnionType) or typing.get_origin(annotation) is not None:
        for argument in typing.get_args(annotation):
            found |= _annotation_types(argument)
    return found


def _holds(annotation: object, wanted: type) -> bool:
    return wanted in _annotation_types(annotation)


def _is_id_field_name(name: str) -> bool:
    return name == "id" or name.endswith(("_id", "_ids"))


def _integer_id_fields(classes: Iterable[type[BaseModel]]) -> set[tuple[str, str]]:
    """Return the integer id fields of the classes defined in an owned package, as (dotted class, field)."""
    found: set[tuple[str, str]] = set()
    for cls in classes:
        if not cls.__module__.startswith(_OWNED_PREFIXES):
            continue
        for name, field in cls.model_fields.items():
            if _is_id_field_name(name) and _holds(field.annotation, int):
                found.add((_dotted(cls), name))
    return found


def _discovered_integer_id_fields() -> set[tuple[str, str]]:
    _import_packages()
    return _integer_id_fields(_subclasses(VersionedPayload))


def _declared_entries() -> list[tuple[str, str, tuple[str, ...], str]]:
    entries: list[tuple[str, str, tuple[str, ...], str]] = []
    for revision in alembic_chain.script_directory().walk_revisions():
        entries.extend(getattr(revision.module, "PAYLOAD_ID_REWRITES", ()))
        entries.extend(getattr(revision.module, "AUDIT_DETAIL_ID_CHANGES", ()))
    return entries


def _declared_pairs() -> set[tuple[str, str]]:
    return {(payload_class, field) for payload_class, field, _stored_under, _parent_table in _declared_entries()}


def _stored_under() -> dict[str, set[tuple[str, ...]]]:
    """Map each declared class to the event types it is stored under; a class may be declared by several revisions."""
    stored_under: dict[str, set[tuple[str, ...]]] = {}
    for payload_class, _field, event_types, _parent in _declared_entries():
        stored_under.setdefault(payload_class, set()).add(event_types)
    return stored_under


def _resolve(dotted_class: str) -> type | None:
    module_name, _, class_name = dotted_class.rpartition(".")
    try:
        return getattr(importlib.import_module(module_name), class_name, None)
    except ImportError:
        return None


def _format(pairs: set[tuple[str, str]]) -> str:
    return "\n".join(f"  {payload_class} {field}" for payload_class, field in sorted(pairs))


def test_the_integer_id_filter_reports_only_owned_integer_id_fields() -> None:
    class Example(BaseModel):
        thing_id: int
        name: str
        other_id: uuid.UUID

    Example.__module__ = "modules.example.events"

    class Foreign(BaseModel):
        thing_id: int

    assert _integer_id_fields([Example, Foreign]) == {(_dotted(Example), "thing_id")}


def test_every_integer_id_field_is_declared_or_listed() -> None:
    uncovered = _discovered_integer_id_fields() - _declared_pairs() - _NOT_YET_REWRITTEN
    assert not uncovered, (
        f"Payload integer id fields that no revision rewrites and that are not listed:\n{_format(uncovered)}\n"
        "Declare them in PAYLOAD_ID_REWRITES of the revision that converts them, or, when that revision is "
        "not written yet, add them to _NOT_YET_REWRITTEN in tests/migrations/test_payload_id_rewrites.py."
    )


def test_every_baseline_field_is_declared_or_listed() -> None:
    uncovered = _BASELINE - _declared_pairs() - _NOT_YET_REWRITTEN
    assert not uncovered, (
        f"Baseline payload id fields that are neither declared nor listed in _NOT_YET_REWRITTEN:\n{_format(uncovered)}\n"
        "Declare them in PAYLOAD_ID_REWRITES of the revision that converts them; do not only delete them from the list."
    )


def test_not_yet_rewritten_does_not_overlap_the_declared_entries() -> None:
    overlap = _NOT_YET_REWRITTEN & _declared_pairs()
    assert not overlap, (
        f"Declared by a revision and still listed in _NOT_YET_REWRITTEN:\n{_format(overlap)}\n{_FIX_THE_LIST}"
    )


def test_not_yet_rewritten_is_part_of_the_baseline() -> None:
    extra = _NOT_YET_REWRITTEN - _BASELINE
    assert not extra, f"_NOT_YET_REWRITTEN may only shrink; entries outside _BASELINE:\n{_format(extra)}"


def test_every_not_yet_rewritten_entry_is_still_an_integer_id_field() -> None:
    stale = _NOT_YET_REWRITTEN - _discovered_integer_id_fields() - _declared_pairs()
    assert not stale, (
        f"_NOT_YET_REWRITTEN entries that are no longer integer id fields and that no revision declares:\n"
        f"{_format(stale)}\n"
        "Declare them in PAYLOAD_ID_REWRITES of the revision that converts them, then delete them from "
        "_NOT_YET_REWRITTEN in tests/migrations/test_payload_id_rewrites.py."
    )


@pytest.mark.parametrize("entry", _declared_entries(), ids=lambda entry: f"{entry[0]}.{entry[1]}")
def test_every_declared_entry_names_a_uuid_field(entry: tuple[str, str, tuple[str, ...], str]) -> None:
    payload_class, field, stored_under, parent_table = entry
    _import_packages()
    cls = _resolve(payload_class)
    assert cls is not None, f"PAYLOAD_ID_REWRITES names {payload_class}, which does not exist."
    assert isinstance(cls, type) and issubclass(cls, VersionedPayload), f"{payload_class} is not a VersionedPayload."
    assert field in cls.model_fields, f"PAYLOAD_ID_REWRITES names {payload_class}.{field}, which does not exist."
    annotation = cls.model_fields[field].annotation
    assert not _holds(annotation, int), f"{payload_class}.{field} is declared as rewritten but still holds int."
    assert _holds(annotation, uuid.UUID), f"{payload_class}.{field} is declared as rewritten but is not a uuid.UUID."
    assert stored_under and all(isinstance(name, str) for name in stored_under)
    assert parent_table in Base.metadata.tables, f"{payload_class}.{field} names the unknown table {parent_table}."


def test_idp_revision_event_types_match_the_application_constants() -> None:
    from modules.auth.account_security import events as account_security_events
    from modules.auth.identity_providers import events as idp_events

    stored_under = _stored_under()

    assert stored_under["modules.auth.identity_providers.events.IdpLinkedPayload"] == {(idp_events.IDP_LINKED,)}
    assert stored_under["modules.auth.account_security.events.AccountSecurityChangedPayload"] == {
        (account_security_events.ACCOUNT_SECURITY_CHANGED,)
    }


def test_activity_revision_event_types_match_the_application_constants() -> None:
    from modules.activities.activity import events as activity_events

    stored_under = _stored_under()

    assert stored_under["modules.activities.activity.events.ActivityCreatedPayload"] == {
        (activity_events.ACTIVITY_CREATED,)
    }
    assert stored_under["modules.activities.activity.events.ActivityUpdatedPayload"] == {
        (activity_events.ACTIVITY_UPDATED,)
    }
    assert stored_under["modules.activities.activity.events.ActivityDeletedPayload"] == {
        (activity_events.ACTIVITY_DELETED,)
    }
    assert stored_under["modules.activities.activity.events.VisibilityEditRequestedPayload"] == {
        (activity_events.ACTIVITIES_VISIBILITY_EDIT_REQUESTED,)
    }


def test_users_revision_event_types_match_the_application_constants() -> None:
    from modules.activities.activity import events as activity_events
    from modules.auth.account_security import events as account_security_events
    from modules.auth.authentication import events as authentication_events
    from modules.auth.identity_providers import events as idp_events
    from modules.auth.known_devices import events as known_devices_events
    from modules.auth.mfa_backup_codes import events as backup_codes_events
    from modules.auth.password_reset_tokens import events as password_reset_events
    from modules.auth.sessions import events as sessions_events
    from modules.auth.sign_up_tokens import events as sign_up_events
    from modules.followers import events as followers_events
    from modules.garmin import events as garmin_events
    from modules.strava import events as strava_events
    from modules.users.users import events as users_events
    from modules.users.users_profile import events as profile_events

    expected: dict[str, set[tuple[str, ...]]] = {
        "modules.activities.activity.events.ActivityCreatedPayload": {(activity_events.ACTIVITY_CREATED,)},
        "modules.activities.activity.events.ActivityUpdatedPayload": {(activity_events.ACTIVITY_UPDATED,)},
        "modules.activities.activity.events.VisibilityEditRequestedPayload": {
            (activity_events.ACTIVITIES_VISIBILITY_EDIT_REQUESTED,)
        },
        "modules.auth.account_security.events.AccountSecurityChangedPayload": {
            (account_security_events.ACCOUNT_SECURITY_CHANGED,)
        },
        "modules.auth.account_security.events.StepUpSessionEndedPayload": {
            (account_security_events.STEP_UP_SESSION_ENDED,)
        },
        "modules.auth.account_security.events.StepUpLockedPayload": {(account_security_events.STEP_UP_LOCKED,)},
        "modules.auth.authentication.events.AccountLockedPayload": {(authentication_events.ACCOUNT_LOCKED,)},
        "modules.auth.authentication.events.MfaLockedPayload": {(authentication_events.MFA_LOCKED,)},
        "modules.auth.authentication.events.RefreshReuseDetectedPayload": {
            (authentication_events.REFRESH_REUSE_DETECTED,)
        },
        "modules.auth.identity_providers.events.IdpLinkedPayload": {(idp_events.IDP_LINKED,)},
        "modules.auth.identity_providers.events.IdpTokenRefreshPayload": {(idp_events.IDP_TOKEN_REFRESH_REQUESTED,)},
        "modules.auth.known_devices.events.NewDeviceSignInPayload": {(known_devices_events.NEW_DEVICE_SIGN_IN,)},
        "modules.auth.mfa_backup_codes.events.BackupCodeUsedPayload": {(backup_codes_events.BACKUP_CODE_USED,)},
        "modules.auth.password_reset_tokens.events.PasswordResetRequestedPayload": {
            (password_reset_events.PASSWORD_RESET_REQUESTED,)
        },
        "modules.auth.password_reset_tokens.events.PasswordResetCompletedPayload": {
            (password_reset_events.PASSWORD_RESET_COMPLETED,)
        },
        "modules.auth.sessions.events.SessionsRevokedPayload": {(sessions_events.SESSIONS_REVOKED,)},
        "modules.auth.sign_up_tokens.events.SignUpUserPayload": {
            (
                sign_up_events.SIGN_UP_VERIFICATION_REQUESTED,
                sign_up_events.ADMIN_INVITATION_REQUESTED,
                sign_up_events.EMAIL_CHANGE_VERIFICATION_REQUESTED,
                sign_up_events.SIGN_UP_APPROVED,
                sign_up_events.SIGN_UP_EXISTING_ACCOUNT,
                sign_up_events.EMAIL_CHANGE_REQUESTED,
                sign_up_events.EMAIL_CHANGE_ADDRESS_TAKEN,
            )
        },
        "modules.auth.sign_up_tokens.events.EmailChangedPayload": {(sign_up_events.EMAIL_CHANGED,)},
        "modules.auth.sign_up_tokens.events.SignUpApprovalRequestedPayload": {
            (sign_up_events.SIGN_UP_APPROVAL_REQUESTED,)
        },
        "modules.followers.events.FollowerRequestedPayload": {(followers_events.FOLLOWER_REQUESTED,)},
        "modules.followers.events.FollowerAcceptedPayload": {(followers_events.FOLLOWER_ACCEPTED,)},
        "modules.followers.events.FollowerRequestRemovedPayload": {(followers_events.FOLLOWER_REQUEST_REMOVED,)},
        "modules.garmin.events.SyncRequestedPayload": {(garmin_events.GARMIN_SYNC_REQUESTED,)},
        "modules.strava.events.SyncRequestedPayload": {(strava_events.STRAVA_SYNC_REQUESTED,)},
        "modules.users.users.events.DeletionRequestedPayload": {(users_events.USERS_DELETION_REQUESTED,)},
        "modules.users.users.events.AdminPromotedPayload": {(users_events.USERS_ADMIN_PROMOTED,)},
        "modules.users.users_profile.events.ProfileImportRequestedPayload": {
            (profile_events.USERS_PROFILE_IMPORT_REQUESTED,)
        },
        "modules.users.users_profile.events.ProfileExportRequestedPayload": {
            (profile_events.USERS_PROFILE_EXPORT_REQUESTED,)
        },
    }
    stored_under = _stored_under()

    assert {payload_class: stored_under[payload_class] for payload_class in expected} == expected
