import type { components } from './api.generated'

/**
 * Accessor for the backend's generated OpenAPI schema types. Derive
 * API-boundary DTOs from `Schemas['Name']` so a backend contract change
 * surfaces here as a TypeScript error instead of a silent runtime mismatch.
 * Regenerate with `npm run gen:api` (see the OpenAPI drift CI check).
 *
 * Feature-specific DTOs live in their feature's `types.ts` (e.g.
 * `@/features/auth/types`); this module holds only types consumed by shared
 * infrastructure (`@/services`, `@/composables`, UI primitives).
 */
export type Schemas = components['schemas']

/**
 * Web token payload returned by login, MFA verification, and refresh. Derived
 * from the backend's generated `TokenWebRead` schema.
 *
 * Lives in shared types (not the auth feature) because the core HTTP layer
 * consumes it directly for transparent token refresh; keeping it here avoids a
 * `@/services/http` → feature dependency. Tokens are held in memory only; the
 * refresh token stays in an HTTP-only cookie managed by the backend.
 */
export type AuthTokenResponse = Schemas['TokenWebRead']

/**
 * Token exchange response returned by the SSO PKCE endpoint. Derived from the
 * backend's generated `TokenExchangeRead` schema.
 *
 * Lives in shared types because the shared `@/services/identityProviders` SSO
 * service returns it; both the auth and config features consume that service.
 */
export type SsoTokenExchangeResponse = Schemas['TokenExchangeRead']

/**
 * Public identity-provider summary returned for login screens. Derived from
 * the backend's generated `IdentityProviderPublicRead` schema.
 *
 * Lives in shared types because the shared `@/services/identityProviders`
 * service produces it for both the auth (SSO login) and config (public server
 * settings) features.
 */
export type IdentityProviderPublic = Schemas['IdentityProviderPublicRead']

/**
 * Content visibility level, mirrored from the backend. Drives the
 * `<VisibilityGate>` primitive so private/followers/unlisted/public/federated
 * rendering decisions live in one enum-driven place rather than ad-hoc `v-if`s.
 */
export type VisibilityLevel = 'private' | 'followers' | 'unlisted' | 'public' | 'federated'

/**
 * Severity vocabulary shared by inline alerts and toasts, mapped to the
 * semantic accent tokens (info/success/warning/error).
 */
export type Severity = 'info' | 'success' | 'warning' | 'error'
