import { apiFetch } from '@/services/http'

/**
 * Triggers a server-side bulk import of plain activity files placed in the
 * backend's `data/activity_files/bulk_import` folder. The work runs in the
 * background; progress arrives over the realtime channel.
 *
 * @throws {HttpError} When the request fails.
 */
export async function bulkImportActivities(): Promise<void> {
  await apiFetch('/activities/bulk-import', { method: 'POST', responseType: 'void' })
}

/**
 * Queues a server-side import of activities from a Strava bulk export placed in
 * the backend's `data/activity_files/strava_import` folder (background work).
 *
 * @throws {HttpError} When the request fails.
 */
export async function importStravaActivities(): Promise<void> {
  await apiFetch('/strava/import/activities', { method: 'POST', responseType: 'void' })
}

/**
 * Imports bikes from a Strava bulk export's gear CSV (completes synchronously).
 *
 * @throws {HttpError} When the request fails.
 */
export async function importStravaBikes(): Promise<void> {
  await apiFetch('/strava/import/bikes', { method: 'POST', responseType: 'void' })
}

/**
 * Imports shoes from a Strava bulk export's gear CSV (completes synchronously).
 *
 * @throws {HttpError} When the request fails.
 */
export async function importStravaShoes(): Promise<void> {
  await apiFetch('/strava/import/shoes', { method: 'POST', responseType: 'void' })
}
