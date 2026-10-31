import type { IdentityProviderPublic, SsoTokenExchangeResponse } from '@/types'

import { apiFetch, API_BASE_URL } from './http'

/**
 * Fetches enabled public identity providers.
 *
 * @returns Enabled SSO providers.
 * @throws {HttpError} When provider discovery fails.
 */
export function fetchEnabledIdentityProviders(): Promise<IdentityProviderPublic[]> {
  return apiFetch<IdentityProviderPublic[]>('/public/idp', {
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
 * @param mfaCode - TOTP or backup code, sent when the account has MFA enabled.
 * @returns Token exchange response.
 * @throws {HttpError} When the exchange fails; the `mfa-required` problem type
 *   means the account needs `mfaCode`.
 */
export function exchangeSessionForTokens(
  sessionId: string,
  codeVerifier: string,
  mfaCode?: string,
): Promise<SsoTokenExchangeResponse> {
  return apiFetch<SsoTokenExchangeResponse>(
    `/public/idp/session/${encodeURIComponent(sessionId)}/tokens`,
    {
      method: 'POST',
      body: JSON.stringify({ code_verifier: codeVerifier, mfa_code: mfaCode }),
      auth: false,
      retryOnUnauthorized: false,
    },
  )
}
