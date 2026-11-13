import type { StepUpInput, StepUpRequestDto } from '@/features/security/types'
import type { UserSession, UserSessionDto } from '@/features/users/types'

import { apiFetch } from '@/services/http'
import { fetchAllPages } from '@/services/pagination'
import { toStepUpWire } from '@/features/security/services/security'

/**
 * Maps a raw `UserSessionsRead` payload to the clean {@link UserSession} model
 * — the single boundary where the snake_case wire shape is normalized.
 *
 * @param dto - Raw session payload from the backend.
 * @returns The normalized session model.
 */
export function mapUserSession(dto: UserSessionDto): UserSession {
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
 * Lists a user's active sessions (admin scope `sessions:read`). The backend
 * returns an empty list in demo environments.
 *
 * @param userId - The target user id.
 * @param signal - Optional abort signal for cancellation.
 * @returns The user's sessions, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function fetchUserSessions(
  userId: string,
  signal?: AbortSignal,
): Promise<UserSession[]> {
  const dtos = await fetchAllPages<UserSessionDto>(`/users/${userId}/sessions`, undefined, {
    signal,
  })
  return dtos.map(mapUserSession)
}

/**
 * Revokes a single session for a user (admin scope `sessions:write`), signing
 * that device out. Needs the administrator's own step-up.
 *
 * @param sessionId - The session id to revoke.
 * @param userId - The session owner's id.
 * @param stepUp - The administrator's step-up credentials.
 * @throws {HttpError} When the request fails (`403` when the step-up is refused).
 */
export async function revokeUserSession(
  sessionId: string,
  userId: string,
  stepUp: StepUpInput,
): Promise<void> {
  await apiFetch<void>(`/users/${userId}/sessions/${encodeURIComponent(sessionId)}/revoke`, {
    method: 'POST',
    body: JSON.stringify({ step_up: toStepUpWire(stepUp) } satisfies StepUpRequestDto),
    responseType: 'void',
  })
}

/**
 * Revokes all of a user's sessions in one request (admin scope
 * `sessions:write`), optionally keeping one intact. Pass the caller's current
 * session id to leave it signed in ("revoke other sessions"). Needs the
 * administrator's own step-up.
 *
 * @param userId - The session owner's id.
 * @param stepUp - The administrator's step-up credentials.
 * @param excludeSessionId - Optional session to keep (e.g. the caller's current one).
 * @throws {HttpError} When the request fails (`403` when the step-up is refused).
 */
export async function revokeOtherUserSessions(
  userId: string,
  stepUp: StepUpInput,
  excludeSessionId?: string,
): Promise<void> {
  const query = excludeSessionId
    ? `?exclude_session_id=${encodeURIComponent(excludeSessionId)}`
    : ''
  await apiFetch<void>(`/users/${userId}/sessions/revoke${query}`, {
    method: 'POST',
    body: JSON.stringify({ step_up: toStepUpWire(stepUp) } satisfies StepUpRequestDto),
    responseType: 'void',
  })
}
