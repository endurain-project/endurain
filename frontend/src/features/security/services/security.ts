import type {
  ApiKey,
  ApiKeyCreateDto,
  ApiKeyCreatedDto,
  ApiKeyCreateInput,
  ApiKeyDto,
  ApiKeyScope,
  BackupCodeStatus,
  BackupCodeStatusDto,
  BackupCodesDto,
  BackupCodesResult,
  MfaBackupCodesDto,
  MfaDisableDto,
  MfaEnableDto,
  MfaEnableInput,
  MfaSetup,
  MfaSetupDto,
  MfaStatus,
  MfaStatusDto,
  PasswordChangeDto,
  PasswordChangeInput,
  KnownDevice,
  KnownDeviceDto,
  SecuritySession,
  SecuritySessionDto,
  EmailChangeDto,
  EmailChangeResultDto,
  UsernameChangeDto,
  IdpReauth,
  IdpReauthDto,
  StepUpDto,
  StepUpRequestDto,
  StepUpInput,
} from '@/features/security/types'

import { apiFetch } from '@/services/http'
import { fetchAllPages } from '@/services/pagination'

/** Problem type of a change refused because it would leave the server without an administrator. */
export const LAST_ADMINISTRATOR_TYPE = 'urn:endurain:error:last-administrator'

/**
 * Starts an API key expiry at midnight of the chosen day in the viewer's timezone.
 *
 * A bare date would be read as UTC midnight, which west of UTC can already be past for the earliest date the
 * picker offers.
 *
 * @param date - A `YYYY-MM-DD` date.
 * @returns The instant the key expires.
 */
export function apiKeyExpiryInstant(date: string): Date {
  return new Date(`${date}T00:00`)
}

/** The resource groups the scope switches are listed under, in display order. */
export const API_KEY_SCOPE_GROUPS = [
  'account',
  'activities',
  'followers',
  'gears',
  'health',
  'healthTargets',
  'notifications',
  'users',
] as const

/**
 * The group each API key scope belongs to, in display order. Typed over every `ApiKeyScope`, so a scope the
 * backend adds and this map misses fails the type check.
 */
const API_KEY_SCOPE_GROUP: Record<ApiKeyScope, (typeof API_KEY_SCOPE_GROUPS)[number]> = {
  account: 'account',
  'activities:read': 'activities',
  'activities:write': 'activities',
  'activities:upload': 'activities',
  'followers:read': 'followers',
  'followers:write': 'followers',
  'gears:read': 'gears',
  'gears:write': 'gears',
  'health:read': 'health',
  'health:write': 'health',
  'health-targets:read': 'healthTargets',
  'health-targets:write': 'healthTargets',
  'notifications:read': 'notifications',
  'notifications:write': 'notifications',
  'users:read': 'users',
}

/** Problem type of a create refused because the account already holds the most active API keys. */
export const API_KEY_LIMIT_TYPE = 'urn:endurain:error:api-key-limit'

/** The scopes an API key can be granted, in display order. */
export const API_KEY_SCOPES = Object.keys(API_KEY_SCOPE_GROUP) as ApiKeyScope[]

/**
 * Lists the scopes of one group.
 *
 * @param group - A member of {@link API_KEY_SCOPE_GROUPS}.
 * @returns The group's scopes, in display order.
 */
export function apiKeyScopesOf(group: (typeof API_KEY_SCOPE_GROUPS)[number]): ApiKeyScope[] {
  return API_KEY_SCOPES.filter((scope) => API_KEY_SCOPE_GROUP[scope] === group)
}

/**
 * Names the locale key segment of a scope's label, e.g. `health-targets:read` is `healthTargetsRead`.
 *
 * @param scope - The API key scope.
 * @returns The camelCase key segment under `settings.security.apiKeys.scopeLabels`.
 */
export function apiKeyScopeLabelKey(scope: ApiKeyScope): string {
  return scope.replace(/[:-](\w)/g, (_match, char: string) => char.toUpperCase())
}

/** Maps a raw MFA-status payload to the clean model. */
export function mapMfaStatus(dto: MfaStatusDto): MfaStatus {
  return { enabled: dto.mfa_enabled }
}

