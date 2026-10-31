# Pull requests

- **PR title**: must itself be a valid Conventional Commit header (same rules and whitelist). If the PR
  has a single commit, reuse its header. If it has several, write one header that summarizes the whole
  change, with the type of the most significant change.
- **Commits in the PR**: every non-merge commit subject on the branch is validated too, so make sure each
  one complies before pushing (`git log --no-merges --format=%s origin/master..HEAD`). Fix offenders
  with an interactive-free approach (e.g. `git commit --amend` for the last commit) or ask the user.
- **PR description**: fill in `.github/PULL_REQUEST_TEMPLATE.md`:
  - *What does this PR do?* - clear description of the change and why.
  - *Related issue* - `Closes #XYZ` so it auto-closes; required for anything beyond a small fix/typo.
  - *Type of change* - tick the matching boxes.
  - *Checklist* - tick only what is true (single concern, ~300 lines max excluding lockfiles/migrations/
    generated code, tests and docs updated, Conventional Commits followed).
  - *Notes for the reviewer* - tricky areas, alternatives considered, screenshots.
- The project is in a **feature freeze**: prefer framing and scoping PRs as bug fixes, security fixes,
  refactors, tests, docs or maintenance. A `feat` PR needs prior discussion linked in the description.
- Base branch is `master`. Create the PR with `gh pr create --title "<header>" --body "<filled template>"`.
  Pushing and opening a PR are outward-facing: only do so when the user asked.
