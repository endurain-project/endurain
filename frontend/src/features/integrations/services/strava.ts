import type {
  ActivityRefreshJob,
  DateRange,
  StravaClientDto,
  StravaClientInput,
  StravaLinkDto,
  StravaStateDto,
  StravaSyncStatus,
} from '@/features/integrations/types'

import { followJob, JobTimeoutError } from '@/services/jobStatus'
import { ifMatchHeaders } from '@/services/ifMatch'
import { apiFetch } from '@/services/http'
import { getRuntimeBackendHost } from '@/services/runtime'

/** The OAuth scopes Endurain requests from Strava (read-only access). */
const STRAVA_SCOPE = 'read,profile:read_all,activity:read_all'

/** The problem type the server answers a link with when Strava granted fewer scopes than requested. */
export const STRAVA_SCOPE_INSUFFICIENT_TYPE = 'urn:endurain:error:provider-scope-insufficient'

/** How often the status of a queued Strava link or unlink is read. */
const STRAVA_SYNC_POLL_MS = 1_000

/** How long to follow a queued Strava link or unlink before giving up on it. */
const STRAVA_SYNC_TIMEOUT_MS = 120_000

/**
 * Follows a queued Strava job (link or unlink) until it finishes.
 *
 * @param queued - The 202 body of the request that queued the job.
 * @param label - The job's name, for the error message.
 * @throws {Error} When the job fails on the server or does not finish in time.
 */
async function followStravaSync(queued: StravaSyncStatus, label: string): Promise<void> {
  let job: StravaSyncStatus
  try {
    job = await followJob<StravaSyncStatus['kind']>(queued.id, {
      intervalMs: STRAVA_SYNC_POLL_MS,
      timeoutMs: STRAVA_SYNC_TIMEOUT_MS,
    })
  } catch (error) {
    throw error instanceof JobTimeoutError
      ? new Error(`${label} Strava did not finish in time`)
      : error
  }
  if (job.status === 'failed') {
    throw new Error(`${label} Strava failed`)
  }
}

/**
 * Asks the server for a one-time CSRF `state` that correlates the OAuth callback back to this
 * account. The server generates it, keeps it briefly and accepts it once.
 *
 * @returns The opaque state to send to Strava.
 * @throws {HttpError} When the request fails.
 */
export async function beginStravaState(): Promise<string> {
  const { state } = await apiFetch<StravaStateDto>('/strava/state', { method: 'POST' })
  return state
}

/**
 * Stores the user's Strava API client id + secret ahead of the OAuth round-trip.
 *
 * @param input - The Strava application's client id and secret.
 * @param version - The integrations version the profile was read at, for `If-Match`.
 * @throws {HttpError} When the request fails, including 412 when the integrations changed meanwhile.
 */
export async function setStravaClient(input: StravaClientInput, version: number): Promise<void> {
  const payload: StravaClientDto = {
    client_id: input.clientId,
    client_secret: input.clientSecret,
  }
  await apiFetch('/strava/client', {
    method: 'PUT',
    headers: ifMatchHeaders(version),
    body: JSON.stringify(payload),
    responseType: 'void',
  })
}

/**
 * Builds the Strava OAuth authorization URL the browser is sent to (full-page).
 * Strava redirects back to `{host}/strava/callback` with `code` + `state`.
 *
 * @param state - The CSRF state previously stored via {@link beginStravaState}.
 * @param clientId - The Strava application's client id.
 * @returns The absolute Strava authorize URL.
 */
export function buildStravaAuthUrl(state: string, clientId: number): string {
  const host = getRuntimeBackendHost() ?? window.location.origin
  const redirectUri = encodeURIComponent(`${host}/strava/callback`)
  return (
    `https://www.strava.com/oauth/authorize?client_id=${clientId}` +
    `&response_type=code&redirect_uri=${redirectUri}&approval_prompt=force` +
    `&scope=${STRAVA_SCOPE}&state=${encodeURIComponent(state)}`
  )
}

/**
 * Completes the Strava link by exchanging the OAuth `code` for tokens. Called
 * from the `/strava/callback` view after Strava redirects back. The server queues the
 * exchange, so this follows the queued job until it finishes.
 *
 * @param state - The state echoed back by Strava.
 * @param code - The authorization code from Strava.
 * @param scope - The comma-separated scopes Strava reports as granted.
 * @throws {HttpError} When the request is refused (e.g. an invalid state, a link already running, or
 *   a grant missing a required scope, which has type {@link STRAVA_SCOPE_INSUFFICIENT_TYPE}).
 * @throws {Error} When the exchange fails on the server or does not finish in time.
 */
export async function completeStravaLink(
  state: string,
  code: string,
  scope: string,
): Promise<void> {
  const payload: StravaLinkDto = { state, code, scope }
  const queued = await apiFetch<StravaSyncStatus>('/strava/link', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  await followStravaSync(queued, 'Linking')
}

/**
 * Kicks off a background import of Strava activities in the given date window.
 *
 * @param range - The inclusive date window to import.
 * @returns The queued sync job.
 * @throws {HttpError} When the request fails.
 */
export async function retrieveStravaActivities(range: DateRange): Promise<ActivityRefreshJob> {
  return apiFetch<ActivityRefreshJob>(
    `/strava/activities?start_date=${encodeURIComponent(range.startDate)}&end_date=${encodeURIComponent(range.endDate)}`,
    { method: 'POST' },
  )
}

/**
 * Kicks off a background import of the user's Strava gear.
 *
 * @returns The queued sync job.
 * @throws {HttpError} When the request fails, including 409 while a gear sync is running.
 */
export async function retrieveStravaGear(): Promise<StravaSyncStatus> {
  return apiFetch<StravaSyncStatus>('/strava/gear', { method: 'POST' })
}

/**
 * Disconnects the user's Strava account. The server queues the unlink, because it revokes the
 * authorization with Strava and deletes what was imported from it, so this follows the queued
 * job until it finishes.
 *
 * @throws {HttpError} When the request fails.
 * @throws {Error} When the unlink fails on the server or does not finish in time.
 */
export async function unlinkStrava(): Promise<void> {
  const queued = await apiFetch<StravaSyncStatus>('/strava/link', { method: 'DELETE' })
  await followStravaSync(queued, 'Unlinking')
}
