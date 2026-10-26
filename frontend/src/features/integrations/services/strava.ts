import type {
  DateRange,
  StravaClientDto,
  StravaClientInput,
  StravaLinkDto,
  StravaStateDto,
  StravaSyncStatus,
} from '@/features/integrations/types'

import { apiFetch } from '@/services/http'
import { getRuntimeBackendHost } from '@/services/runtime'

/** The OAuth scopes Endurain requests from Strava (read-only access). */
const STRAVA_SCOPE = 'read,read_all,profile:read_all,activity:read,activity:read_all'

/** How often the status of a queued Strava link or unlink is read. */
const STRAVA_SYNC_POLL_MS = 1_000

/** How many status reads to make before giving up on a queued Strava link or unlink. */
const STRAVA_SYNC_MAX_POLLS = 120

/**
 * Follows a queued Strava job (`link` or `unlink`) until it finishes.
 *
 * @param kind - Which job to follow.
 * @param status - The status the request that queued it answered with.
 * @param label - The job's name, for the error message.
 * @throws {Error} When the job fails on the server or does not finish in time.
 */
async function followStravaSync(
  kind: StravaSyncStatus['kind'],
  status: StravaSyncStatus,
  label: string,
): Promise<void> {
  for (let poll = 0; poll < STRAVA_SYNC_MAX_POLLS; poll++) {
    if (status.status === 'completed') {
      return
    }
    if (status.status === 'failed') {
      throw new Error(`${label} Strava failed`)
    }
    await new Promise((resolve) => setTimeout(resolve, STRAVA_SYNC_POLL_MS))
    status = await apiFetch<StravaSyncStatus>(`/strava/sync/${kind}`)
  }
  throw new Error(`${label} Strava did not finish in time`)
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
 * Forgets the user's pending OAuth state.
 *
 * @throws {HttpError} When the request fails.
 */
export async function clearStravaState(): Promise<void> {
  await apiFetch('/strava/state', { method: 'DELETE', responseType: 'void' })
}

/**
 * Stores the user's Strava API client id + secret ahead of the OAuth round-trip.
 *
 * @param input - The Strava application's client id and secret.
 * @throws {HttpError} When the request fails.
 */
export async function setStravaClient(input: StravaClientInput): Promise<void> {
  const payload: StravaClientDto = {
    client_id: input.clientId,
    client_secret: input.clientSecret,
  }
  await apiFetch('/strava/client', {
    method: 'PUT',
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
 * @throws {HttpError} When the request is refused (e.g. an invalid state, or a link already running).
 * @throws {Error} When the exchange fails on the server or does not finish in time.
 */
export async function completeStravaLink(state: string, code: string): Promise<void> {
  const payload: StravaLinkDto = { state, code }
  const status = await apiFetch<StravaSyncStatus>('/strava/link', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  await followStravaSync('link', status, 'Linking')
}

/**
 * Kicks off a background import of Strava activities in the given date window.
 * The work runs server-side; progress arrives over the realtime channel.
 *
 * @param range - The inclusive date window to import.
 * @throws {HttpError} When the request fails.
 */
export async function retrieveStravaActivities(range: DateRange): Promise<void> {
  await apiFetch(
    `/strava/activities?start_date=${encodeURIComponent(range.startDate)}&end_date=${encodeURIComponent(range.endDate)}`,
    { method: 'POST', responseType: 'void' },
  )
}

/**
 * Kicks off a background import of the user's Strava gear.
 *
 * @throws {HttpError} When the request fails.
 */
export async function retrieveStravaGear(): Promise<void> {
  await apiFetch('/strava/gear', { method: 'POST', responseType: 'void' })
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
  const status = await apiFetch<StravaSyncStatus>('/strava/link', { method: 'DELETE' })
  await followStravaSync('unlink', status, 'Unlinking')
}
