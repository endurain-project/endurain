import { beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  ActivityExerciseTitle,
  ActivityExerciseTitleDto,
  ActivitySetDto,
  ActivityWorkoutStep,
  ActivityWorkoutStepDto,
} from '@/features/activities/types'

import { apiFetch } from '@/services/http'
import {
  fetchActivityExerciseTitles,
  fetchActivitySets,
  fetchActivityWorkoutSteps,
  mapActivityExerciseTitle,
  mapActivitySet,
  mapActivityWorkoutStep,
} from '@/features/activities/services/activities'
import { expandWorkoutSteps, resolveExerciseName } from '@/features/activities/utils/workout'

vi.mock('@/services/http', () => ({ apiFetch: vi.fn<typeof apiFetch>() }))

beforeEach(() => {
  vi.mocked(apiFetch).mockReset()
})

function makeStep(overrides: Partial<ActivityWorkoutStep> = {}): ActivityWorkoutStep {
  return {
    durationType: 'time',
    durationValue: 60,
    exerciseCategory: null,
    exerciseName: null,
    exerciseWeight: null,
    intensity: 'active',
    messageIndex: 0,
    secondaryTargetValue: null,
    targetType: null,
    targetValue: null,
    ...overrides,
  }
}

describe('expandWorkoutSteps', () => {
  it('passes non-repeat steps through unchanged', () => {
    const steps = [makeStep({ messageIndex: 0 }), makeStep({ messageIndex: 1 })]
    expect(expandWorkoutSteps(steps).map((step) => step.messageIndex)).toEqual([0, 1])
  })

  it('expands a repeat directive by repeating the prior two steps', () => {
    const steps = [
      makeStep({ messageIndex: 0 }),
      makeStep({ messageIndex: 1 }),
      makeStep({ messageIndex: 2, durationType: 'repeat_until_steps_cmplt', targetValue: 3 }),
    ]
    // Original A,B then the repeat block adds A,B twice (count 3 - 1 = 2).
    expect(expandWorkoutSteps(steps).map((step) => step.messageIndex)).toEqual([0, 1, 0, 1, 0, 1])
  })
})

describe('resolveExerciseName', () => {
  const titles: ActivityExerciseTitle[] = [
    { exerciseCategory: 1, exerciseName: 5, wktStepName: 'Bench Press' },
  ]

  it('resolves a matching category/name pair', () => {
    expect(resolveExerciseName(titles, 5, 1)).toBe('Bench Press')
  })

  it('returns null when the category does not match', () => {
    expect(resolveExerciseName(titles, 5, 2)).toBeNull()
  })

  it('returns null for nullish codes', () => {
    expect(resolveExerciseName(titles, null, 1)).toBeNull()
    expect(resolveExerciseName(titles, 5, null)).toBeNull()
  })
})

describe('workout mappers', () => {
  it('maps a workout step', () => {
    const dto: ActivityWorkoutStepDto = {
      activity_id: 5,
      duration_type: 'reps',
      duration_value: 12,
      exercise_category: 1,
      exercise_name: 5,
      exercise_weight: 40,
      id: 7,
      intensity: 'active',
      message_index: 0,
      notes: null,
      secondary_target_value: null,
      target_type: null,
      target_value: null,
      weight_display_unit: 'kg',
    }
    expect(mapActivityWorkoutStep(dto)).toEqual({
      durationType: 'reps',
      durationValue: 12,
      exerciseCategory: 1,
      exerciseName: 5,
      exerciseWeight: 40,
      intensity: 'active',
      messageIndex: 0,
      secondaryTargetValue: null,
      targetType: null,
      targetValue: null,
    })
  })

  it('maps a workout set', () => {
    const dto: ActivitySetDto = {
      activity_id: 5,
      category: 1,
      category_subtype: 5,
      duration: 60,
      id: 9,
      repetitions: 12,
      set_type: 'active',
      start_time: '2024-01-01T00:00:00Z',
      weight: 40,
    }
    expect(mapActivitySet(dto)).toEqual({
      id: 9,
      category: 1,
      categorySubtype: 5,
      duration: 60,
      repetitions: 12,
      setType: 'active',
      weight: 40,
    })
  })

  it('maps an exercise title', () => {
    const dto: ActivityExerciseTitleDto = {
      exercise_category: 1,
      exercise_name: 5,
      id: 1,
      wkt_step_name: 'Bench Press',
    }
    expect(mapActivityExerciseTitle(dto)).toEqual({
      exerciseCategory: 1,
      exerciseName: 5,
      wktStepName: 'Bench Press',
    })
  })
})

describe('workout fetchers', () => {
  it('fetches workout steps from the authenticated endpoint', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce([])
    await fetchActivityWorkoutSteps(5, { authenticated: true })
    expect(apiFetch).toHaveBeenCalledWith('/activities/5/workout-steps', {
      auth: true,
      signal: undefined,
    })
  })

  it('fetches workout sets from the public endpoint when anonymous', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(null)
    const sets = await fetchActivitySets(5, { authenticated: false })
    expect(apiFetch).toHaveBeenCalledWith('/public/activities/5/sets', {
      auth: false,
      signal: undefined,
    })
    expect(sets).toEqual([])
  })

  it('fetches the exercise-title catalogue (authenticated)', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce([])
    await fetchActivityExerciseTitles({ authenticated: true })
    expect(apiFetch).toHaveBeenCalledWith('/activities/exercise-titles/all', {
      auth: true,
      signal: undefined,
    })
  })

  it('fetches the public exercise-title catalogue when anonymous', async () => {
    vi.mocked(apiFetch).mockResolvedValueOnce(null)
    const titles = await fetchActivityExerciseTitles({ authenticated: false })
    expect(apiFetch).toHaveBeenCalledWith('/public/activities/exercise-titles/all', {
      auth: false,
      signal: undefined,
    })
    expect(titles).toEqual([])
  })
})
