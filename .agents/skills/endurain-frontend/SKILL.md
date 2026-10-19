---
name: endurain-frontend
description: Endurain frontend conventions (Vue 3, TypeScript, Tailwind v4, shadcn-vue, TanStack Query). Use when adding or changing code in frontend/src or its tests.
---

# Endurain frontend

Design source of truth: `docs/developer-guide/brand-and-ux-guidelines.md` and the tokens in `frontend/src/assets/main.css`.
Repo-wide rules are in `AGENTS.md`.

## Core rules (always apply)

- `<script setup lang="ts">`; infer types where obvious; no implicit `any`.
- Code lives in `src/features/<feature>/` (`components/`, `composables/`, `services/`, `stores/`, `views/`, `types.ts`); promote to shared `src/` only when reused across features.
- Server state goes through TanStack Query; client state only in Pinia (never tokens or server-owned data).
- HTTP goes through `src/services/http.ts`; never call `fetch` in a component.
- Query keys come from `src/services/queryKeys.ts`; writes use `useInvalidatingMutation`.
- API DTOs derive from the generated client (`src/types/api.generated.ts`, never hand-edited) via `Schemas`.
- Compose `src/components/ui/` primitives; style with Tailwind semantic tokens and `cn()`, no hex values or arbitrary sizes.
- Every user-facing string goes through vue-i18n; English is the source of truth.
- Never use `v-html` on user data; render through `SafeHtml.vue`.
- Branch on `HttpError.type` (the problem URN), not on `status` alone.
- KISS, YAGNI, DRY: reuse an existing composable, service, query key or `ui/` primitive first; no prop, store, abstraction or option without a current use; extract on the third repetition.
- Interactive elements are keyboard reachable, labelled, and have loading, empty and error states.

## Read on demand

| When you are | Read |
| --- | --- |
| Adding a feature, query, mutation, store, route or form | `references/architecture.md` |
| Building or styling UI, dark mode, accessibility | `references/ui.md` |
| Adding or changing text, locales | `references/i18n.md` |
| Writing JSDoc or tests | `references/docs-and-tests.md` |

## Before finishing

```bash
cd frontend
npm run check        # type-check + lint:check + format:check + test
npm run gen:api      # only after backend API changes
```

## Repo hygiene

- Do only what was asked; prefer existing composables and primitives over new ones.
- Commit messages and PR titles: use the `conventional-commits` skill.
- Backend work: use the `endurain-backend` skill.
