import { HttpError } from '@/services/http'

/**
 * Builds the `If-Match` header that makes a write to a versioned resource conditional on the
 * version the caller read. The backend refuses a write without it (428) and a stale one (412), so
 * every mutation of a versioned resource sends it.
 *
 * @param version - The row version the caller's copy was read at.
 * @returns The headers to merge into the request.
 */
export function ifMatchHeaders(version: number): { 'If-Match': string } {
  return { 'If-Match': `"${version}"` }
}

/**
 * Reads the version a record was served at. The backend always sends it. A missing one becomes 0,
 * which no stored version equals, so the write is refused with 412 instead of overwriting.
 *
 * @param version - The `version` field of a record payload.
 * @returns The version to send back in `If-Match`.
 */
export function rowVersion(version: number | null | undefined): number {
  return version ?? 0
}

/**
 * Whether a failed write was refused because the caller's copy is out of date. A 412 on a
 * versioned resource only ever means the `If-Match` version no longer matches, so the caller
 * should refetch the record and tell the user nothing was saved.
 *
 * @param error - The error a write rejected with.
 * @returns True for a 412 `HttpError`.
 */
export function isStaleWrite(error: unknown): boolean {
  return error instanceof HttpError && error.status === 412
}
