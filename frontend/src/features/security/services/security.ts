import type {
  ApiKey,
  ApiKeyCreateDto,
  ApiKeyCreatedDto,
  ApiKeyCreateInput,
  ApiKeyDto,
  BackupCodeStatus,
  BackupCodeStatusDto,
  BackupCodesDto,
  BackupCodesResult,
  MfaDisableDto,
  MfaEnableDto,
  MfaEnableInput,
  MfaSetup,
  MfaSetupDto,
  MfaStatus,
  MfaStatusDto,
  PasswordChangeDto,
  PasswordChangeInput,
  SecuritySession,
  SecuritySessionDto,
  EmailChangeDto,
  IdpReauth,
  IdpReauthDto,
  StepUpDto,
  StepUpInput,
} from '@/features/security/types'

import { apiFetch } from '@/services/http'
import { fetchAllPages } from '@/services/pagination'

/** The scopes an API key can be granted (mirrors the backend allow-list). */
export const API_KEY_SCOPES = ['activities:upload'] as const

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

/** Safely parses the backend's JSON-encoded scopes string into an array. */
function parseScopes(scopesJson: string): string[] {
  try {
    const parsed: unknown = JSON.parse(scopesJson)
    return Array.isArray(parsed)
      ? parsed.filter((scope): scope is string => typeof scope === 'string')
      : []
  } catch {
    return []
  }
}

/**
 * Maps a raw API-key payload to the clean {@link ApiKey} model — the single
 * boundary where the snake_case wire shape is normalized and the JSON-encoded
 * `scopes` string is parsed into an array.
 *
 * @param dto - Raw API-key payload from the backend.
 * @returns The normalized API-key model.
 */
export function mapApiKey(dto: ApiKeyDto): ApiKey {
  return {
    id: dto.id,
    name: dto.name,
    keyPrefix: dto.key_prefix,
    scopes: parseScopes(dto.scopes),
    expiresAt: dto.expires_at ?? null,
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
 * @throws {HttpError} When the request fails (e.g. 400 wrong current password).
 */
export async function changePassword(input: PasswordChangeInput): Promise<void> {
  const payload: PasswordChangeDto = {
    current_password: input.currentPassword,
    password: input.newPassword,
    mfa_code: input.mfaCode,
    revoke_other_sessions: input.revokeOtherSessions,
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
 * accounts that have one), returning the one-time backup codes.
 *
 * @param input - The confirming code and optional step-up password.
 * @returns The generated backup codes (shown once).
 * @throws {HttpError} When the request fails (e.g. 400 invalid code).
 */
export async function enableMfa(input: MfaEnableInput): Promise<string[]> {
  const payload: MfaEnableDto = {
    mfa_code: input.mfaCode,
    current_password: input.currentPassword,
    ...toIdpReauthWire(input.idpReauth),
  }
  const response = await apiFetch<{ backup_codes: string[] }>('/profile/mfa/enable', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return response.backup_codes ?? []
}

/**
 * Disables MFA after step-up verification (an MFA or backup code, plus a
 * password for accounts that have one).
 *
 * @param input - The step-up credentials.
 * @throws {HttpError} When the request fails (e.g. 401 verification failed).
 */
export async function disableMfa(input: StepUpInput): Promise<void> {
  const payload: MfaDisableDto = {
    mfa_code: input.mfaCode ?? '',
    current_password: input.currentPassword,
    ...toIdpReauthWire(input.idpReauth),
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
 * @returns The newly generated backup codes.
 * @throws {HttpError} When the request fails (e.g. 401 verification failed).
 */
export async function regenerateBackupCodes(input: StepUpInput): Promise<BackupCodesResult> {
  const dto = await apiFetch<BackupCodesDto>('/profile/mfa/backup-codes', {
    method: 'POST',
    body: JSON.stringify(toStepUpWire(input)),
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
  const dtos = await fetchAllPages<SecuritySessionDto>('/profile/sessions', undefined, signal)
  return dtos.map(mapSecuritySession)
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
  await apiFetch('/profile/sessions', {
    method: 'DELETE',
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
  const dtos = await fetchAllPages<ApiKeyDto>('/profile/api-keys', undefined, signal)
  return dtos.map(mapApiKey)
}

/**
 * Creates a new API key (step-up: current password, plus an MFA code when MFA
 * is enabled). The raw key is returned once here and can never be retrieved
 * again, so the caller must show it to the user immediately.
 *
 * @param input - The clean create-API-key input.
 * @returns The full raw API key, shown once.
 * @throws {HttpError} When the request fails (e.g. 401 step-up, 400 invalid scopes).
 */
export async function createApiKey(input: ApiKeyCreateInput): Promise<string> {
  const payload: ApiKeyCreateDto = {
    name: input.name,
    scopes: input.scopes,
    expires_at: input.expiresAt,
    current_password: input.currentPassword,
    mfa_code: input.mfaCode,
    ...toIdpReauthWire(input.idpReauth),
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
 * @throws {HttpError} When the request fails (401 step-up, 409 only administrator).
 */
export async function deleteAccount(input: StepUpInput): Promise<void> {
  await apiFetch('/profile/delete-account', {
    method: 'POST',
    body: JSON.stringify(toStepUpWire(input)),
    responseType: 'void',
  })
}

/**
 * Changes the account email after step-up verification. The new address starts unverified and
 * the backend emails it a verification link when mail is configured.
 *
 * @param email - The new email address.
 * @param input - The step-up credentials (password and, with MFA, a code).
 * @param revokeOtherSessions - Whether to sign out every other session after the change.
 * @throws {HttpError} When the request fails (401 step-up, 409 address already in use).
 */
export async function changeEmail(
  email: string,
  input: StepUpInput,
  revokeOtherSessions: boolean,
): Promise<void> {
  const payload: EmailChangeDto = {
    email,
    ...toStepUpWire(input),
    revoke_other_sessions: revokeOtherSessions,
  }
  await apiFetch('/profile/email/change', {
    method: 'POST',
    body: JSON.stringify(payload),
    responseType: 'void',
  })
}
