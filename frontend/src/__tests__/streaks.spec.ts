import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

import type { WeeklyStreak, WeeklyStreakDto } from '@/features/streaks/types'

import i18n from '@/i18n'
import { apiFetch } from '@/services/http'
import WeeklyStreakCard from '@/features/streaks/components/WeeklyStreakCard.vue'
import {
  fetchMyWeeklyStreak,
  fetchStreakSettings,
  fetchUserWeeklyStreak,
  mapWeeklyStreak,
  updateStreakSettings,
} from '@/features/streaks/services/streaks'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
}))

const streakDto: WeeklyStreakDto = {
  current_streak: 3,
  current_streak_start: '2026-09-28',
  longest_streak: 5,
  longest_streak_start: '2026-01-05',
  longest_streak_end: '2026-02-02',
  current_week_start: '2026-10-12',
  current_week_count: 1,
  current_week_met: false,
  at_risk: true,
  min_activities_per_week: 2,
  activity_types: null,
  recent_weeks: [
    { week_start: '2026-10-05', activity_count: 2, met: true },
    { week_start: '2026-10-12', activity_count: 1, met: false },
  ],
}

/** Builds a streak model, overridable per case. */
function makeStreak(overrides: Partial<WeeklyStreak> = {}): WeeklyStreak {
  return { ...mapWeeklyStreak(streakDto), ...overrides }
}

/**
 * Mounts the streak card with the app's i18n plugin.
 *
 * @param props - Card props for the case under test.
 * @returns The mounted wrapper.
 */
function mountCard(props: InstanceType<typeof WeeklyStreakCard>['$props']) {
  return mount(WeeklyStreakCard, { props, global: { plugins: [i18n] } })
}

describe('streak service', () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset()
  })

  it('maps the streak payload to the clean model', () => {
    expect(mapWeeklyStreak(streakDto)).toEqual({
      currentStreak: 3,
      currentStreakStart: '2026-09-28',
      longestStreak: 5,
      longestStreakStart: '2026-01-05',
      longestStreakEnd: '2026-02-02',
      currentWeekStart: '2026-10-12',
      currentWeekCount: 1,
      currentWeekMet: false,
      atRisk: true,
      minActivitiesPerWeek: 2,
      activityTypes: null,
      recentWeeks: [
        { weekStart: '2026-10-05', activityCount: 2, met: true },
        { weekStart: '2026-10-12', activityCount: 1, met: false },
      ],
    })
  })

  it('fetches the viewer streak', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(streakDto)
    const streak = await fetchMyWeeklyStreak()
    expect(apiFetch).toHaveBeenCalledWith('/activities_streaks', { signal: undefined })
    expect(streak.currentStreak).toBe(3)
  })

  it('returns null for a profile that keeps the streak private', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(null)
    expect(await fetchUserWeeklyStreak(7)).toBeNull()
    expect(apiFetch).toHaveBeenCalledWith('/activities_streaks/user/7', { signal: undefined })
  })

  it('maps settings and treats an empty type list as all types', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      user_id: 1,
      min_activities_per_week: 3,
      activity_types: [],
      show_on_profile: true,
    })
    expect(await fetchStreakSettings()).toEqual({
      minActivitiesPerWeek: 3,
      activityTypes: null,
      showOnProfile: true,
    })
  })

  it('sends snake-cased settings on update', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce({
      min_activities_per_week: 2,
      activity_types: [1, 4],
      show_on_profile: false,
    })
    const stored = await updateStreakSettings({
      minActivitiesPerWeek: 2,
      activityTypes: [1, 4],
      showOnProfile: false,
    })
    expect(apiFetch).toHaveBeenCalledWith('/profile/streak_settings', {
      method: 'PUT',
      body: JSON.stringify({
        min_activities_per_week: 2,
        activity_types: [1, 4],
        show_on_profile: false,
      }),
    })
    expect(stored.activityTypes).toEqual([1, 4])
  })
})

describe('WeeklyStreakCard', () => {
  it('shows the current streak and an at-risk nudge', () => {
    const wrapper = mountCard({ streak: makeStreak() })
    expect(wrapper.get('[data-testid="streak-current"]').text()).toBe('3 weeks')
    expect(wrapper.get('[data-testid="streak-status"]').text()).toContain('1 more activity')
    expect(wrapper.findAll('li')).toHaveLength(2)
    expect(wrapper.text()).toContain('Longest streak: 5 weeks')
  })

  it('shows plain progress instead of the nudge on another user profile', () => {
    const wrapper = mountCard({ streak: makeStreak(), isOtherUser: true })
    expect(wrapper.get('[data-testid="streak-status"]').text()).toBe('1 of 2 this week')
  })

  it('marks a met week and a personal best', () => {
    const wrapper = mountCard({
      streak: makeStreak({
        currentStreak: 6,
        longestStreak: 6,
        currentWeekCount: 2,
        currentWeekMet: true,
        atRisk: false,
      }),
    })
    expect(wrapper.get('[data-testid="streak-status"]').text()).toContain(
      'Done for this week (2 of 2)',
    )
    expect(wrapper.text()).toContain('Personal best')
  })

  it('caps the progressbar value at the weekly target', () => {
    const wrapper = mountCard({
      streak: makeStreak({ currentWeekCount: 5, currentWeekMet: true, atRisk: false }),
    })
    const bar = wrapper.get('[role="progressbar"]')
    expect(bar.attributes('aria-valuenow')).toBe('2')
    expect(bar.attributes('aria-valuemax')).toBe('2')
    expect(wrapper.get('[data-testid="streak-status"]').text()).toContain('5 of 2')
  })

  it('invites the user to start a streak when there is none', () => {
    const wrapper = mountCard({
      streak: makeStreak({
        currentStreak: 0,
        currentStreakStart: null,
        longestStreak: 0,
        longestStreakStart: null,
        longestStreakEnd: null,
        atRisk: false,
        currentWeekCount: 0,
      }),
    })
    expect(wrapper.get('[data-testid="streak-current"]').text()).toBe('0 weeks')
    expect(wrapper.text()).toContain('No streak yet')
  })

  it('renders a skeleton while loading', () => {
    const wrapper = mountCard({ streak: undefined, isLoading: true })
    expect(wrapper.find('[aria-busy="true"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="streak-current"]').exists()).toBe(false)
  })
})
