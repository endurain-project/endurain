import type { StepUpInput, StepUpRequestDto } from '@/features/security/types'
import type { UserIdentityProvider, UserIdentityProviderDto } from '@/features/users/types'

import { apiFetch } from '@/services/http'
import { fetchAllPages } from '@/services/pagination'
import { toStepUpWire } from '@/features/security/services/security'

/**
 * Maps a raw `IdentityProviderLinkRead` payload to the clean
 * {@link UserIdentityProvider} model — the single boundary where the snake_case
 * wire shape is normalized.
 *
 * @param dto - Raw identity-provider link payload from the backend.
 * @returns The normalized identity-provider link model.
 */
export function mapUserIdentityProvider(dto: UserIdentityProviderDto): UserIdentityProvider {
  return {
    id: dto.id,
    idpId: dto.idp_id,
    name: dto.idp_name ?? null,
    slug: dto.idp_slug ?? null,
    providerType: dto.idp_provider_type ?? null,
    subject: dto.idp_subject,
    linkedAt: dto.linked_at,
    lastLogin: dto.last_login ?? null,
  }
}

/**
 * Lists a user's linked identity providers (admin scope `users:read`).
 *
 * @param userId - The target user id.
 * @param signal - Optional abort signal for cancellation.
 * @returns The user's identity-provider links, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function fetchUserIdentityProviders(
  userId: number,
  signal?: AbortSignal,
): Promise<UserIdentityProvider[]> {
  const dtos = await fetchAllPages<UserIdentityProviderDto>(
    `/users/${userId}/identity-providers`,
    undefined,
    { signal },
  )
  return dtos.map(mapUserIdentityProvider)
}

/**
 * Unlinks an identity provider from a user (admin scope `users:write`). The
 * backend rejects the request (409 `last-sign-in-method`) when this is the user's
 * last authentication method and they have no password set.
 *
 * @param userId - The target user id.
 * @param idpId - The identity provider id to unlink.
 * @param stepUp - The administrator's step-up credentials.
 * @throws {HttpError} When the request fails.
 */
export async function unlinkUserIdentityProvider(
  userId: number,
  idpId: number,
  stepUp: StepUpInput,
): Promise<void> {
  await apiFetch<void>(`/users/${userId}/identity-providers/${idpId}/unlink`, {
    method: 'POST',
    body: JSON.stringify({ step_up: toStepUpWire(stepUp) } satisfies StepUpRequestDto),
    responseType: 'void',
  })
}
