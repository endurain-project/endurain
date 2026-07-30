import type { Schemas } from '@/types'

/**
 * An activity created by the backend from an uploaded fitness file. Derived
 * from the generated `Activity` schema (see {@link Schemas}) so a backend
 * contract change surfaces here as a TypeScript error rather than a silent
 * runtime mismatch.
 */
export type Activity = Schemas['Activity']

/**
 * A queued activity-file import. The upload endpoint answers `202` with this
 * handle rather than the parsed activities, because parsing runs on a
 * background worker; the client polls until it reaches a terminal state.
 */
export type ActivityIngestionJob = Schemas['ActivityIngestionJob']

/** Lifecycle state of an {@link ActivityIngestionJob}. */
export type IngestionJobStatus = ActivityIngestionJob['status']

/** Sanitized reason a background import failed. */
export type IngestionJobErrorCode = NonNullable<ActivityIngestionJob['error_code']>

/**
 * Statuses that will not change again, so polling can stop.
 */
export const TERMINAL_INGESTION_STATUSES = ['completed', 'failed'] as const

/**
 * Whether an upload job has reached a state it will not leave.
 *
 * @param job - The job to inspect.
 * @returns `true` when the job is finished, successfully or not.
 */
export function isTerminalIngestionJob(job: ActivityIngestionJob): boolean {
  return (TERMINAL_INGESTION_STATUSES as readonly string[]).includes(job.status)
}

/**
 * Accepted activity-file extensions, mirroring the backend's `ACTIVITY` and
 * `GZIP` upload kinds (`backend/app/core/file_uploads.py`).
 *
 * Security note: this is a client-side convenience allowlist for fail-fast UX
 * only. The backend re-validates every upload by magic number, size, and
 * decompression-bomb limits and is the authoritative gate — a client-side pass
 * is never trusted.
 */
export const ACTIVITY_FILE_EXTENSIONS = ['gpx', 'tcx', 'fit', 'gz'] as const

/** A single accepted activity-file extension. */
export type ActivityFileExtension = (typeof ACTIVITY_FILE_EXTENSIONS)[number]

/**
 * Maximum activity-file size accepted client-side, mirroring the backend
 * `_MAX_ACTIVITY_BYTES` ceiling (200 MiB). Rejecting oversized files before
 * upload avoids a doomed multi-hundred-MiB round-trip; the backend enforces the
 * real limit.
 */
export const MAX_ACTIVITY_FILE_BYTES = 200 * 1024 * 1024

/** Machine-readable reason a client-side upload pre-check rejected a file. */
export type UploadValidationCode = 'empty' | 'extension' | 'size'

/**
 * Error thrown by client-side upload validation. Carries a machine-readable
 * {@link UploadValidationCode} so the UI can map it to a localized message
 * instead of parsing the human-readable string.
 */
export class UploadValidationError extends Error {
  /**
   * @param code - Why validation failed.
   * @param message - Human-readable diagnostic (developer/log oriented).
   */
  constructor(
    readonly code: UploadValidationCode,
    message: string,
  ) {
    super(message)
    this.name = 'UploadValidationError'
  }
}
