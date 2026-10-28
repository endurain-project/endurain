import type { Schemas } from '@/types'

/** Change-password request body (snake_case wire shape). */
export type PasswordChangeDto = Schemas['UsersEditPassword']

/** Raw MFA status payload. */
export type MfaStatusDto = Schemas['MFAStatusRead']

/** Raw MFA setup payload (TOTP secret + QR image). */
export type MfaSetupDto = Schemas['MFASetupRead']

/** Enable-MFA request body. */
export type MfaEnableDto = Schemas['MFASetupRequest']

/** Disable-MFA request body. */
export type MfaDisableDto = Schemas['MFADisableRequest']

/** Raw backup-code status payload. */
export type BackupCodeStatusDto = Schemas['MFABackupCodeStatusRead']

/** Raw regenerated backup-codes payload. */
export type BackupCodesDto = Schemas['MFABackupCodesRead']

/** Step-up verification body shared by sensitive self-service actions. */
export type StepUpDto = Schemas['StepUpVerification']

/** Email-change request body: the new address plus the step-up credentials. */
export type EmailChangeDto = Schemas['EmailChange']

/** Raw session payload (snake_case wire shape). */
export type SecuritySessionDto = Schemas['UsersSessionsRead']

/**
 * The clean inputs the change-password form collects. The MFA code is only
 * required when the account has MFA enabled; `revokeOtherSessions` signs out
 * every other device on success.
 */
export interface PasswordChangeInput {
  currentPassword: string
  newPassword: string
  mfaCode: string | null
  revokeOtherSessions: boolean
}

/** Whether the account currently has MFA (TOTP) enabled. */
export interface MfaStatus {
  enabled: boolean
}

/** The data needed to display a TOTP enrolment: the secret and a QR image. */
export interface MfaSetup {
  /** The base32 TOTP secret, shown for manual entry. */
  secret: string
  /** A ready-to-render `data:image/png;base64,...` QR code. */
  qrCode: string
}

/** Credentials proving control of the account before a sensitive change. */
export interface StepUpInput {
  /** The current password, or `null` for SSO-only accounts. */
  currentPassword: string | null
  /** A TOTP or backup code, or `null` when MFA is not enabled. */
  mfaCode: string | null
}

/** Completes MFA enrolment: the first valid code plus optional step-up password. */
export interface MfaEnableInput {
  mfaCode: string
  currentPassword: string | null
}

/** The remaining-backup-codes summary shown while MFA is enabled. */
export interface BackupCodeStatus {
  hasCodes: boolean
  total: number
  unused: number
  used: number
}

/** Freshly generated backup codes, shown once for the user to save. */
export interface BackupCodesResult {
  codes: string[]
  createdAt: string
}

/**
 * The clean, camel-cased session model used by the sessions card. Mapped from
 * {@link SecuritySessionDto} at the service boundary.
 *
 * @property id - Stable session identifier (also the revoke key).
 * @property ipAddress - The IP the session was last seen from.
 * @property deviceType - Coarse device class (desktop/mobile/…).
 * @property operatingSystem - OS family.
 * @property operatingSystemVersion - OS version.
 * @property browser - Browser family.
 * @property browserVersion - Browser version.
 * @property createdAt - When the session was created (ISO).
 * @property lastActivityAt - When the session was last active (ISO).
 * @property expiresAt - When the session expires (ISO).
 */
export interface SecuritySession {
  id: string
  ipAddress: string
  deviceType: string
  operatingSystem: string
  operatingSystemVersion: string
  browser: string
  browserVersion: string
  createdAt: string
  lastActivityAt: string
  expiresAt: string
}

/** Raw linked identity-provider payload (snake_case wire shape). */
export type LinkedProviderDto = Schemas['IdentityProviderLinkRead']

/** Raw link-token payload from the generate-link-token step. */
export type LinkTokenDto = Schemas['IdentityProviderLinkTokenRead']

/** A provider a user can link to (an enabled public provider). */
export type AvailableProvider = Schemas['IdentityProviderPublicRead']

/**
 * A clean linked identity-provider model for the security zone. Mapped from
 * {@link LinkedProviderDto} at the service boundary.
 *
 * @property id - The link record id.
 * @property idpId - The identity-provider id (used to unlink).
 * @property name - Provider display name, or `null`.
 * @property slug - Provider slug, or `null`.
 * @property icon - Provider icon key or URL, or `null`.
 * @property providerType - Provider protocol (oidc/oauth2/saml), or `null`.
 * @property subject - The user's subject id at the provider.
 * @property linkedAt - When the account was linked (ISO).
 * @property lastLogin - Last login via this provider (ISO), or `null`.
 */
export interface LinkedProvider {
  id: number
  idpId: number
  name: string | null
  slug: string | null
  icon: string | null
  providerType: string | null
  subject: string
  linkedAt: string
  lastLogin: string | null
}

/** Raw API-key payload (snake_case wire shape; `scopes` is a JSON string). */
export type ApiKeyDto = Schemas['UsersApiKeyRead']

/** Raw create-API-key response, including the one-time raw `key`. */
export type ApiKeyCreatedDto = Schemas['UsersApiKeyCreatedRead']

/** Create-API-key request body. */
export type ApiKeyCreateDto = Schemas['UsersApiKeyCreate']

/**
 * A clean, camel-cased API-key model for the security zone. Mapped from
 * {@link ApiKeyDto} at the service boundary, where the JSON-encoded `scopes`
 * string is parsed into an array.
 *
 * @property id - Stable key identifier (UUID; also the revoke/delete key).
 * @property name - User-friendly label.
 * @property keyPrefix - First characters of the key, shown for identification.
 * @property scopes - The granted scopes (parsed from the wire JSON string).
 * @property expiresAt - When the key expires (ISO), or `null` for no expiry.
 * @property lastUsedAt - When the key was last used (ISO), or `null`.
 * @property createdAt - When the key was created (ISO).
 * @property isActive - Whether the key is active (not revoked).
 */
export interface ApiKey {
  id: string
  name: string
  keyPrefix: string
  scopes: string[]
  expiresAt: string | null
  lastUsedAt: string | null
  createdAt: string
  isActive: boolean
}

/**
 * The clean inputs the create-API-key dialog collects. Step-up credentials are
 * required because minting a key is a persistent grant of account access.
 *
 * @property expiresAt - A `YYYY-MM-DD` date, or `null` for a key that never expires.
 */
export interface ApiKeyCreateInput {
  name: string
  scopes: string[]
  expiresAt: string | null
  currentPassword: string | null
  mfaCode: string | null
}
