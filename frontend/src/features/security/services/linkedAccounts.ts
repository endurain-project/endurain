import type {
  IdentityProviderLinkStartDto,
  LinkedProvider,
  LinkedProviderDto,
  StepUpInput,
  StepUpRequestDto,
  StepUpStartResultDto,
} from '@/features/security/types'

import { apiFetch } from '@/services/http'
import { fetchAllPages } from '@/services/pagination'
import { toStepUpWire } from '@/features/security/services/security'

/**
 * Maps a raw linked-provider payload to the clean {@link LinkedProvider} model
 * — the single boundary where the snake_case wire shape is normalized.
 *
 * @param dto - Raw linked-provider payload from the backend.
 * @returns The normalized linked-provider model.
 */
export function mapLinkedProvider(dto: LinkedProviderDto): LinkedProvider {
  return {
    id: dto.id,
    idpId: dto.idp_id,
    name: dto.idp_name ?? null,
    slug: dto.idp_slug ?? null,
    icon: dto.idp_icon ?? null,
    iconUploaded: dto.idp_icon_uploaded ?? false,
    providerType: dto.idp_provider_type ?? null,
    subject: dto.idp_subject,
    linkedAt: dto.linked_at,
    lastLogin: dto.last_login ?? null,
  }
}

/**
 * Lists the authenticated user's linked identity providers.
 *
 * @param signal - Optional abort signal for cancellation.
 * @returns The linked providers, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function fetchLinkedProviders(signal?: AbortSignal): Promise<LinkedProvider[]> {
  const dtos = await fetchAllPages<LinkedProviderDto>('/profile/identity-providers', undefined, {
    signal,
  })
  return dtos.map(mapLinkedProvider)
}

/**
 * Starts linking an identity provider after step-up verification. The response
 * also sets the cookie that binds the link to this browser, so the browser must
 * then be sent to the returned URL.
 *
 * The `returnPath` is captured on the backend's OAuth state and used to build
 * the final post-callback redirect, so the browser lands back on this exact
 * frontend route (carrying the `idp_link` result). It must be a relative path;
 * the backend validates it against open redirects.
 *
 * @param idpId - The identity-provider id to link.
 * @param input - The step-up credentials.
 * @param revokeOtherSessions - Whether completing the link signs out every other session.
 * @param returnPath - The frontend route to return to after the callback.
 * @returns The identity provider's authorization URL.
 * @throws {HttpError} When the request fails (403 step-up, 409 already linked).
 */
export async function startProviderLink(
  idpId: number,
  input: StepUpInput,
  revokeOtherSessions: boolean,
  returnPath = '/settings/security',
): Promise<string> {
  const payload: IdentityProviderLinkStartDto = {
    redirect: returnPath,
    revoke_other_sessions: revokeOtherSessions,
    step_up: toStepUpWire(input),
  }
  const dto = await apiFetch<StepUpStartResultDto>(`/profile/identity-providers/${idpId}/link`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return dto.authorization_url
}

/**
 * Unlinks an identity provider after step-up verification. The backend rejects
 * the request (400) when this is the user's last authentication method and they
 * have no password set.
 *
 * @param idpId - The identity-provider id to unlink.
 * @param input - The step-up credentials.
 * @throws {HttpError} When the request fails (403 step-up, 400 last method).
 */
export async function unlinkProvider(idpId: number, input: StepUpInput): Promise<void> {
  await apiFetch(`/profile/identity-providers/${idpId}/unlink`, {
    method: 'POST',
    body: JSON.stringify({ step_up: toStepUpWire(input) } satisfies StepUpRequestDto),
    responseType: 'void',
  })
}
