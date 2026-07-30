import { apiFetch } from '@/services/http'
import { getBackendAssetUrl } from '@/services/runtime'

import type { ActivityMedia, ActivityMediaDto } from '../types'

/**
 * Maps a media DTO to the domain model. The backend returns a ready-to-use
 * `url` — a signed, token-gated app route on local storage or a presigned URL on
 * object storage — so the client never derives an image address itself.
 *
 * @param dto - The media wire payload.
 * @returns The media domain model.
 */
export function mapActivityMedia(dto: ActivityMediaDto): ActivityMedia {
  return {
    id: dto.id,
    activityId: dto.activity_id,
    url: getBackendAssetUrl(dto.url),
  }
}

/**
 * Fetches all media attached to an activity. Authenticated-only — there is no
 * public media endpoint.
 *
 * @param activityId - Activity identifier.
 * @param signal - Optional abort signal (e.g. TanStack Query cancellation).
 * @returns The activity's media, newest first as returned by the backend.
 */
export async function fetchActivityMedia(
  activityId: number,
  signal?: AbortSignal,
): Promise<ActivityMedia[]> {
  const dtos = await apiFetch<ActivityMediaDto[] | null>(`/activities/${activityId}/media`, {
    signal,
  })
  return (dtos ?? []).map(mapActivityMedia)
}

/**
 * Uploads an image file to an activity. The file is sent as multipart form data
 * (the browser sets the boundary) with no request timeout, since large images
 * can take a while. The backend validates the image by magic number and size.
 *
 * @param activityId - Activity the image belongs to.
 * @param file - The image file to upload.
 * @returns The newly created media record.
 * @throws {HttpError} When the upload or validation fails.
 */
export async function uploadActivityMedia(activityId: number, file: File): Promise<ActivityMedia> {
  const formData = new FormData()
  formData.append('file', file, file.name)
  const dto = await apiFetch<ActivityMediaDto>(`/activities/${activityId}/media`, {
    method: 'POST',
    body: formData,
    timeoutMs: 0,
  })
  return mapActivityMedia(dto)
}

/**
 * Deletes one photo from an activity (owner only); the backend also removes the
 * file from disk.
 *
 * @param activityId - Activity the photo belongs to.
 * @param mediaId - The media record id to delete.
 * @throws {HttpError} When the delete fails.
 */
export async function deleteActivityMedia(activityId: number, mediaId: number): Promise<void> {
  await apiFetch(`/activities/${activityId}/media/${mediaId}`, {
    method: 'DELETE',
    responseType: 'void',
  })
}
