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
