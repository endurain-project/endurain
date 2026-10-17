import type { ActivityIngestionJob } from '@/features/upload/types'
import { apiFetch } from '@/services/http'

/** Multipart form-field name every upload endpoint here expects. */
const UPLOAD_FIELD = 'file'

/**
 * How the files of a bulk import are laid out: plain activity files, or a
 * provider's own export. A closed set the server also validates.
 */
export type BulkImportSource = 'generic' | 'strava'

/**
 * Starts a bulk import of the files the user placed in their own folder on the
 * server. The folder is packed and staged in the background; the response is the
 * single job to poll for progress.
 *
 * @param source - The folder's layout.
 * @returns The accepted import job, in the pending state.
 * @throws {HttpError} `409` when an import is already running, `400` when the
 *   folder holds nothing importable.
 */
export async function bulkImportFromFolder(
  source: BulkImportSource,
): Promise<ActivityIngestionJob> {
  return apiFetch<ActivityIngestionJob>(`/activities/bulk-import/folder?source=${source}`, {
    method: 'POST',
  })
}

/**
 * Uploads a ZIP archive of activity files (or a provider export) for import.
 *
 * Resolves when the server has the archive, not when it is imported: the import
 * runs in batches on a worker and the returned job is polled for progress. The
 * original filename is only the multipart part name; the server names the stored
 * file itself.
 *
 * @param file - The ZIP archive.
 * @param source - The archive's layout.
 * @param options - Optional abort signal.
 * @returns The accepted import job, in the pending state.
 * @throws {HttpError} `409` when an import is already running, `400` when the
 *   archive holds nothing importable, `413` when it is too large.
 */
export async function bulkImportFromArchive(
  file: File,
  source: BulkImportSource,
  options: { signal?: AbortSignal } = {},
): Promise<ActivityIngestionJob> {
  const formData = new FormData()
  formData.append(UPLOAD_FIELD, file, file.name)
  return apiFetch<ActivityIngestionJob>(`/activities/bulk-import?source=${source}`, {
    method: 'POST',
    body: formData,
    signal: options.signal,
    // An archive can be hundreds of MiB; cancellation is the caller's signal.
    timeoutMs: 0,
  })
}

/**
 * Imports bikes from a Strava export's `bikes.csv` (completes synchronously).
 *
 * @param file - The CSV file.
 * @throws {HttpError} When the request fails (e.g. wrong headers).
 */
export async function importStravaBikes(file: File): Promise<void> {
  const formData = new FormData()
  formData.append(UPLOAD_FIELD, file, file.name)
  await apiFetch('/strava/import/bikes', { method: 'POST', body: formData, responseType: 'void' })
}

/**
 * Imports shoes from a Strava export's `shoes.csv` (completes synchronously).
 *
 * @param file - The CSV file.
 * @throws {HttpError} When the request fails (e.g. wrong headers).
 */
export async function importStravaShoes(file: File): Promise<void> {
  const formData = new FormData()
  formData.append(UPLOAD_FIELD, file, file.name)
  await apiFetch('/strava/import/shoes', { method: 'POST', body: formData, responseType: 'void' })
}
