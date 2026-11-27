import type { IdentityProviderPublic, SsoExchangeResponse } from '@/types'

import { apiFetch, API_BASE_URL } from './http'
import { fetchAllPages } from './pagination'

/**
 * Fetches every enabled public identity provider, without credentials.
 *
 * @returns Enabled SSO providers.
 * @throws {HttpError} When provider discovery fails.
 */
export function fetchEnabledIdentityProviders(): Promise<IdentityProviderPublic[]> {
  return fetchAllPages<IdentityProviderPublic>('/public/idp', undefined, {
    auth: false,
    retryOnUnauthorized: false,
  })
}

/**
 * Builds the backend SSO initiation URL for a provider.
 *
 * @param slug - Provider slug.
 * @param params - Encoded query parameters.
 * @returns Absolute SSO initiation URL.
 */
export function getIdentityProviderLoginUrl(slug: string, params: URLSearchParams): string {
  return `${API_BASE_URL}/public/idp/login/${encodeURIComponent(slug)}?${params.toString()}`
}

/**
 * Exchanges an SSO session and PKCE verifier for web tokens.
 *
 * @param sessionId - Session ID returned by the backend callback.
 * @param codeVerifier - PKCE code verifier stored before SSO redirect.
 * @returns The web token body, or the MFA step when the account has MFA enabled; its `next_step`
 *   says which.
 * @throws {HttpError} When the exchange fails.
 */
export function exchangeSessionForTokens(
  sessionId: string,
  codeVerifier: string,
): Promise<SsoExchangeResponse> {
  return apiFetch<SsoExchangeResponse>(`/auth/sessions/${encodeURIComponent(sessionId)}/tokens`, {
    method: 'POST',
    body: JSON.stringify({ code_verifier: codeVerifier }),
    auth: false,
    retryOnUnauthorized: false,
  })
}
