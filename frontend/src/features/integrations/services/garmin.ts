import type {
  DateRange,
  GarminLinkStatus,
  GarminLoginDto,
  GarminLoginInput,
  GarminMfaDto,
} from '@/features/integrations/types'

import { apiFetch } from '@/services/http'

/**
 * Starts linking a Garmin Connect account. The login runs in the background, so this
 * returns at once; follow it with {@link fetchGarminLinkStatus}. When the account has MFA
 * the status turns `mfa_required` and the code goes through {@link submitGarminMfa}.
 *
 * @param input - The Garmin Connect username and password.
 * @returns The attempt's initial status (`pending`).
 * @throws {HttpError} When the request fails, including 409 while another link is running.
 */
export async function linkGarmin(input: GarminLoginInput): Promise<GarminLinkStatus> {
  const payload: GarminLoginDto = {
    username: input.username,
    password: input.password,
    // Garmin China (connect.garmin.cn) accounts authenticate against a separate
    // region; the dialog's toggle drives this flag.
    is_cn: input.isCn,
  }
  return apiFetch<GarminLinkStatus>('/garminconnect/link', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

/**
 * Reads where the Garmin Connect link attempt is. The state lives on the server, so any
 * backend replica answers it and nothing depends on a realtime push arriving.
 *
 * @param signal - Optional abort signal for cancellation.
 * @returns The attempt's status, with the failure reason once it has failed.
 * @throws {HttpError} When the request fails, including 404 once no attempt is recorded.
 */
export async function fetchGarminLinkStatus(signal?: AbortSignal): Promise<GarminLinkStatus> {
  return apiFetch<GarminLinkStatus>('/garminconnect/link/status', { signal })
}

/**
 * Submits the Garmin Connect MFA code the link attempt asked for.
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
    { method: 'POST', responseType: 'void' },
  )
}

/**
 * Kicks off a background import of the user's Garmin Connect gear.
 *
 * @throws {HttpError} When the request fails.
 */
export async function retrieveGarminGear(): Promise<void> {
  await apiFetch('/garminconnect/gear', { method: 'POST', responseType: 'void' })
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
    { method: 'POST', responseType: 'void' },
  )
}

/**
 * Disconnects the user's Garmin Connect account.
 *
 * @throws {HttpError} When the request fails.
 */
export async function unlinkGarmin(): Promise<void> {
  await apiFetch('/garminconnect/link', { method: 'DELETE', responseType: 'void' })
}
