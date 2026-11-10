import type {
  EmailChangeConfirm,
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
 * @returns The backend response; `next_step` is `check_email`, `await_approval` or `sign_in`.
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
 * Confirms a sign-up with the token of its emailed link and the chosen password.
 *
 * @param request - The emailed token and the password the user chose.
 * @returns The backend response; `next_step` is `sign_in` or `await_approval`.
 * @throws {HttpError} 403 (`urn:endurain:error:email-verification-disabled`) when verification is
 *   disabled, 400 when the token is unknown, used, expired or not a sign-up token, 404 when no
 *   matching user exists, 422 when the password fails the policy.
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
 * Confirms an email change with the token of the link emailed to the new address.
 *
 * @param request - The emailed token.
 * @returns The backend response; `next_step` is `sign_in`.
 * @throws {HttpError} 400 when the token is unknown, used, expired, not an email-change token or
 *   predates a security change, 409 when another account holds the address now.
 */
export function confirmEmailChange(request: EmailChangeConfirm): Promise<SignUpResponse> {
  return apiFetch<SignUpResponse>('/public/email-change/confirm', {
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
 * @returns The backend's fixed answer, `next_step: check_email`.
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
