# Frontend architecture

## Feature module layout

- `src/features/<feature>/components|composables|services|stores|views|utils` plus `types.ts`.
- Reference implementations: `features/auth` (full module), `features/health` (TanStack CRUD with dialogs), `features/followers` (small module).
- A feature does not import another feature's internals; share through `src/composables`, `src/components`, `src/utils` or `src/types`.

## Server state (the canonical pattern)

1. Service function in `features/<f>/services/<domain>.ts`: `apiFetch` plus a mapper from the DTO to a clean model.
2. Key factory entry in `src/services/queryKeys.ts`: `all()` is the broad prefix, `list(filters)` and `detail(id)` narrow from it.
3. Composable `useXxxQuery()` calling `useQuery` with the service function and the key factory.
4. View or component consumes the composable; it never calls `fetch`/`apiFetch` and never copies server data into Pinia.

Writes:
- Use `useInvalidatingMutation` so the affected domain's keys are invalidated.
- Optimistic updates snapshot in `onMutate`, roll back in `onError`, invalidate in `onSettled` (reference: `useMarkNotificationReadMutation`).
- Seed or invalidate `queryKeys.currentUser()` when a profile change must propagate everywhere.

## Typed API client

- `src/types/api.generated.ts` is generated from the backend OpenAPI schema and committed.
- Regenerate with `npm run gen:api` (set `ENDURAIN_OPENAPI_SOURCE` to a backend `openapi.json` or URL) after any backend API change.
- Derive DTO types with `Schemas` in `src/types/index.ts` so contract changes become compile errors.
- Review the generated diff; an unexpected change means the backend contract moved.

## Errors

- `apiFetch` throws `HttpError(status, statusText, detail, type, requestId)`.
- Branch on `error.type` (e.g. `urn:endurain:error:conflict`), because two 409s share a status.
- Show a friendly translated message; surface `requestId` only where support needs it.
- Never render raw error objects or stack traces.

## Client state, composables, config

- Keep tokens in HTTP-only cookies, never `localStorage` or `sessionStorage`.

- Pinia setup stores for UI/client state only.
- Shared composables: `useForm`, `useToasts`, `useTheme`, `useLocale`, `useNavigation`, `useListPagination`, `useInfiniteScroll`, `useRouteQuery`, `useSafeRedirect`, `useRealtime`.
- Charts and maps go through `useChartProvider` / `useMapProvider`.
- Read deployment config from the app config or public server settings, not `import.meta.env` in views.

## Routing and performance

- `useRoute`/`useRouter` in `<script setup>`; guards via `beforeEach` / `beforeEnter`; route `meta` for auth and breadcrumbs.
- Lazy-load heavy views and components with dynamic imports.
- Prefer `computed` over `watch`; clean up side effects in `onUnmounted` or watch cleanups.
