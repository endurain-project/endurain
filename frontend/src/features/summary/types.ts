/**
 * Domain models for the activity summary feature (the `/summary` view). These
 * are the clean, camel-cased shapes the views and components consume; the
 * snake-cased backend DTOs live in `services/summary.ts` and never escape it.
 */

/** The summary period granularity, matching the backend `view_type` path param. */
export type SummaryViewType = 'week' | 'month' | 'year' | 'lifetime'

/**
 * Aggregated totals for a summary period. All quantities are stored in SI base
 * units (metres, seconds); formatting to the user's unit system happens in the
 * components via the summary formatters.
 */
export interface SummaryTotals {
  /** Total distance, in metres. */
  totalDistance: number
  /** Total moving/timer duration, in seconds. */
  totalDuration: number
  /** Total elevation gain, in metres. */
  totalElevationGain: number
  /** Total calories burned. */
  totalCalories: number
  /** Number of activities in the period. */
  activityCount: number
}

/**
 * One row of a period breakdown. The meaning of {@link SummaryBreakdownRow.bucket}
 * depends on the view type:
 * - `week` → day of week, `0` = Monday … `6` = Sunday
 * - `month` → configured calendar week number within the month
 * - `year` → month number, `1` = January … `12` = December
 * - `lifetime` → calendar year
 */
export interface SummaryBreakdownRow extends SummaryTotals {
  /** Sub-period index; its meaning depends on the view type (see above). */
  bucket: number
}

/** One row of the per-activity-type breakdown. */
export interface SummaryTypeBreakdownRow extends SummaryTotals {
  /** Numeric activity-type code. */
  activityType: number
  /** Backend activity-type name (used only as a fallback label). */
  activityTypeName: string
}

/** A complete activity summary for one view type, period, and optional type filter. */
export interface ActivitySummary {
  /** The totals across the whole period. */
  totals: SummaryTotals
  /** Sub-period breakdown rows, in chronological order. */
  breakdown: SummaryBreakdownRow[]
  /**
   * Per-activity-type breakdown, ordered by activity count descending. Empty
   * when the summary is already filtered to a single activity type.
   */
  typeBreakdown: SummaryTypeBreakdownRow[]
}
