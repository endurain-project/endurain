import type { Schemas } from '@/types'

/** The protocol a provider speaks. */
export type ProviderType = Schemas['ProviderType']

/** Raw authenticated identity-provider payload (snake_case wire shape). */
export type IdentityProviderDto = Schemas['IdentityProviderRead']

/** Create body for a new identity provider (client secret and the administrator's step-up required). */
export type IdentityProviderCreateDto = Schemas['IdentityProviderCreateRequest']

/** Update body for an identity provider (client secret optional, the administrator's step-up required). */
export type IdentityProviderUpdateDto = Schemas['IdentityProviderUpdateRequest']

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
 * @property providerType - Protocol: `oidc` or `oauth2`.
 * @property enabled - Whether the provider is offered on the login screen.
 * @property issuerUrl - OIDC issuer / discovery URL, or `null`.
 * @property clientId - OAuth client id (decrypted for admins), or `null`.
 * @property scopes - Space-separated OAuth scopes.
 * @property icon - Built-in icon key or a custom icon URL, or `null`.
 * @property iconUploaded - Whether an uploaded image is shown instead of `icon`.
 * @property autoCreateUsers - Whether first-time logins auto-create an account.
 * @property linkByEmail - Whether an unlinked sign-in joins the local account with the same verified email.
 * @property syncUserInfo - Whether the mapped profile fields, except the email, are synced on each login.
 * @property syncEmail - Whether the email the provider verified is synced on each login.
 * @property authorizationEndpoint - Discovered OAuth authorization endpoint, or `null`.
 * @property tokenEndpoint - Discovered OAuth token endpoint, or `null`.
 * @property userinfoEndpoint - Discovered OIDC userinfo endpoint, or `null`.
 */
export interface IdentityProvider {
  id: string
  /** Row version echoed as `If-Match` when the provider is edited. */
  version: number
  name: string
  slug: string
  providerType: ProviderType
  enabled: boolean
  issuerUrl: string | null
  clientId: string | null
  scopes: string
  icon: string | null
  iconUploaded: boolean
  autoCreateUsers: boolean
  linkByEmail: boolean
  syncUserInfo: boolean
  syncEmail: boolean
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
 * @property linkByEmail - Whether the preset links an unlinked sign-in by email.
 * @property syncEmail - Whether the preset syncs the verified email on each login.
 * @property scopes - Scopes the preset applies.
 * @property icon - Icon key the preset applies, or `null`.
 * @property description - Short description shown under the preset selector.
 * @property configurationNotes - Setup guidance shown when the preset is chosen, or `null`.
 */
export interface IdentityProviderTemplate {
  templateId: string
  name: string
  providerType: ProviderType
  issuerUrl: string | null
  linkByEmail: boolean
  syncEmail: boolean
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
  providerType: ProviderType
  enabled: boolean
  issuerUrl: string | null
  clientId: string | null
  /** Required on create; `null` on edit keeps the existing stored secret. */
  clientSecret: string | null
  scopes: string
  icon: string | null
  autoCreateUsers: boolean
  linkByEmail: boolean
  syncUserInfo: boolean
  syncEmail: boolean
}
