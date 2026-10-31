---
name: skill-authoring
description: How to create or edit skills in this repo. Use when adding, splitting, trimming or reviewing a file under .agents/skills.
---

# Authoring skills for Endurain

Goal: the least text loaded per task that still prevents the mistakes the skill exists for.

## Where skills live

- Source of truth: `.agents/skills/<name>/SKILL.md`.
- Expose to Claude Code with a relative symlink: `ln -s ../../.agents/skills/<name> .claude/skills/<name>`.
- Name is kebab-case and matches the folder.

## What is paid for, and when

| Part | Cost |
| --- | --- |
| Frontmatter `description` | Every session, whether used or not |
| `SKILL.md` body | Each time the skill is invoked |
| `references/*.md` | Only when the body says to read one and it does |

## Rules

1. **Description:** one sentence of what plus one sentence of when.
   - No keyword lists; the trigger is the task, not synonyms.
   - Keep it under about 200 characters.
2. **Body:** only rules that apply to every use of the skill, ideally under 60 lines.
3. **References:** put situational detail in `references/<topic>.md`, one topic per file.
   - Link each from a "read when" table in `SKILL.md`; a reference nothing points to never loads.
   - Do not nest references from references.
4. **Do not duplicate a guide.** If `docs/` already states a rule, summarize it in one line and point to the doc; say which wins on conflict.
5. **Rules, not history.** Leave out incident stories, rationale essays and changelog; keep the rule and, if it is non-obvious, a clause of why.
6. **Imperative and checkable.** "Run `uv run ruff check .`" beats "ensure code quality".
7. **Format:** one sentence per line (clean diffs), tables for lookups, code blocks for commands only.
8. **One concern per skill.** Split by trigger, not by size; do not create several skills that always fire together.
9. **No secrets or personal paths;** commands are repo-relative.
10. **KISS, YAGNI, DRY:** no rule, reference or section for a hypothetical case; state each rule once and link to it.

## Splitting an existing skill

1. List what applies to every invocation; that stays in `SKILL.md`.
2. Group the rest by the task that needs it; one reference file per group.
3. Add the "read when" table and keep the always-apply rules above it.
4. Check nothing was lost: every rule is in exactly one place.

## Before finishing

- `wc -l` the body and each reference; reconsider anything over about 100 lines.
- Confirm the symlink resolves: `ls -L .claude/skills/<name>/SKILL.md`.
- Invoke the skill on a real task and confirm it reads the reference it should.
- Skills under `.claude/` and `.agents/` may be untracked; add them to git only when asked.
