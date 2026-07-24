import {
  ACTIVITY_FILE_EXTENSIONS,
  type Activity,
  type ActivityFileExtension,
  MAX_ACTIVITY_FILE_BYTES,
  UploadValidationError,
} from '@/features/upload/types'
import { apiFetch } from '@/services/http'

/** Multipart form-field name the backend upload endpoint expects. */
const UPLOAD_FIELD = 'file'

/** Activity-file upload endpoint, relative to the API base URL. */
const UPLOAD_PATH = '/activities/upload'

/**
 * Extracts a lowercase extension from a filename for the allowlist check.
 *
 * Security: the returned value is compared ONLY against
 * {@link ACTIVITY_FILE_EXTENSIONS}. It is never used to build a request path,
 * storage key, or filesystem path, so a hostile filename
 * (e.g. `../../etc/passwd.gpx`) cannot influence where anything is read or
 * written — the backend owns storage naming.
 *
 * @param filename - The user-supplied `File.name`.
 * @returns The lowercased extension without the leading dot, or `''` when none.
 */
function getExtension(filename: string): string {
  const dot = filename.lastIndexOf('.')
  return dot >= 0 ? filename.slice(dot + 1).toLowerCase() : ''
}

/**
 * Validates an activity file before upload — a fast, client-side allowlist
 * check mirroring the backend's `validate_upload` contract for the
 * `ACTIVITY`/`GZIP` kinds.
 *
 * Defense-in-depth and UX only: it rejects obviously-wrong files without a
 * network round-trip, but the backend re-validates every byte (magic number,
 * size, decompression bombs) and is the authoritative gate. Never treat a
 * client-side pass as trusted.
 *
 * @param file - The file selected by the user.
 * @throws {UploadValidationError} When the file is empty, has a disallowed
 *   extension, or exceeds {@link MAX_ACTIVITY_FILE_BYTES}.
 */
export function assertValidActivityFile(file: File): void {
  if (file.size === 0) {
    throw new UploadValidationError('empty', 'The selected file is empty.')
  }

  const extension = getExtension(file.name)
  if (!ACTIVITY_FILE_EXTENSIONS.includes(extension as ActivityFileExtension)) {
    throw new UploadValidationError(
      'extension',
      `Unsupported file type. Accepted: ${ACTIVITY_FILE_EXTENSIONS.join(', ')}.`,
    )
  }

  if (file.size > MAX_ACTIVITY_FILE_BYTES) {
    throw new UploadValidationError('size', 'The selected file is too large.')
  }
}

/**
 * Uploads a single activity file (GPX/TCX/FIT/GZ) and returns the activities
 * the backend parsed from it.
 *
 * The reference upload pattern — security-sensitive:
 *
 * - Pre-validates with {@link assertValidActivityFile} (fail-fast UX; the
 *   backend is the real validator).
 * - Sends `multipart/form-data` via {@link FormData}. {@link apiFetch} leaves
 *   `Content-Type` unset for a `FormData` body so the browser adds the
 *   multipart boundary, and attaches the bearer token + CSRF header.
 * - The original filename travels only as the multipart part name. The server
 *   generates the stored filename (`save_validated_upload`), so the client
 *   filename is never used to build a URL, storage key, or path.
 * - Disables the default request timeout (`timeoutMs: 0`): a legitimate large
 *   upload can exceed the 30s API default, so cancellation is delegated to the
 *   caller-supplied {@link AbortSignal} instead.
 *
 * @param file - The activity file to upload.
 * @param options - Optional abort signal for cancellation (e.g. on unmount).
 * @returns The list of activities created from the file.
 * @throws {UploadValidationError} When client-side validation fails (no request
 *   is sent).
 * @throws {HttpError} When the server rejects or fails the upload.
 */
export async function uploadActivityFile(
  file: File,
  options: { signal?: AbortSignal } = {},
): Promise<Activity[]> {
  assertValidActivityFile(file)

  const formData = new FormData()
  // The third argument is the multipart part filename only; it is not used to
  // construct any server path. The backend sanitizes the name and generates its
  // own storage filename.
  formData.append(UPLOAD_FIELD, file, file.name)

  return apiFetch<Activity[]>(UPLOAD_PATH, {
    method: 'POST',
    body: formData,
    signal: options.signal,
    timeoutMs: 0,
  })
}
