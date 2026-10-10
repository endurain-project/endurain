import type { GearActivitiesPage, GearActivity, GearActivityDto } from '@/features/gears/types'
import type { Schemas } from '@/types'

import { apiFetch } from '@/services/http'

/** Pagination input for an activities-for-a-gear request. */
export interface GearActivitiesListParams {
  /** 1-based page number. */
  page: number
  /** Page size (records per page). */
  numRecords: number
}

/**
 * Maps a raw `Activity` payload to the trimmed {@link GearActivity} model used
 * by the read-only gear-detail list.
 *
 * @param dto - Raw activity payload from the backend.
 * @returns The normalized, trimmed activity model.
 */
export function mapGearActivity(dto: GearActivityDto): GearActivity {
  return {
    id: dto.id ?? 0,
    name: dto.name,
    activityType: dto.activity_type,
    // The raw UTC instant plus the recording timezone, matching the main
    // activities list, so the row renders in the timezone the activity happened
    // in rather than the viewer's.
    startTime: dto.start_time ?? null,
    timezone: dto.timezone ?? null,
    distance: dto.distance,
    totalTimerTime: dto.total_timer_time ?? null,
  }
}

/**
 * Fetches one page of the activities recorded against a gear.
 *
 * @param gearId - The parent gear id.
 * @param params - Page number and size.
 * @param signal - Optional abort signal so TanStack Query can cancel the
 *   request on unmount or invalidation.
 * @returns The page's activities (mapped) plus the total record count.
 * @throws {HttpError} When the request fails.
 */
export async function fetchGearActivities(
  gearId: number,
  { page, numRecords }: GearActivitiesListParams,
  signal?: AbortSignal,
): Promise<GearActivitiesPage> {
  const params = new URLSearchParams({
    page_number: String(page),
    num_records: String(numRecords),
  })
  const page_ = await apiFetch<Schemas['Page_Activity_']>(
    `/activities/gears/${gearId}?${params.toString()}`,
    { signal },
  )
  return {
    records: (page_.items ?? []).map((dto) => mapGearActivity(dto as GearActivityDto)),
    total: page_.total,
  }
}
