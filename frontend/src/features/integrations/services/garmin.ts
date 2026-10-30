import type {
  DateRange,
  GarminLoginDto,
  GarminLoginInput,
  GarminMfaDto,
} from '@/features/integrations/types'

import { apiFetch } from '@/services/http'

/** Above the backend MFA wait of 185 s (modules/garmin/utils.py). */
export const GARMIN_LINK_TIMEOUT_MS = 200_000

/**
 * Begins linking a Garmin Connect account. When the account has MFA enabled the
 * backend signals `MFA_REQUIRED` over the realtime channel and this request
 * stays pending until the code is supplied via {@link submitGarminMfa}.
 *
 * @param input - The Garmin Connect username and password.
 * @throws {HttpError} When authentication fails.
 */
export async function linkGarmin(input: GarminLoginInput): Promise<void> {
  const payload: GarminLoginDto = {
    username: input.username,
    password: input.password,
    // Garmin China (connect.garmin.cn) accounts authenticate against a separate
    // region; the dialog's toggle drives this flag.
    is_cn: input.isCn,
  }
  await apiFetch('/garminconnect/link', {
    method: 'POST',
    body: JSON.stringify(payload),
    responseType: 'void',
    // The request stays open while the backend waits up to 185 s for the MFA
    // code, so the default 30 s timeout would abort it mid-login.
    timeoutMs: GARMIN_LINK_TIMEOUT_MS,
  })
}

/**
 * Submits the Garmin Connect MFA code, unblocking a pending {@link linkGarmin}.
 *
 * @param code - The MFA code from the user's authenticator/SMS.
 * @throws {HttpError} When the request fails.
 */
export async function submitGarminMfa(code: string): Promise<void> {
  const payload: GarminMfaDto = { mfa_code: code }
  await apiFetch('/garminconnect/mfa', {
    method: 'POST',
    body: JSON.stringify(payload),
    responseType: 'void',
  })
}

/**
 * Kicks off a background import of Garmin Connect activities in the given window.
 *
 * @param range - The inclusive date window to import.
 * @throws {HttpError} When the request fails.
 */
export async function retrieveGarminActivities(range: DateRange): Promise<void> {
  await apiFetch(
    `/garminconnect/activities?start_date=${encodeURIComponent(range.startDate)}&end_date=${encodeURIComponent(range.endDate)}`,
    { responseType: 'void' },
  )
}

/**
 * Kicks off a background import of the user's Garmin Connect gear.
 *
 * @throws {HttpError} When the request fails.
 */
export async function retrieveGarminGear(): Promise<void> {
  await apiFetch('/garminconnect/gear', { responseType: 'void' })
}

/**
 * Kicks off a background import of Garmin Connect health data in the given window.
 *
 * @param range - The inclusive date window to import.
 * @throws {HttpError} When the request fails.
 */
export async function retrieveGarminHealth(range: DateRange): Promise<void> {
  await apiFetch(
    `/garminconnect/health?start_date=${encodeURIComponent(range.startDate)}&end_date=${encodeURIComponent(range.endDate)}`,
    { responseType: 'void' },
  )
}

/**
 * Disconnects the user's Garmin Connect account.
 *
 * @throws {HttpError} When the request fails.
 */
export async function unlinkGarmin(): Promise<void> {
  await apiFetch('/garminconnect/unlink', { method: 'DELETE', responseType: 'void' })
}