/** Maps a raw MFA-setup payload to the clean model. */
export function mapMfaSetup(dto: MfaSetupDto): MfaSetup {
  return { secret: dto.secret, qrCode: dto.qr_code }
}

/** Maps a raw backup-code-status payload to the clean model. */
export function mapBackupCodeStatus(dto: BackupCodeStatusDto): BackupCodeStatus {
  return {
    hasCodes: dto.has_codes,
    total: dto.total,
    unused: dto.unused,
    used: dto.used,
  }
}

/** Maps a raw regenerated-backup-codes payload to the clean model. */
export function mapBackupCodes(dto: BackupCodesDto): BackupCodesResult {
  return { codes: dto.codes, createdAt: dto.created_at }
}

/**
 * Maps a raw session payload to the clean {@link SecuritySession} model — the
 * single boundary where the snake_case wire shape is normalized.
 *
 * @param dto - Raw session payload from the backend.
 * @returns The normalized session model.
 */
export function mapSecuritySession(dto: SecuritySessionDto): SecuritySession {
  return {
    id: dto.id,
    ipAddress: dto.ip_address,
    deviceType: dto.device_type,
    operatingSystem: dto.operating_system,
    operatingSystemVersion: dto.operating_system_version,
    browser: dto.browser,
    browserVersion: dto.browser_version,
    createdAt: dto.created_at,
    lastActivityAt: dto.last_activity_at,
    expiresAt: dto.expires_at,
    appRedirectUri: dto.app_redirect_uri ?? null,
  }
}

/**
 * Maps a raw known-device payload to the clean {@link KnownDevice} model.
 *
 * @param dto - Raw known-device payload from the backend.
 * @returns The normalized known-device model.
 */
export function mapKnownDevice(dto: KnownDeviceDto): KnownDevice {
  return {
    id: dto.id,
    browser: dto.browser ?? null,
    operatingSystem: dto.operating_system ?? null,
    deviceType: dto.device_type ?? null,
    createdAt: dto.created_at,
    lastSeenAt: dto.last_seen_at,
    current: dto.current,
  }
}

/** Maps the clean sign-in proof to its wire field, omitted when there is no proof. */
function toIdpReauthWire(reauth: IdpReauth | null | undefined): { idp_reauth?: IdpReauthDto } {
  return reauth ? { idp_reauth: { ticket: reauth.ticket, code_verifier: reauth.codeVerifier } } : {}
}

/**
 * Builds the step-up wire body, sending `null` for fields that don't apply.
 *
 * @param input - The step-up credentials.
 * @returns The wire body shared by every step-up-gated request.
 */
export function toStepUpWire(input: StepUpInput): StepUpDto {
  return {
    current_password: input.currentPassword,
    mfa_code: input.mfaCode,
    ...toIdpReauthWire(input.idpReauth),
  }
}

/**
 * Maps a raw API-key payload to the clean {@link ApiKey} model — the single
 * boundary where the snake_case wire shape is normalized.
 *
 * @param dto - Raw API-key payload from the backend.
 * @returns The normalized API-key model.
 */
export function mapApiKey(dto: ApiKeyDto): ApiKey {
  return {
    id: dto.id,
    name: dto.name,
    keyPrefix: dto.key_prefix,
    scopes: dto.scopes,
    expiresAt: dto.expires_at,
    lastUsedAt: dto.last_used_at ?? null,
    createdAt: dto.created_at,
    isActive: dto.is_active,
  }
}

/**
 * Changes the authenticated user's password (step-up: current password, plus an
 * MFA code when MFA is enabled). Optionally signs out every other session.
 *
 * @param input - The clean change-password input.
 * @throws {HttpError} When the request fails (e.g. 403 `step-up-failed` for a wrong current password or MFA code).
 */
export async function changePassword(input: PasswordChangeInput): Promise<void> {
  const payload: PasswordChangeDto = {
    password: input.newPassword,
    revoke_other_sessions: input.revokeOtherSessions,
    step_up: toStepUpWire({ currentPassword: input.currentPassword, mfaCode: input.mfaCode }),
  }
  await apiFetch('/profile/password/change', {
    method: 'POST',
    body: JSON.stringify(payload),
    responseType: 'void',
  })
}

