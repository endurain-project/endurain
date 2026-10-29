import type { SignUpRequest, SignUpResponse } from '@/features/auth/types'

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
  return apiFetch<SignUpResponse>('/sign-up/request', {
    method: 'POST',
    body: JSON.stringify(request),
    auth: false,
    retryOnUnauthorized: false,
  })
}

interface SignUpConfirm {
  token: string
}

/**
 * Confirms a sign-up by verifying the emailed token.
 *
 * @param request - The email verification token.
 * @returns The backend response, including any admin-approval flag.
 * @throws {HttpError} 412 when verification is disabled, 400 when the token is
 *   invalid or expired, 404 when no matching user exists.
 */
export function confirmSignUp(request: SignUpConfirm): Promise<SignUpResponse> {
  return apiFetch<SignUpResponse>('/sign-up/confirm', {
    method: 'POST',
    body: JSON.stringify(request),
    auth: false,
    retryOnUnauthorized: false,
  })
}
