# Module structure reference

The guide, `docs/developer-guide/module-structure.md`, is the only statement of the rules. This file
points at its sections and holds the few lookups that are not in it.

## Where each rule lives

| Question | Guide section |
| --- | --- |
| What does each file name mean, and who may import it? | File roles, Visibility |
| May this file import that one? | Allowed-import matrix |
| Where does a commit, rollback or event belong? | Layering inside a module, Transaction ownership |
| Query, event, contributor or seam? | Choosing a coupling mechanism |
| What do I name an alias, a publisher, a schema, a collection? | Conventions that look like drift |
| What do I add for a new module? | Adding a module (the `convert-module` skill covers an existing one) |
| What is enforced, and where? | Enforcement |

## Lookups not in the guide

- Activity children return `ingestion_contributor`, `profile_contributor` and `profile_global_contributor` from `integration_service`.
  Plain child collections (rows hanging off one activity) build them with `activities_contributors.child_ingestion_contributor` / `child_profile_contributor`.
  `app/module_registry.py` installs them in `modules.activities.contributor_registry`.
- Mirror the module tree under `backend/tests/`.
- Auth boundary: use only `modules.auth.dependencies` and `modules.auth.identity_service.IdentityService`; never `modules.auth._internal` or any `modules.auth.*.crud`.
  `auth` publishes `identity_service.py`, not `integration_service.py`; do not copy that.
