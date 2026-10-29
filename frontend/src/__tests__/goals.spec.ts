import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { GoalDto, GoalInput, GoalProgressDto } from '@/features/goals/types'

import { apiFetch } from '@/services/http'
import {
  createGoal,
  deleteGoal,
  fetchGoalResults,
  fetchGoals,
  mapGoal,
  updateGoal,
} from '@/features/goals/services/goals'
import {
  distanceValueToMeters,
  elevationValueToMeters,
  formatGoalDuration,
  hoursMinutesToSeconds,
  metersToDistanceValue,
  metersToElevationValue,
  secondsToHoursMinutes,
} from '@/features/goals/utils/goalFormat'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
}))

const goalDto: GoalDto = {
  id: 3,
  user_id: 7,
  version: 4,
  interval: 'weekly',
  activity_type: 'run',
  goal_type: 'distance',
  goal_distance: 42195,
}

const mappedGoal = {
  id: 3,
  userId: 7,
  version: 4,
  interval: 'weekly',
  activityType: 'run',
  goalType: 'distance',
  calories: null,
  activitiesNumber: null,
  distanceMeters: 42195,
  elevationMeters: null,
  durationSeconds: null,
}

const goalInput: GoalInput = {
  interval: 'daily',
  activityType: 'bike',
  goalType: 'calories',
  calories: 500,
  activitiesNumber: null,
  distanceMeters: null,
  elevationMeters: null,
  durationSeconds: null,
}

const expectedWirePayload = {
  interval: 'daily',
  activity_type: 'bike',
  goal_type: 'calories',
  goal_calories: 500,
  goal_activities_number: null,
  goal_distance: null,
  goal_elevation: null,
  goal_duration: null,
}

describe('mapGoal', () => {
  it('maps the snake-cased DTO to the clean model', () => {
    expect(mapGoal(goalDto)).toEqual(mappedGoal)
  })

  it('collapses absent optional targets to null', () => {
    expect(
      mapGoal({
        id: 1,
        user_id: 2,
        version: 1,
        interval: 'daily',
        activity_type: 'swim',
        goal_type: 'duration',
        goal_duration: 3600,
      }),
    ).toEqual({
      id: 1,
      userId: 2,
      version: 1,
      interval: 'daily',
      activityType: 'swim',
      goalType: 'duration',
      calories: null,
      activitiesNumber: null,
      distanceMeters: null,
      elevationMeters: null,
      durationSeconds: 3600,
    })
  })
})

describe('goal service requests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('requests the goals path and maps the records', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ items: [goalDto], next: null })

    const result = await fetchGoals()

    expect(apiFetch).toHaveBeenCalledWith(
      '/profile/goals?page_number=1',
      expect.objectContaining({ signal: undefined }),
    )
    expect(result).toEqual([mappedGoal])
  })

  it('encodes active filters as query params', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ items: [goalDto], next: null })

    await fetchGoals({ interval: 'weekly', activityType: 'run', goalType: 'distance' })

    expect(apiFetch).toHaveBeenCalledWith(
      '/profile/goals?interval=weekly&activity_type=run&goal_type=distance&page_number=1',
      expect.objectContaining({ signal: undefined }),
    )
  })

  it('omits unset filters from the query string', async () => {
    vi.mocked(apiFetch).mockResolvedValue({ items: [goalDto], next: null })

    await fetchGoals({ interval: null, activityType: 'bike', goalType: null })

    expect(apiFetch).toHaveBeenCalledWith(
      '/profile/goals?activity_type=bike&page_number=1',
      expect.objectContaining({ signal: undefined }),
    )
  })

  it('maps a null payload to an empty array', async () => {
    vi.mocked(apiFetch).mockResolvedValue(null)
    await expect(fetchGoals()).resolves.toEqual([])
  })

  it('follows the pages until the last one', async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce({ items: [goalDto], next: 2 })
      .mockResolvedValueOnce({ items: [goalDto], next: null })

    const result = await fetchGoals()

    expect(apiFetch).toHaveBeenNthCalledWith(2, '/profile/goals?page_number=2', expect.anything())
    expect(result).toHaveLength(2)
  })

  it('reads every page of the goal results and maps them', async () => {
    const progressDto: GoalProgressDto = {
      goal_id: 1,
      interval: 'weekly',
      activity_type: 'run',
      goal_type: 'calories',
      start_date: '2026-03-02',
      end_date: '2026-03-08',
      percentage_completed: 50,
      total_calories: 250,
      goal_calories: 500,
    }
    vi.mocked(apiFetch)
      .mockResolvedValueOnce({ items: [progressDto], next: 2 })
      .mockResolvedValueOnce({ items: [{ ...progressDto, goal_id: 2 }], next: null })

    const result = await fetchGoalResults()

    expect(apiFetch).toHaveBeenNthCalledWith(
      1,
      '/profile/goals/results?page_number=1',
      expect.anything(),
    )
    expect(apiFetch).toHaveBeenNthCalledWith(
      2,
      '/profile/goals/results?page_number=2',
      expect.anything(),
    )
    expect(result.map((progress) => progress.goalId)).toEqual([1, 2])
    expect(result[0]).toMatchObject({ total: 250, target: 500, percentageCompleted: 50 })
  })

  it('creates a goal via a POST with the snake-cased payload', async () => {
    vi.mocked(apiFetch).mockResolvedValue(goalDto)

    await createGoal(goalInput)

    expect(apiFetch).toHaveBeenCalledWith('/profile/goals', {
      method: 'POST',
      body: JSON.stringify(expectedWirePayload),
    })
  })

  it('replaces a goal via a PUT to its path, guarded by If-Match, without the id', async () => {
    vi.mocked(apiFetch).mockResolvedValue(goalDto)

    await updateGoal(3, goalInput, 4)

    expect(apiFetch).toHaveBeenCalledWith('/profile/goals/3', {
      method: 'PUT',
      headers: { 'If-Match': '"4"' },
      body: JSON.stringify(expectedWirePayload),
    })
  })

  it('deletes a goal via a void DELETE', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await deleteGoal(3, 6)

    expect(apiFetch).toHaveBeenCalledWith('/profile/goals/3', {
      method: 'DELETE',
      headers: { 'If-Match': '"6"' },
      responseType: 'void',
    })
  })
})

describe('goal unit conversions', () => {
  it('converts metres to the display distance for each unit system', () => {
    expect(metersToDistanceValue(42195, 'metric')).toBe(42.2)
    expect(metersToDistanceValue(1609.344, 'imperial')).toBe(1)
  })

  it('converts a display distance back to whole metres', () => {
    expect(distanceValueToMeters(42.2, 'metric')).toBe(42200)
    expect(distanceValueToMeters(1, 'imperial')).toBe(1609)
  })

  it('converts metres to the display elevation for each unit system', () => {
    expect(metersToElevationValue(1000, 'metric')).toBe(1000)
    expect(metersToElevationValue(304.8, 'imperial')).toBe(1000)
  })

  it('converts a display elevation back to whole metres', () => {
    expect(elevationValueToMeters(1000, 'metric')).toBe(1000)
    expect(elevationValueToMeters(1000, 'imperial')).toBe(305)
  })

  it('splits and recombines durations', () => {
    expect(secondsToHoursMinutes(5400)).toEqual({ hours: 1, minutes: 30 })
    expect(hoursMinutesToSeconds(1, 30)).toBe(5400)
  })

  it('formats durations compactly', () => {
    expect(formatGoalDuration(5400)).toBe('1h 30m')
    expect(formatGoalDuration(1800)).toBe('30m')
  })
})
