import type { OnboardingRequest, OnboardingStatus } from '@/features/auth/types'
import type { Schemas } from '@/types'

import { apiFetch } from '@/services/http'

/**
 * Asks the backend whether the installation still needs its first administrator.
 *
 * @returns The onboarding status.
 * @throws {HttpError} When the request fails.
 */
export async function fetchOnboardingStatus(): Promise<OnboardingStatus> {
  const dto = await apiFetch<Schemas['OnboardingStatusRead']>('/public/onboarding', {
    auth: false,
    retryOnUnauthorized: false,
  })
  return { onboardingRequired: dto.onboarding_required }
}

/**
 * Creates the first administrator with the setup token printed in the server log.
 *
 * @param request - Setup token and the administrator's details.
 * @returns Resolves once the account exists.
 * @throws {HttpError} 400 when the token is invalid, expired or used, 409 when
 *   an account already exists, 422 when the details or password are rejected,
 *   429 when rate limited, 503 when token storage is unavailable.
 */
export async function completeOnboarding(request: OnboardingRequest): Promise<void> {
  await apiFetch<Schemas['UsersRead']>('/public/onboarding', {
    method: 'POST',
    body: JSON.stringify(request),
    auth: false,
    retryOnUnauthorized: false,
  })
}
