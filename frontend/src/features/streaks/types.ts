/**
 * Weekly streak domain types.
 *
 * A week "counts" toward the streak when it holds at least
 * `minActivitiesPerWeek` activities of the selected types. The backend owns the
 * calculation; these are the clean, camel-cased models the UI consumes. The raw
 * snake_case DTOs live here too, derived from the generated OpenAPI schemas,
 * but never leave the service module.
 */

import type { Schemas } from '@/types'

/** One week of the streak history strip. */
export interface StreakWeek {
  /** ISO `YYYY-MM-DD` first day of the week. */
  weekStart: string
  /** Activities counted in the week. */
  activityCount: number
  /** Whether the weekly target was reached. */
  met: boolean
}

/** The weekly streak status for a user. */
export interface WeeklyStreak {
  /** Consecutive weeks meeting the target, up to now. */
  currentStreak: number
  /** ISO first week of the current streak, or `null` when there is none. */
  currentStreakStart: string | null
  /** Longest run of consecutive weeks ever. */
  longestStreak: number
  /** ISO first week of the longest run, or `null`. */
  longestStreakStart: string | null
  /** ISO last week of the longest run, or `null`. */
  longestStreakEnd: string | null
  /** ISO first day of the current week. */
  currentWeekStart: string
  /** Activities counted so far this week. */
  currentWeekCount: number
  /** Whether this week's target is already met. */
  currentWeekMet: boolean
  /** A streak is running but this week's target isn't met yet. */
  atRisk: boolean
  /** The weekly target in effect. */
  minActivitiesPerWeek: number
  /** Counted activity-type codes, or `null` for every type. */
  activityTypes: number[] | null
  /** Recent weeks, oldest first, ending with the current week. */
  recentWeeks: StreakWeek[]
}

/** The user's streak configuration. */
export interface StreakSettings {
  /** Activities a week needs to keep the streak (1–21). */
  minActivitiesPerWeek: number
  /** Counted activity-type codes, or `null` for every type. */
  activityTypes: number[] | null
  /** Whether other users can see the streak on the profile. */
  showOnProfile: boolean
}

/** Upper bound for the weekly target; mirrors the backend validation. */
export const MAX_ACTIVITIES_PER_WEEK = 21

/** Wire format of a history week. */
export type StreakWeekDto = Schemas['StreakWeek']

/** Wire format of `GET /activities_streaks`. */
export type WeeklyStreakDto = Schemas['WeeklyStreakResponse']

/** Wire format of `GET /profile/streak_settings` and the `PUT` response. */
export type StreakSettingsReadDto = Schemas['UsersStreakSettingsRead']

/** Request body of `PUT /profile/streak_settings`. */
export type StreakSettingsUpdateDto = Schemas['UsersStreakSettingsUpdate']
