# Endurain frontend (v2)

The next-generation Endurain web client — a ground-up rewrite of `frontend`
following the strangler-fig plan in `devdocs/UX_INCREMENTAL_MIGRATION_PLAN.md`.

## Stack

- **Vue 3** (`<script setup>`) + **TypeScript**
- **Vite** build, **Vitest** unit tests
- **Pinia** (setup stores) for client state, **TanStack Query** for server state
- **vue-router**, **vue-i18n** (lazy locales)
- **Tailwind CSS v4** (`@theme` tokens in `src/assets/main.css`) + **shadcn-vue** / **reka-ui** primitives

Recommended editor: VS Code + the [Vue (Official)](https://marketplace.visualstudio.com/items?itemName=Vue.volar) extension.

## Getting started

```sh
npm install
npm run dev        # dev server with hot reload
```

## Commands

| Command | Purpose |
| --- | --- |
| `npm run dev` | Start the dev server |
| `npm run build` | Type-check + production build |
| `npm run test` | Run unit tests once |
| `npm run test:unit` | Run unit tests in watch mode |
| `npm run test:coverage` | Run tests with the coverage gate |
| `npm run type-check` | `vue-tsc` type check |
| `npm run lint` / `npm run lint:check` | oxlint + ESLint (fix / check) |
| `npm run format` / `npm run format:check` | Prettier (write / check) |
| `npm run check` | type-check + lint + format + test (run before pushing) |
| `npm run gen:api` | Regenerate the typed API client (see below) |

CI (`.github/workflows/lint-frontend.yml`) runs format, lint, type-check, and
the coverage-gated tests on every PR touching `frontend`.

## Typed API client

`src/types/api.generated.ts` is generated from the backend's OpenAPI schema and
**committed** so the frontend builds without the backend. Derive API-boundary
DTOs from it via the `Schemas` helper in `src/types/index.ts` so a backend
contract change surfaces as a TypeScript error.

Regenerate after backend API changes:

```sh
# 1. Export the schema from the backend (no DB required)
python ../../backend/scripts/export_openapi.py openapi.json
# 2. Generate the TypeScript client
npm run gen:api
```

`.github/workflows/openapi-types-drift.yml` regenerates the client in CI and
fails if the committed copy is stale, so it can never drift from the backend.
The intermediate `openapi.json` is gitignored.

## Conventions

- Read deployment config from the app config / public server settings, never
  from `import.meta.env` in views.
- Muted text uses `text-muted-foreground`; `bg-muted` is a surface
  (shadcn-conventional). Brand tokens live in `src/assets/main.css`.
