import type { StepUpInput, StepUpRequestDto, ApiKey, ApiKeyDto } from '@/features/security/types'

import { apiFetch } from '@/services/http'
import { fetchAllPages } from '@/services/pagination'
import { mapApiKey, toStepUpWire } from '@/features/security/services/security'

/**
 * Lists a user's API keys, active and revoked (admin scope `api-keys:read`). The
 * secret of a key is never returned.
 *
 * @param userId - The key owner's id.
 * @param signal - Optional abort signal for cancellation.
 * @returns The user's API keys, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function fetchUserApiKeys(userId: string, signal?: AbortSignal): Promise<ApiKey[]> {
  const dtos = await fetchAllPages<ApiKeyDto>(`/users/${userId}/api-keys`, undefined, { signal })
  return dtos.map(mapApiKey)
}

/**
 * Revokes one of a user's API keys (admin scope `api-keys:write`) and notifies the
 * user. Needs the administrator's own step-up.
 *
 * @param apiKeyId - The key id to revoke.
 * @param userId - The key owner's id.
 * @param stepUp - The administrator's step-up credentials.
 * @throws {HttpError} When the request fails (`403` when the step-up is refused, `404` for an unknown key).
 */
export async function revokeUserApiKey(
  apiKeyId: string,
  userId: string,
  stepUp: StepUpInput,
): Promise<void> {
  await apiFetch<void>(`/users/${userId}/api-keys/${encodeURIComponent(apiKeyId)}/revoke`, {
    method: 'POST',
    body: JSON.stringify({ step_up: toStepUpWire(stepUp) } satisfies StepUpRequestDto),
    responseType: 'void',
  })
}

/**
 * Revokes every active API key of a user in one request and notifies the user.
 * Needs the administrator's own step-up.
 *
 * @param userId - The key owner's id.
 * @param stepUp - The administrator's step-up credentials.
 * @throws {HttpError} When the request fails (`403` when the step-up is refused).
 */
export async function revokeAllUserApiKeys(userId: string, stepUp: StepUpInput): Promise<void> {
  await apiFetch<void>(`/users/${userId}/api-keys/revoke`, {
    method: 'POST',
    body: JSON.stringify({ step_up: toStepUpWire(stepUp) } satisfies StepUpRequestDto),
    responseType: 'void',
  })
}
