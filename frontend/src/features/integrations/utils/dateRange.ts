import type { DateRange } from '@/features/integrations/types'

import { todayIsoDate } from '@/utils/datetime'

/**
 * Formats a `Date` as a `YYYY-MM-DD` string using its **local** calendar fields.
 *
 * Reading UTC fields here mixed frames with the local `setDate()` arithmetic
 * below, and made the window exclude today for viewers east of UTC (and include
 * a day that has not happened for those far west).
 */
function toIsoDate(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

/**
 * Builds an inclusive date window spanning the last `days` days up to today,
 * mirroring the v1 "retrieve last N days" option.
 *
 * @param days - Number of days back from today the window should start.
 * @returns The `{ startDate, endDate }` window as `YYYY-MM-DD` strings.
 */
export function daysAgoRange(days: number): DateRange {
  const end = new Date()
  const start = new Date()
  start.setDate(end.getDate() - days)
  return { startDate: toIsoDate(start), endDate: todayIsoDate() }
}
