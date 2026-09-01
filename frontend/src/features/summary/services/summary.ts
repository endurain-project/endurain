/**
 * Activity summary service — the DTO ↔ domain boundary for the `/summary` view.
 *
 * The backend exposes `GET /activities_summaries/{view_type}` returning one of
 * four response shapes (week/month/year/lifetime), each carrying period totals,
 * a sub-period `breakdown`, and an optional per-type `type_breakdown`. These
 * schemas are not part of the generated OpenAPI types, so the snake-cased DTOs
 * are declared here and mapped to the clean {@link ActivitySummary} model; the
 * DTO shapes never leave this module.
 */

import { apiFetch } from '@/services/http'

import type {
  ActivitySummary,
  SummaryBreakdownRow,
  SummaryTotals,
  SummaryTypeBreakdownRow,
  SummaryViewType,
} from '@/features/summary/types'

/** The metric fields shared by every summary response and breakdown row. */
interface SummaryMetricsDto {
  total_distance: number
  total_duration: number
  total_elevation_gain: number
  total_calories: number
  activity_count: number
}

/** A per-activity-type breakdown row. */
interface TypeBreakdownItemDto extends SummaryMetricsDto {
  activity_type_id: number
  activity_type: string
}

/** Week-view daily breakdown row (`day_of_week`: 0 = Monday … 6 = Sunday). */
interface DaySummaryDto extends SummaryMetricsDto {
  day_of_week: number
}

/** Month-view weekly breakdown row (`week_number`: configured calendar week). */
interface WeekSummaryDto extends SummaryMetricsDto {
  week_number: number
}

/** Year-view monthly breakdown row (`month_number`: 1–12). */
interface MonthSummaryDto extends SummaryMetricsDto {
  month_number: number
}

/** Lifetime-view yearly breakdown row (`year_number`: calendar year). */
interface YearlyPeriodSummaryDto extends SummaryMetricsDto {
  year_number: number
}

/** The union of breakdown row shapes across the four view types. */
type BreakdownItemDto = DaySummaryDto | WeekSummaryDto | MonthSummaryDto | YearlyPeriodSummaryDto

/** Any of the four summary responses (each carries its own breakdown shape). */
interface SummaryResponseDto extends SummaryMetricsDto {
  breakdown: BreakdownItemDto[] | null
  type_breakdown: TypeBreakdownItemDto[] | null
}

/** Filter inputs for a summary request; which apply depends on the view type. */
export interface ActivitySummaryParams {
  /** ISO `YYYY-MM-DD` date within the target week/month (week & month views). */
  date?: string | null
  /** Target calendar year (year view). */
  year?: number | null
  /** Activity-type name filter (the summary endpoint filters by name), or null. */
  typeName?: string | null
}

/** Extracts the view-type-specific sub-period index from a breakdown row. */
function bucketOf(viewType: SummaryViewType, row: BreakdownItemDto): number {
  switch (viewType) {
    case 'week':
      return (row as DaySummaryDto).day_of_week
    case 'month':
      return (row as WeekSummaryDto).week_number
    case 'year':
      return (row as MonthSummaryDto).month_number
    case 'lifetime':
      return (row as YearlyPeriodSummaryDto).year_number
  }
}

/** Maps the shared metric fields, defaulting any missing value to zero. */
function mapTotals(dto: SummaryMetricsDto): SummaryTotals {
  return {
    totalDistance: dto.total_distance ?? 0,
    totalDuration: dto.total_duration ?? 0,
    totalElevationGain: dto.total_elevation_gain ?? 0,
    totalCalories: dto.total_calories ?? 0,
    activityCount: dto.activity_count ?? 0,
  }
}

/**
 * Maps a raw summary response to the clean {@link ActivitySummary} model,
 * resolving each breakdown row's `bucket` from the view type.
 *
 * @param viewType - The requested view type (drives the breakdown bucket).
 * @param dto - The raw backend response.
 * @returns The normalized summary.
 */
export function mapActivitySummary(
  viewType: SummaryViewType,
  dto: SummaryResponseDto,
): ActivitySummary {
  const breakdown: SummaryBreakdownRow[] = (dto.breakdown ?? []).map((row) => ({
    ...mapTotals(row),
    bucket: bucketOf(viewType, row),
  }))
  const typeBreakdown: SummaryTypeBreakdownRow[] = (dto.type_breakdown ?? []).map((row) => ({
    ...mapTotals(row),
    activityType: row.activity_type_id,
    activityTypeName: row.activity_type,
  }))
  return { totals: mapTotals(dto), breakdown, typeBreakdown }
}

/** An all-zero summary response, returned when the backend yields no body. */
const EMPTY_RESPONSE: SummaryResponseDto = {
  total_distance: 0,
  total_duration: 0,
  total_elevation_gain: 0,
  total_calories: 0,
  activity_count: 0,
  breakdown: [],
  type_breakdown: [],
}

/**
 * Fetches an aggregated activity summary for the authenticated user. The query
 * parameters carried depend on the view type: `date` for week/month, `year` for
 * year, and an optional `type` name filter for all views.
 *
 * @param viewType - The period granularity (`week`/`month`/`year`/`lifetime`).
 * @param params - The date/year anchor and optional type-name filter.
 * @param signal - Optional abort signal for cancellation.
 * @returns The normalized summary for the period.
 * @throws {HttpError} When the request fails.
 */
export async function fetchActivitySummary(
  viewType: SummaryViewType,
  params: ActivitySummaryParams = {},
  signal?: AbortSignal,
): Promise<ActivitySummary> {
  const search = new URLSearchParams()
  if ((viewType === 'week' || viewType === 'month') && params.date) {
    search.set('date', params.date)
  }
  if (viewType === 'year' && params.year !== null && params.year !== undefined) {
    search.set('year', String(params.year))
  }
  const typeName = params.typeName?.trim()
  if (typeName) {
    search.set('type', typeName)
  }

  const query = search.toString()
  const path = query
    ? `/activities_summaries/${viewType}?${query}`
    : `/activities_summaries/${viewType}`

  const dto = await apiFetch<SummaryResponseDto | null>(path, { signal })
  return mapActivitySummary(viewType, dto ?? EMPTY_RESPONSE)
}
