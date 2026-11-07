import type {
  SignUpConfirm,
  SignUpRequest,
  SignUpResend,
  SignUpResponse,
} from '@/features/auth/types'

import { apiFetch } from '@/services/http'

/**
 * Submits a self-service sign-up request.
 *
 * @param request - The new account's details.
 * @returns The backend response, including verification/approval flags.
 * @throws {HttpError} When sign-up is disabled (403), the username is
 *   already taken (409), validation fails (400/422), or the request fails.
 */
export function requestSignUp(request: SignUpRequest): Promise<SignUpResponse> {
  return apiFetch<SignUpResponse>('/public/sign-up/request', {
    method: 'POST',
    body: JSON.stringify(request),
    auth: false,
    retryOnUnauthorized: false,
  })
}

/**
 * Confirms a sign-up by verifying the emailed token.
 *
 * @param request - The email verification token and, for a sign-up link, the chosen password
 *   (sent after the backend answered `urn:endurain:error:password-required`).
 * @returns The backend response, including any admin-approval flag.
 * @throws {HttpError} 412 when verification is disabled, 400 when the token is
 *   invalid or expired or a password is required, 404 when no matching user
 *   exists, 422 when the password fails the policy.
 */
export function confirmSignUp(request: SignUpConfirm): Promise<SignUpResponse> {
  return apiFetch<SignUpResponse>('/public/sign-up/confirm', {
    method: 'POST',
    body: JSON.stringify(request),
    auth: false,
    retryOnUnauthorized: false,
  })
}

/**
 * Asks for a sign-up's verification email to be sent again. The backend answers
 * the same whether or not the address is awaiting verification.
 *
 * @param request - The address the sign-up used.
 * @returns The backend's fixed acknowledgement.
 * @throws {HttpError} 422 when the address is malformed, 429 when rate limited.
 */
export function resendSignUpVerification(request: SignUpResend): Promise<SignUpResponse> {
  return apiFetch<SignUpResponse>('/public/sign-up/resend', {
    method: 'POST',
    body: JSON.stringify(request),
    auth: false,
    retryOnUnauthorized: false,
  })
}
