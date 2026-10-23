import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { GoalDto, GoalInput } from '@/features/goals/types'

import { apiFetch } from '@/services/http'
import {
  createGoal,
  deleteGoal,
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
import i18n from '@/i18n'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
}))

const goalDto: GoalDto = {
  id: 3,
  user_id: 7,
  interval: 'weekly',
  activity_type: 'run',
  goal_type: 'distance',
  goal_distance: 42195,
}

const mappedGoal = {
  id: 3,
  userId: 7,
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
        interval: 'daily',
        activity_type: 'swim',
        goal_type: 'duration',
        goal_duration: 3600,
      }),
    ).toEqual({
      id: 1,
      userId: 2,
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
    vi.mocked(apiFetch).mockResolvedValue([goalDto])

    const result = await fetchGoals()

    expect(apiFetch).toHaveBeenCalledWith(
      '/profile/goals',
      expect.objectContaining({ signal: undefined }),
    )
    expect(result).toEqual([mappedGoal])
  })

  it('encodes active filters as query params', async () => {
    vi.mocked(apiFetch).mockResolvedValue([goalDto])

    await fetchGoals({ interval: 'weekly', activityType: 'run', goalType: 'distance' })

    expect(apiFetch).toHaveBeenCalledWith(
      '/profile/goals?interval=weekly&activity_type=run&goal_type=distance',
      expect.objectContaining({ signal: undefined }),
    )
  })

  it('omits unset filters from the query string', async () => {
    vi.mocked(apiFetch).mockResolvedValue([goalDto])

    await fetchGoals({ interval: null, activityType: 'bike', goalType: null })

    expect(apiFetch).toHaveBeenCalledWith(
      '/profile/goals?activity_type=bike',
      expect.objectContaining({ signal: undefined }),
    )
  })

  it('maps a null payload to an empty array', async () => {
    vi.mocked(apiFetch).mockResolvedValue(null)
    await expect(fetchGoals()).resolves.toEqual([])
  })

  it('creates a goal via a POST with the snake-cased payload', async () => {
    vi.mocked(apiFetch).mockResolvedValue(goalDto)

    await createGoal(goalInput)

    expect(apiFetch).toHaveBeenCalledWith('/profile/goals', {
      method: 'POST',
      body: JSON.stringify(expectedWirePayload),
    })
  })

  it('updates a goal via a PUT that includes the id and user id', async () => {
    vi.mocked(apiFetch).mockResolvedValue(goalDto)

    await updateGoal(3, 7, goalInput)

    expect(apiFetch).toHaveBeenCalledWith('/profile/goals', {
      method: 'PUT',
      body: JSON.stringify({ ...expectedWirePayload, id: 3, user_id: 7 }),
    })
  })

  it('deletes a goal via a void DELETE', async () => {
    vi.mocked(apiFetch).mockResolvedValue(undefined)

    await deleteGoal(3)

    expect(apiFetch).toHaveBeenCalledWith('/profile/goals/3', {
      method: 'DELETE',
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
    const t = i18n.global.t
    expect(formatGoalDuration(5400, t)).toBe('1h 30m')
    expect(formatGoalDuration(1800, t)).toBe('30m')
  })
})
