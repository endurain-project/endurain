---
name: conventional-commits
description: Write commit messages, commit titles and pull request titles/descriptions for Endurain following Conventional Commits. Use whenever creating a git commit, amending or squashing commits, naming a branch's PR, or opening/updating a pull request.
---

# Conventional Commits for Endurain

Every commit subject and every PR title is validated in CI by `.github/workflows/conventional-commits.yml`
(script: `.github/scripts/check_conventional_commits.py`). A non-compliant title blocks the PR, so get it
right the first time.

## Header format

```
<type>(<scope>)!: <description>
```

- `(<scope>)` and `!` are optional.
- A single space after the colon is required.
- Only the first line is validated; the body and footers are free-form.

### Allowed types (project whitelist)

| Type | Use for |
| --- | --- |
| `feat` | New user-facing capability |
| `fix` | Bug fix (including security fixes) |
| `docs` | Documentation only (`docs/`, README, comments) |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `perf` | Performance improvement |
| `test` | Adding or correcting tests |
| `build` | Build system, dependencies, Dockerfiles |
| `ci` | CI configuration and workflows |
| `chore` | Maintenance that fits nowhere else (version bumps, housekeeping) |
| `style` | Formatting only, no logic change |
| `revert` | Reverting a previous commit |

Any other type (e.g. `feature`, `bugfix`, `security`, `deps`) fails validation.

### Scope

Optional, any non-empty string without parentheses. Prefer the module or area touched, matching what
recent history uses: `activities`, `auth`, `garmin`, `strava`, `users`, `migrations`, `scheduler`,
`frontend`, `docs`, `api`, `deps`. Omit the scope when the change spans many areas.

### Description

- Imperative mood, describes what the change does: `add GPX max speed parsing`, not `added` / `adds`.
- Specific, not vague (`fix: handle multi-segment GPX distance`, not `fix: bug`).
- No trailing period; keep the header readable (aim for ~72 characters or fewer).

### Breaking changes

Mark with `!` after the type/scope (`refactor(api)!: rename Activity.distance to total_distance`) and/or a
`BREAKING CHANGE: <explanation>` footer in the body. Use whenever an API, config, env var, or DB behavior
changes in a way that requires action from users or integrators.

## Examples

```
feat: add GPX max speed parsing
fix(garmin): handle multi-segment GPX distance correctly
docs: update development instructions
test(activities): add regression test for GPX segment handling
refactor(api)!: rename Activity.distance to total_distance
chore: bump version to 0.19.3 and update dependencies
```

## Committing

1. Inspect the change first: `git status`, `git diff --staged` (and `git log --format=%s -10` to match
   recent style and scopes).
2. Choose the type by the *primary intent* of the change. If a diff mixes unrelated concerns, prefer
   splitting into separate commits, one concern each.
3. Write the header per the rules above. Add a body (blank line after the header) only when the *why*
   isn't obvious; wrap at ~72 columns.
4. Reference issues in the body/footer, e.g. `Closes #123` or `Refs #123`.
5. Do not use `--no-verify`, and do not rewrite or force-push shared history unless explicitly asked.
6. Include any attribution/co-author trailer that the session instructs you to add.

Optionally self-check before committing:

```bash
python3 .github/scripts/check_conventional_commits.py "feat(scope): your header"
```

## Pull requests

Opening or updating a PR (title, template, feature freeze, `gh pr create`): read `references/pull-requests.md`.
A PR title must itself be a valid header; every non-merge commit subject on the branch is validated too.
