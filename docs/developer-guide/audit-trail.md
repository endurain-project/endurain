# Audit trail

This page says which actions Endurain records in the audit trail, how a package declares and writes them, and what CI enforces. For retention, tamper evidence and signing, see [Audit trail](../getting-started/advanced-setup.md#audit-trail) in the setup guide.

## What the trail is for

The trail is the append-only record of security-relevant actions: who did what, to what, from where, and how it ended. It is not a log of everything users do.

It differs from [domain events](events-and-subscribers.md). A row is written synchronously, on the caller's own session, so the change and its row commit or roll back together. No bus, outbox or Redis is involved, so it behaves the same with and without `JOBS_ENABLED`. It also records refusals (`denied`) and failures, which no domain event describes.

## What must be audited

An action that falls in one of these categories gets an audit action and a row.

| Category | Audit | Examples |
| -------- | ----- | -------- |
| Authentication and credentials | Sign-ins (successful and refused), sign-outs, lockouts, refused refreshes and API keys, requests refused because the account must enrol MFA (once per credential per day), password, MFA, backup code and API key changes, sessions signed out, password reset requests | `auth.session.login`, `auth.lockout.apply`, `auth.backup_codes.use`, `auth.password_reset.request`, `auth.mfa_enrolment.denied` |
| Identity and account lifecycle | Accounts created, confirmed, approved, changed or deleted; refused first-run onboarding attempts; email changes; sign-in providers linked or unlinked | `users.user.create`, `auth.onboarding.refuse`, `auth.sign_up.confirm`, `users.email.change`, `auth.identity_link.link` |
| Admin actions | Anything an administrator does to another user or to server settings | `users.user.update`, `auth.identity_provider.update`, `server_settings.settings.update`, `server_settings.logs.clear` |
| Integrations | Linking or unlinking a third-party account, storing its secrets | `strava.account.link`, `garmin.account.revoke`, `strava.client.update` |
| Data leaving or entering the system | Exports, downloads, imports | `users.profile_export.download`, `users.profile_import.request`, `activities.import.request` |
| Who can see data | Privacy and visibility changes, followers | `users.privacy.update`, `activities.visibility.update`, `followers.follow.accept` |

These are not audited:

| Not audited | Why |
| ----------- | --- |
| Ordinary personal records: health entries, gear, goals, notifications, media, single activity uploads and deletes | They are the user's own data and change constantly; the trail would drown the rows that matter. |
| Routine syncs, token refreshes and housekeeping | Automatic and high volume. A refresh-token reuse is the exception: it is a security event. |
| Rate-limit 429 responses | Noise, and an attacker controls the volume. |
| Step-up success | The sensitive action that follows is audited. A failed step-up is audited. |
| MFA setup | It only stores a pending secret; enabling is audited. |

## Declaring an action

A package declares its actions in `audit_actions.py`, a composition surface in [Module structure](module-structure.md). The file holds the `details` models, the `AuditAction` constants and an `ACTIONS` tuple. The package's `RuntimeModule` in `backend/app/module_registry.py` passes `ACTIONS` as `audit_actions`, and `configure_audit()` registers every module's actions in the audit catalog. The package's own services write the rows.

```python
class UserUpdateDetails(VersionedPayload):
    model_config = ConfigDict(extra="forbid")

    SCHEMA_VERSION: ClassVar[int] = 1

    changed_fields: list[str]


USER_UPDATE = jasil_audit.AuditAction(
    id="users.user.update",
    category=jasil_audit.Category.ADMIN,
    severity=jasil_audit.Severity.HIGH,
    description_key="audit.users.user.update",
    description_default="An administrator changed an account",
    details_model=UserUpdateDetails,
)

ACTIONS: tuple[jasil_audit.AuditAction, ...] = (USER_UPDATE,)
```

| Field | Rule |
| ----- | ---- |
| `id` | `<top-level module>.<resource>.<verb>`: three lower-case snake_case segments. The first is the top-level module under `app/modules` (`auth`, `users`, `strava`). |
| `category`, `severity` | `jasil_audit.Category` (`authentication`, `credential`, `authorization`, `identity`, `admin`, `data_change`, `data_transfer`, `integration`, `system`) and `jasil_audit.Severity` (`info` to `high`). |
| `description_key` | `audit.<id>`. |
| `description_default` | A short past-tense English sentence. |
| `details_model` | A `VersionedPayload`; omit it for an action with no details. |

## Writing a row

| Situation | Call |
| --------- | ---- |
| The change succeeds | `jasil_audit.stage(db, ACTION, ...)` in the transaction that commits the change, before the commit |
| A refusal or failure, where the transaction rolls back or there is none | `jasil_audit.record_detached(ACTION, outcome=..., ...)` |

- `stage` only adds the row to the session; it never commits. Stage nothing when nothing changed, such as an edit that sets the same values.
- `record_detached` writes in its own short transaction and never raises; a failure is logged and counted instead.
- `Outcome.DENIED` is a request refused by authorization or policy. `Outcome.FAILURE` is an allowed request that did not succeed, such as a bad token or an invalid code.
- Write exactly one row per change. Before adding a call, check the callers so a service and the service it calls do not both record the same change.
- Pass `target_type`, `target_id` and `target_owner_id` as strings; the owner is the user the data belongs to.

## Who is acting

The provider `audit_context_from_request` in `app/modules/auth/dependencies.py` is installed by `configure_audit()` and read when a row is written. Inside an HTTP request the actor is the principal an auth dependency resolved, with the client address and user agent. It is anonymous until a dependency has run. Outside a request the actor is `SYSTEM`.

A job never has the request:

- Record what the user asked for in the request that queues the job, in the transaction that queues it.
- A job may record its own outcome. Its rows name `SYSTEM` as the actor, and `target_owner_id` names the user. The request id still reaches them: `BoundedPool` jobs run under a copy of the submitter's context without the request (`app/core/local_pool.py`, `app/core/request_context.py`).
- This is the same with and without `JOBS_ENABLED`.

Use `jasil_audit.audit_context(...)` only where the actor is known but not yet on the request, such as a sign-in, where the user has no principal until the tokens are issued (`app/modules/auth/authentication/service.py`).

## What goes in `details`

Ids, counts, enumerated values and the names of changed fields. Never a field's value, an email, a username, a name, a token, a code, a password, a secret, a URL or a file name.

Every `details` model sets `extra="forbid"` and a `SCHEMA_VERSION`. A key the model does not declare is rejected, so a value cannot leak by accident. Assert the exact `details` in the test.

## Keeping ids stable

Rows outlive the code.

- Never rename or delete an action id. When nothing writes an action any more, set `deprecated=True`.
- When a `details` model changes (a new field or enum value), raise its `SCHEMA_VERSION`.

## Which package writes the row

The package that owns the change writes it. A sibling package of the same top-level module may reuse an action: `app/modules/auth/dependencies.py` writes `authentication` actions. Never import another top-level module's `audit_actions.py`.

## Testing

Write the test first. `jasil.testing.capture_audit()` collects every row staged or recorded inside the block, with no database. `tests/conftest.py` calls `configure_audit()` with audit writes disabled, so the catalog is registered and a test needs no audit tables.

```python
with jasil_testing.capture_audit() as audit:
    users_service.create_user(...)

entry = audit.assert_audited(
    users_audit_actions.USER_CREATE.id, target_type="user", target_id=str(user.id), target_owner_id=str(user.id)
)
assert entry.details == {"access_type": "regular"}
```

- `assert_audited(action_id, outcome=..., target_id=..., **fields)` returns the first matching entry; `matching(...)` returns all of them; `assert_not_audited(action_id)` covers a no-op.
- Cover the success, the denied outcome and the failure outcome, where the action has them.
- Assert `details` exactly, which proves no value leaks.
- A capture lists a row when it is staged, even if its transaction rolls back later. To test the rollback, assert on the database.

## What CI enforces

`backend/tests/architecture/test_audit_trail.py`:

| Test | Fails when |
| ---- | ---------- |
| `test_every_audit_actions_file_is_registered_by_a_runtime_module` | An `audit_actions.py` has an `ACTIONS` tuple that no `RuntimeModule` in `module_registry.py` registers. |
| `test_every_action_is_written_by_application_code` | A non-deprecated action is never referenced by application code outside the composition root. |
| `test_an_action_id_starts_with_its_top_level_module` | An id's first segment is not the top-level module its file lives in. |
| `test_every_action_is_declared_in_its_modules_actions_tuple` | An `AuditAction` constant is not in its module's `ACTIONS`. |
| `test_every_write_route_is_classified` | A `POST`, `PUT`, `PATCH` or `DELETE` route is in none of the tables below. |
| `test_every_entry_names_a_write_route_once` | A table entry names a route that no longer exists, or a route is classified twice. |
| `test_a_mapped_route_names_declared_actions` | A mapped route names an action id no `audit_actions.py` declares, or none. |

Every write route is classified in the same file, so adding one is a decision, not an oversight:

- `_AUDITED_WRITES` maps the route to every action it records, in the request or in the job it queues for what was asked. A refusal by the scope check or the API-key check is common to all routes and is not listed.
- `_UNAUDITED_WRITES` gives the reason a route records nothing, using a shared reason such as `_PERSONAL` or `_ROUTINE` where one fits.
- `_UNAUDITED_ROUTERS` exempts a whole router file whose every write is a personal record.

The tables cannot see whether the service really writes the row: the module's own `capture_audit` tests do.

Review covers the rest: what to audit, the contents of `details`, one row per change and the right call for the situation.
