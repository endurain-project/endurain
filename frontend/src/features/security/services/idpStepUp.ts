import type { StepUpAction, StepUpStartDto, StepUpStartResultDto } from '@/features/security/types'

import { apiFetch } from '@/services/http'

/**
 * Starts a fresh sign-in with a linked identity provider, for an account
 * without a local password. The response also sets the cookie that binds the
 * sign-in to this browser.
 *
 * @param idpId - The linked identity-provider id to sign in with again.
 * @param action - The sensitive operation the sign-in authorises.
 * @param codeChallenge - The PKCE S256 challenge of the verifier kept in this browser.
 * @param redirect - The relative frontend path the provider's callback returns to.
 * @returns The identity provider's authorization URL.
 * @throws {HttpError} When the request fails (400 account has a password, 404 not linked, 429 locked out).
 */
export async function startIdpStepUp(
  idpId: number,
  action: StepUpAction,
  codeChallenge: string,
  redirect: string,
): Promise<string> {
  const payload: StepUpStartDto = { code_challenge: codeChallenge, action, redirect }
  const dto = await apiFetch<StepUpStartResultDto>(`/profile/identity-providers/${idpId}/step-up`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return dto.authorization_url
}
