/**
 * Weekly streak service — the DTO ↔ domain boundary for the streak card and the
 * streak settings. Snake-cased wire shapes are mapped to the clean models in
 * `@/features/streaks/types` and never leave this module.
 */

import type {
  StreakSettings,
  StreakSettingsReadDto,
  StreakSettingsUpdateDto,
  WeeklyStreak,
  WeeklyStreakDto,
} from '@/features/streaks/types'

import { apiFetch } from '@/services/http'

/**
 * Maps a raw streak payload to the clean {@link WeeklyStreak} model.
 *
 * @param dto - Raw streak payload from the backend.
 * @returns The normalized streak model.
 */
export function mapWeeklyStreak(dto: WeeklyStreakDto): WeeklyStreak {
  return {
    currentStreak: dto.current_streak,
    currentStreakStart: dto.current_streak_start ?? null,
    longestStreak: dto.longest_streak,
    longestStreakStart: dto.longest_streak_start ?? null,
    longestStreakEnd: dto.longest_streak_end ?? null,
    currentWeekStart: dto.current_week_start,
    currentWeekCount: dto.current_week_count,
    currentWeekMet: dto.current_week_met,
    atRisk: dto.at_risk,
    minActivitiesPerWeek: dto.min_activities_per_week,
    activityTypes: dto.activity_types ?? null,
    recentWeeks: (dto.recent_weeks ?? []).map((week) => ({
      weekStart: week.week_start,
      activityCount: week.activity_count,
      met: week.met,
    })),
  }
}

/**
 * Maps a raw settings payload to the clean {@link StreakSettings} model.
 *
 * @param dto - Raw settings payload from the backend.
 * @returns The normalized settings model.
 */
export function mapStreakSettings(dto: StreakSettingsReadDto): StreakSettings {
  return {
    minActivitiesPerWeek: dto.min_activities_per_week,
    activityTypes: dto.activity_types && dto.activity_types.length > 0 ? dto.activity_types : null,
    showOnProfile: dto.show_on_profile,
  }
}

/**
 * Fetches the authenticated user's weekly streak.
 *
 * @param signal - Optional abort signal for cancellation.
 * @returns The mapped streak.
 * @throws {HttpError} When the request fails.
 */
export async function fetchMyWeeklyStreak(signal?: AbortSignal): Promise<WeeklyStreak> {
  const dto = await apiFetch<WeeklyStreakDto>('/activities_streaks', { signal })
  return mapWeeklyStreak(dto)
}

/**
 * Fetches another user's weekly streak for their profile. Resolves to `null`
 * when the owner has not chosen to show it on their profile.
 *
 * @param userId - The profile owner's id.
 * @param signal - Optional abort signal for cancellation.
 * @returns The mapped streak, or `null` when not shared.
 * @throws {HttpError} When the request fails.
 */
export async function fetchUserWeeklyStreak(
  userId: number,
  signal?: AbortSignal,
): Promise<WeeklyStreak | null> {
  const dto = await apiFetch<WeeklyStreakDto | null>(`/activities_streaks/user/${userId}`, {
    signal,
  })
  return dto ? mapWeeklyStreak(dto) : null
}

/**
 * Fetches the authenticated user's streak settings (defaults if never saved).
 *
 * @param signal - Optional abort signal for cancellation.
 * @returns The mapped settings.
 * @throws {HttpError} When the request fails.
 */
export async function fetchStreakSettings(signal?: AbortSignal): Promise<StreakSettings> {
  const dto = await apiFetch<StreakSettingsReadDto>('/profile/streak_settings', { signal })
  return mapStreakSettings(dto)
}

/**
 * Replaces the authenticated user's streak settings.
 *
 * @param settings - The new settings.
 * @returns The stored settings, mapped.
 * @throws {HttpError} When the request fails (e.g. validation).
 */
export async function updateStreakSettings(settings: StreakSettings): Promise<StreakSettings> {
  const payload: StreakSettingsUpdateDto = {
    min_activities_per_week: settings.minActivitiesPerWeek,
    activity_types:
      settings.activityTypes && settings.activityTypes.length > 0 ? settings.activityTypes : null,
    show_on_profile: settings.showOnProfile,
  }
  const dto = await apiFetch<StreakSettingsReadDto>('/profile/streak_settings', {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
  return mapStreakSettings(dto)
}