/**
 * Fetches whether MFA is enabled for the authenticated user.
 *
 * @param signal - Optional abort signal for cancellation.
 * @returns The MFA status, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function fetchMfaStatus(signal?: AbortSignal): Promise<MfaStatus> {
  return mapMfaStatus(await apiFetch<MfaStatusDto>('/profile/mfa/status', { signal }))
}

/**
 * Begins MFA enrolment, returning the TOTP secret and a QR image to scan. The
 * secret is held server-side until enrolment is confirmed via {@link enableMfa}.
 *
 * @returns The setup data (secret + QR image), mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function setupMfa(): Promise<MfaSetup> {
  return mapMfaSetup(await apiFetch<MfaSetupDto>('/profile/mfa/setup', { method: 'POST' }))
}

/**
 * Completes MFA enrolment with the first valid code (and a step-up password for
 * accounts that have one), returning the one-time backup codes. Optionally signs
 * out every other session.
 *
 * @param input - The confirming code, optional step-up password and sessions choice.
 * @returns The generated backup codes (shown once).
 * @throws {HttpError} When the request fails (e.g. 400 invalid code).
 */
export async function enableMfa(input: MfaEnableInput): Promise<string[]> {
  const payload: MfaEnableDto = {
    totp_code: input.mfaCode,
    step_up: toStepUpWire({
      currentPassword: input.currentPassword,
      mfaCode: null,
      idpReauth: input.idpReauth,
    }),
    revoke_other_sessions: input.revokeOtherSessions,
  }
  const dto = await apiFetch<BackupCodesDto>('/profile/mfa/enable', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return mapBackupCodes(dto).codes
}

/**
 * Disables MFA after step-up verification (an MFA or backup code, plus a
 * password for accounts that have one).
 *
 * @param input - The step-up credentials.
 * @param revokeOtherSessions - Whether to sign out every other session after the change.
 * @throws {HttpError} When the request fails (e.g. 403 verification failed).
 */
export async function disableMfa(input: StepUpInput, revokeOtherSessions: boolean): Promise<void> {
  const payload: MfaDisableDto = {
    step_up: toStepUpWire(input),
    revoke_other_sessions: revokeOtherSessions,
  }
  await apiFetch('/profile/mfa/disable', {
    method: 'POST',
    body: JSON.stringify(payload),
    responseType: 'void',
  })
}

/**
 * Fetches the remaining-backup-codes summary (only meaningful while MFA is on).
 *
 * @param signal - Optional abort signal for cancellation.
 * @returns The backup-code status, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function fetchBackupCodeStatus(signal?: AbortSignal): Promise<BackupCodeStatus> {
  return mapBackupCodeStatus(
    await apiFetch<BackupCodeStatusDto>('/profile/mfa/backup-codes/status', { signal }),
  )
}

/**
 * Regenerates the MFA backup codes after step-up verification. The previous set
 * is invalidated, so the new codes are shown once for the user to save.
 *
 * @param input - The step-up credentials.
 * @param revokeOtherSessions - Whether to sign out every other session after the change.
 * @returns The newly generated backup codes.
 * @throws {HttpError} When the request fails (e.g. 403 verification failed).
 */
export async function regenerateBackupCodes(
  input: StepUpInput,
  revokeOtherSessions: boolean,
): Promise<BackupCodesResult> {
  const payload: MfaBackupCodesDto = {
    step_up: toStepUpWire(input),
    revoke_other_sessions: revokeOtherSessions,
  }
  const dto = await apiFetch<BackupCodesDto>('/profile/mfa/backup-codes', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return mapBackupCodes(dto)
}

/**
 * Lists the authenticated user's active sessions.
 *
 * @param signal - Optional abort signal for cancellation.
 * @returns The sessions, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function fetchSessions(signal?: AbortSignal): Promise<SecuritySession[]> {
  const dtos = await fetchAllPages<SecuritySessionDto>('/profile/sessions', undefined, { signal })
  return dtos.map(mapSecuritySession)
}

/**
 * Lists the devices the authenticated user is known to sign in from.
 *
 * @param signal - Optional abort signal for cancellation.
 * @returns The known devices, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function fetchKnownDevices(signal?: AbortSignal): Promise<KnownDevice[]> {
  const dtos = await fetchAllPages<KnownDeviceDto>('/profile/devices', undefined, { signal })
  return dtos.map(mapKnownDevice)
}

/**
 * Forgets one of the authenticated user's known devices after step-up verification.
 *
 * @param deviceId - The device id to forget.
 * @param input - The step-up credentials.
 * @throws {HttpError} When the request fails (403 step-up, 404 no such device).
 */
export async function forgetKnownDevice(deviceId: number, input: StepUpInput): Promise<void> {
  await apiFetch(`/profile/devices/${deviceId}/delete`, {
    method: 'POST',
    body: JSON.stringify({ step_up: toStepUpWire(input) } satisfies StepUpRequestDto),
    responseType: 'void',
  })
}

/**
 * Forgets every known device except the one making the request (step-up gated). The sessions
 * that signed in from the forgotten devices end.
 *
 * @param input - The step-up credentials.
 * @throws {HttpError} When the request fails (403 step-up).
 */
export async function forgetOtherKnownDevices(input: StepUpInput): Promise<void> {
  await apiFetch('/profile/devices/revoke', {
    method: 'POST',
    body: JSON.stringify({ step_up: toStepUpWire(input) } satisfies StepUpRequestDto),
    responseType: 'void',
  })
}

/**
 * Forgets every known device, the one making the request included (step-up gated). The sessions
 * that signed in from the devices end, this one with them, and the server clears the browser's
 * refresh-token cookie.
 *
 * @param input - The step-up credentials.
 * @throws {HttpError} When the request fails (403 step-up).
 */
export async function forgetAllKnownDevices(input: StepUpInput): Promise<void> {
  await apiFetch('/profile/devices/delete', {
    method: 'POST',
    body: JSON.stringify({ step_up: toStepUpWire(input) } satisfies StepUpRequestDto),
    responseType: 'void',
  })
}

/**
 * Revokes one of the authenticated user's sessions, signing that device out.
 *
 * @param sessionId - The session id to revoke.
 * @throws {HttpError} When the request fails.
 */
export async function revokeSession(sessionId: string): Promise<void> {
  await apiFetch(`/profile/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
    responseType: 'void',
  })
}

/**
 * Revokes all of the authenticated user's other sessions in one request — the
 * self-service "sign out other devices" action. The backend keeps the caller's
 * current session (identified from the access token), so no session id is sent.
 *
 * @throws {HttpError} When the request fails.
 */
export async function revokeOtherSessions(): Promise<void> {
  await apiFetch('/profile/sessions/revoke?keep_current=true', {
    method: 'POST',
    responseType: 'void',
  })
}

/**
 * Ends every session of the authenticated user, the current one included — the
 * self-service "sign out everywhere" action. The server also clears the
 * browser's refresh-token cookie.
 *
 * @throws {HttpError} When the request fails.
 */
export async function signOutEverywhere(): Promise<void> {
  await apiFetch('/profile/sessions/revoke', {
    method: 'POST',
    responseType: 'void',
  })
}

/**
 * Lists the authenticated user's API keys. Raw keys are never returned here —
 * only the prefix and metadata.
 *
 * @param signal - Optional abort signal for cancellation.
 * @returns The API keys, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function fetchApiKeys(signal?: AbortSignal): Promise<ApiKey[]> {
  const dtos = await fetchAllPages<ApiKeyDto>('/profile/api-keys', undefined, { signal })
  return dtos.map(mapApiKey)
}

/**
 * Creates a new API key (step-up: current password, plus an MFA code when MFA
 * is enabled). The raw key is returned once here and can never be retrieved
 * again, so the caller must show it to the user immediately.
 *
 * @param input - The clean create-API-key input.
 * @returns The full raw API key, shown once.
 * @throws {HttpError} When the request fails (e.g. 403 step-up, 422 on `body.scopes` or `body.expires_at`).
 */
export async function createApiKey(input: ApiKeyCreateInput): Promise<string> {
  const payload: ApiKeyCreateDto = {
    name: input.name,
    scopes: input.scopes,
    expires_at: input.expiresAt ? apiKeyExpiryInstant(input.expiresAt).toISOString() : null,
    step_up: toStepUpWire(input),
  }
  const dto = await apiFetch<ApiKeyCreatedDto>('/profile/api-keys', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return dto.key
}

/**
 * Revokes an API key (soft-disable). The record is kept for audit but the key
 * is rejected on any subsequent use.
 *
 * @param id - The API-key id to revoke.
 * @throws {HttpError} When the request fails.
 */
export async function revokeApiKey(id: string): Promise<void> {
  await apiFetch(`/profile/api-keys/${encodeURIComponent(id)}/revoke`, {
    method: 'POST',
    responseType: 'void',
  })
}

/**
 * Permanently deletes an API key. The key is gone and cannot be recovered.
 *
 * @param id - The API-key id to delete.
 * @throws {HttpError} When the request fails.
 */
export async function deleteApiKey(id: string): Promise<void> {
  await apiFetch(`/profile/api-keys/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    responseType: 'void',
  })
}

/**
 * Queues the permanent deletion of the authenticated user's account and all of
 * their data (the GDPR right to erasure) after step-up verification. The backend
 * signs the user out and deactivates the account at once (202), then a background
 * job removes the activities and their files, health records, gear, goals,
 * integrations and every other row that references the user. It refuses when the
 * user is the server's only administrator.
 *
 * @param input - The step-up credentials.
 * @throws {HttpError} When the request fails (403 step-up, 409 `last-administrator` for the only administrator).
 */
export async function deleteAccount(input: StepUpInput): Promise<void> {
  await apiFetch('/profile/delete-account', {
    method: 'POST',
    body: JSON.stringify({ step_up: toStepUpWire(input) } satisfies StepUpRequestDto),
    responseType: 'void',
  })
}

/**
 * Requests an account email change after step-up verification. With mail configured the new
 * address is held as pending and emailed a confirmation link; without mail it applies at once,
 * unverified. Submitting the current address cancels a pending change.
 *
 * @param email - The new email address.
 * @param input - The step-up credentials (password and, with MFA, a code).
 * @param revokeOtherSessions - Whether to sign out every other session after the change.
 * @returns Whether the new address awaits confirmation (`false` when it applied at once).
 * @throws {HttpError} When the request fails (403 step-up, 409 address already in use).
 */
export async function changeEmail(
  email: string,
  input: StepUpInput,
  revokeOtherSessions: boolean,
): Promise<boolean> {
  const payload: EmailChangeDto = {
    email,
    revoke_other_sessions: revokeOtherSessions,
    step_up: toStepUpWire(input),
  }
  const profile = await apiFetch<EmailChangeResultDto>('/profile/email/change', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return profile.pending_email != null
}

/**
 * Changes the account username after step-up verification. The username is the sign-in name, so it
 * applies at once; the account's email address is told of the change.
 *
 * @param username - The new username.
 * @param input - The step-up credentials (password and, with MFA, a code).
 * @param revokeOtherSessions - Whether to sign out every other session after the change.
 * @throws {HttpError} When the request fails (403 step-up, 409 username already in use).
 */
export async function changeUsername(
  username: string,
  input: StepUpInput,
  revokeOtherSessions: boolean,
): Promise<void> {
  const payload: UsernameChangeDto = {
    username,
    revoke_other_sessions: revokeOtherSessions,
    step_up: toStepUpWire(input),
  }
  await apiFetch('/profile/username/change', {
    method: 'POST',
    body: JSON.stringify(payload),
    responseType: 'void',
  })
}

/**
 * Asks for a new confirmation link for the pending email change. The backend always answers 204,
 * including when the resend cooldown suppresses the email.
 *
 * @throws {HttpError} When the request fails.
 */
export async function resendEmailChange(): Promise<void> {
  await apiFetch('/profile/email/change/resend', { method: 'POST', responseType: 'void' })
}

/**
 * Cancels the pending email change; the current address stays as it is.
 *
 * @throws {HttpError} When the request fails.
 */
export async function cancelEmailChange(): Promise<void> {
  await apiFetch('/profile/email/change', { method: 'DELETE', responseType: 'void' })
}
