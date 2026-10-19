# Documentation comments and tests

## JSDoc

- Standard `/** ... */` blocks with a one-line summary, then `@param`, `@returns`, `@throws` (always, even when obvious).
- No examples and no extended explanations; describe what, not how.
- Interfaces: `@property` per member, one sentence each.
- Constants: a single-line `/** ... */`.
- Document public members; skip private ones unless needed.

## Tests (Vitest)

- Location: `src/__tests__/` (shared fixtures in `src/__tests__/fixtures/`).
- Run once: `npm run test`; watch: `npm run test:unit`; coverage gate: `npm run test:coverage`.
- Test composables and services with mocked `apiFetch`; test components with `@vue/test-utils`.
- Cover loading, error and empty states, not only the happy path.
- Prefer fixtures typed from the generated `Schemas`, as in `__tests__/fixtures/`, so contract drift fails type-check.

## Pre-commit gate

- `npm run check` (type-check, lint:check, format:check, test) is the CI gate.
- Run `npm run format` and `npm run lint` to auto-fix.
