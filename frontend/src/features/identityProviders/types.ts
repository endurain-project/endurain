import type { Schemas } from '@/types'

/** Raw authenticated identity-provider payload (snake_case wire shape). */
export type IdentityProviderDto = Schemas['IdentityProviderRead']

/** Create body for a new identity provider (client secret required). */
export type IdentityProviderCreateDto = Schemas['IdentityProviderCreate']

/** Update body for an identity provider (client secret optional). */
export type IdentityProviderUpdateDto = Schemas['IdentityProviderUpdate']

/** Raw identity-provider preset payload (snake_case wire shape). */
export type IdentityProviderTemplateDto = Schemas['IdentityProviderTemplateRead']

/**
 * The clean, camel-cased identity-provider model used across the admin zone.
 * Mapped from {@link IdentityProviderDto} at the service boundary so components
 * never touch the raw DTO. The client secret is intentionally absent — the
 * backend never returns it — so it only ever lives in the add/edit form.
 *
 * @property id - Stable unique identifier.
 * @property name - Display name shown to users on the login screen.
 * @property slug - URL-safe identifier used in the SSO login path (immutable after creation).
 * @property providerType - Protocol: `oidc`, `oauth2`, or `saml`.
 * @property enabled - Whether the provider is offered on the login screen.
 * @property issuerUrl - OIDC issuer / discovery URL, or `null`.
 * @property clientId - OAuth client id (decrypted for admins), or `null`.
 * @property scopes - Space-separated OAuth scopes.
 * @property icon - Built-in icon key or a custom icon URL, or `null`.
 * @property autoCreateUsers - Whether first-time logins auto-create an account.
 * @property syncUserInfo - Whether profile info is synced on each login.
 * @property authorizationEndpoint - Discovered OAuth authorization endpoint, or `null`.
 * @property tokenEndpoint - Discovered OAuth token endpoint, or `null`.
 * @property userinfoEndpoint - Discovered OIDC userinfo endpoint, or `null`.
 */
export interface IdentityProvider {
  id: number
  /** Row version echoed as `If-Match` when the provider is edited. */
  version: number
  name: string
  slug: string
  providerType: string
  enabled: boolean
  issuerUrl: string | null
  clientId: string | null
  scopes: string
  icon: string | null
  autoCreateUsers: boolean
  syncUserInfo: boolean
  authorizationEndpoint: string | null
  tokenEndpoint: string | null
  userinfoEndpoint: string | null
}

/**
 * A selectable preset that pre-fills the add form for a known provider.
 *
 * @property templateId - Stable preset identifier.
 * @property name - Human-readable preset name.
 * @property providerType - Protocol the preset configures.
 * @property issuerUrl - Issuer URL the preset applies, or `null`.
 * @property scopes - Scopes the preset applies.
 * @property icon - Icon key the preset applies, or `null`.
 * @property description - Short description shown under the preset selector.
 * @property configurationNotes - Setup guidance shown when the preset is chosen, or `null`.
 */
export interface IdentityProviderTemplate {
  templateId: string
  name: string
  providerType: string
  issuerUrl: string | null
  scopes: string
  icon: string | null
  description: string
  configurationNotes: string | null
}

/**
 * The editable provider fields shared by create and update. The service builds
 * the protocol-specific wire body from this: the client secret is required when
 * creating and omitted (left `null`) when editing to keep the stored secret.
 */
export interface IdentityProviderInput {
  name: string
  slug: string
  providerType: string
  enabled: boolean
  issuerUrl: string | null
  clientId: string | null
  /** Required on create; `null` on edit keeps the existing stored secret. */
  clientSecret: string | null
  scopes: string
  icon: string | null
  autoCreateUsers: boolean
  syncUserInfo: boolean
}
