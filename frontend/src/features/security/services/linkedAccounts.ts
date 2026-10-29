import type {
  LinkTokenDto,
  LinkedProvider,
  LinkedProviderDto,
  StepUpInput,
} from '@/features/security/types'

import { API_BASE_URL, apiFetch } from '@/services/http'
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
  const dtos = await apiFetch<LinkedProviderDto[] | null>('/profile/identity-providers', { signal })
  return (dtos ?? []).map(mapLinkedProvider)
}

/**
 * Generates a one-time link token after step-up verification. The token is then
 * consumed by navigating the browser to {@link buildLinkStartUrl} to begin the
 * provider OAuth flow.
 *
 * @param idpId - The identity-provider id to link.
 * @param input - The step-up credentials.
 * @returns The one-time link token.
 * @throws {HttpError} When the request fails (401 step-up, 409 already linked).
 */
export async function generateLinkToken(idpId: number, input: StepUpInput): Promise<string> {
  const dto = await apiFetch<LinkTokenDto>(`/profile/identity-providers/${idpId}/link/token`, {
    method: 'POST',
    body: JSON.stringify(toStepUpWire(input)),
  })
  return dto.token
}

/**
 * Builds the absolute backend URL that begins the provider OAuth link. The
 * browser is navigated here (full-page) with the one-time token; the backend
 * 307-redirects on to the provider's authorization page.
 *
 * The `returnPath` is captured on the backend's OAuth state and used to build
 * the final post-callback redirect, so the browser lands back on this exact
 * frontend route (carrying the `idp_link` result) instead of the legacy v1
 * default. It must be a relative path; the backend validates it against open
 * redirects.
 *
 * @param idpId - The identity-provider id being linked.
 * @param token - The one-time link token from {@link generateLinkToken}.
 * @param returnPath - The frontend route to return to after the callback.
 * @returns The absolute link-start URL.
 */
export function buildLinkStartUrl(
  idpId: number,
  token: string,
  returnPath = '/settings/security',
): string {
  const params = new URLSearchParams({ link_token: token, redirect: returnPath })
  return `${API_BASE_URL}/profile/identity-providers/${idpId}/link?${params.toString()}`
}

/**
 * Unlinks an identity provider after step-up verification. The backend rejects
 * the request (400) when this is the user's last authentication method and they
 * have no password set.
 *
 * @param idpId - The identity-provider id to unlink.
 * @param input - The step-up credentials.
 * @throws {HttpError} When the request fails (401 step-up, 400 last method).
 */
export async function unlinkProvider(idpId: number, input: StepUpInput): Promise<void> {
  await apiFetch(`/profile/identity-providers/${idpId}/unlink`, {
    method: 'POST',
    body: JSON.stringify(toStepUpWire(input)),
    responseType: 'void',
  })
}
