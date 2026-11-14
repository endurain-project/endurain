import type { AuthTokenResponse } from '@/types'

/** Raised when a token-bearing answer is not a web token answer this client can use. */
export class UnsupportedTokenAnswerError extends Error {
  constructor() {
    super('The answer is not a web token answer')
    this.name = 'UnsupportedTokenAnswerError'
  }
}

/**
 * Checks that an answer carries web tokens: `next_step` is `tokens` and the access token is present. The
 * web client sends `X-Client-Type: web`, so a body that carries a refresh token is a mobile answer that
 * never belongs in the SPA.
 *
 * @param answer - Answer of a login, refresh, restore or SSO exchange request.
 * @returns Whether the answer is a usable web token answer.
 */
export function isWebTokenAnswer(answer: unknown): answer is AuthTokenResponse {
  if (typeof answer !== 'object' || answer === null) {
    return false
  }
  const body = answer as Record<string, unknown>
  return (
    body.next_step === 'tokens' &&
    typeof body.access_token === 'string' &&
    body.access_token !== '' &&
    !('refresh_token' in body)
  )
}

let accessToken: string | null = null

/**
 * Returns the current in-memory bearer access token.
 *
 * @returns The access token, or `null` when unauthenticated.
 */
export function getAccessToken(): string | null {
  return accessToken
}

/**
 * Stores auth tokens in memory only.
 *
 * @param nextAccessToken - Bearer token returned by the backend.
 */
export function setAuthTokens(nextAccessToken: string): void {
  accessToken = nextAccessToken
}

/**
 * Clears all in-memory auth tokens.
 */
export function clearAuthTokens(): void {
  accessToken = null
}
