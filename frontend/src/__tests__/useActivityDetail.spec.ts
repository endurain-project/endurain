import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, QueryObserver, VueQueryPlugin } from '@tanstack/vue-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Activity, ActivityEditInput } from '@/features/activities/types'

import {
  useDeleteActivityMutation,
  useEditActivityMutation,
  useSetActivityGearMutation,
} from '@/features/activities/composables/useActivityDetail'
import {
  deleteActivity,
  editActivity,
  setActivityGear,
} from '@/features/activities/services/activities'
import { queryKeys } from '@/services/queryKeys'

import { makeActivity } from './fixtures/activity'

vi.mock('@/features/activities/services/activities', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/activities/services/activities')>()),
  deleteActivity: vi.fn<(id: number) => Promise<void>>(),
  editActivity:
    vi.fn<(id: number, input: ActivityEditInput, version: number) => Promise<Activity>>(),
  setActivityGear: vi.fn<(activity: Activity, gearId: number | null) => Promise<Activity>>(),
}))

const ACTIVITY_ID = 5
const GEAR_ID = 3

const editInput: ActivityEditInput = {
  name: 'Evening run',
  activityType: 1,
  description: '',
  privateNotes: '',
  visibility: 0,
  isHidden: false,
  hideStartTime: false,
  hideLocation: false,
  hideMap: false,
  hideHr: false,
  hidePower: false,
  hideCadence: false,
  hideElevation: false,
  hideSpeed: false,
  hidePace: false,
  hideLaps: false,
  hideWorkoutSetsSteps: false,
  hideGear: false,
}

/** Everything derived from activity rows: an activity write makes these stale. */
const AGGREGATE_KEYS = {
  list: queryKeys.activities.list({ scope: 'user-list', userId: 7, page: 1 }),
  feed: queryKeys.activities.userFeed(7, 25),
  summary: queryKeys.activities.summary({ viewType: 'week' }),
  stats: queryKeys.activities.stats(7, 'week'),
  search: queryKeys.activities.search('run'),
  typeNames: queryKeys.activities.typeNames(),
  monthCount: queryKeys.activities.monthCount(7),
}

/** One activity's own data and static reference data: an activity write never changes these. */
const UNAFFECTED_ACTIVITY_KEYS = {
  streams: queryKeys.activities.streams(ACTIVITY_ID),
  laps: queryKeys.activities.laps(ACTIVITY_ID),
  workoutSteps: queryKeys.activities.workoutSteps(ACTIVITY_ID),
  sets: queryKeys.activities.sets(ACTIVITY_ID),
  media: queryKeys.activities.media(ACTIVITY_ID),
  otherDetail: queryKeys.activities.detail(99),
  exerciseTitles: queryKeys.activities.exerciseTitles(),
  owner: queryKeys.activities.owner(5),
}

/** A gear's totals and its activity rows depend on which activities carry it. */
const GEAR_USAGE_KEYS = {
  detail: queryKeys.gears.detail(GEAR_ID),
  activities: queryKeys.gears.activities(GEAR_ID, { page: 1 }),
}

/** Gear data an activity write never changes. */
const UNAFFECTED_GEAR_KEYS = {
  list: queryKeys.gears.list({ page: 1 }),
  components: queryKeys.gears.components(GEAR_ID),
  componentTypes: queryKeys.gears.componentTypes(),
  byType: queryKeys.gears.byType(1),
}

let wrapper: ReturnType<typeof mount> | undefined

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.clearAllMocks()
})

/** Mounts a component that runs `useMutation` against the given client and returns its result. */
function mountMutation<T>(queryClient: QueryClient, useMutation: () => T): T {
  let mutation: T | undefined
  wrapper = mount(
    defineComponent({
      setup() {
        mutation = useMutation()
        return () => h('div')
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
  )
  if (!mutation) {
    throw new Error('Mutation was not initialized')
  }
  return mutation
}

/** Builds a client with every key above, plus the edited activity's detail, in the cache. */
function seededClient(): QueryClient {
  const queryClient = new QueryClient()
  queryClient.setQueryData(queryKeys.activities.detail(ACTIVITY_ID), makeActivity({ id: 5 }))
  for (const key of [
    ...Object.values(AGGREGATE_KEYS),
    ...Object.values(UNAFFECTED_ACTIVITY_KEYS),
    ...Object.values(GEAR_USAGE_KEYS),
    ...Object.values(UNAFFECTED_GEAR_KEYS),
  ]) {
    queryClient.setQueryData(key, [])
  }
  return queryClient
}

function isInvalidated(queryClient: QueryClient, key: readonly unknown[]): boolean {
  const state = queryClient.getQueryState(key)
  if (!state) {
    throw new Error(`No query cached under ${JSON.stringify(key)}`)
  }
  return state.isInvalidated
}

/** Names of the entries whose cached query is marked invalidated, in the order given. */
function invalidatedNames(
  queryClient: QueryClient,
  keys: Record<string, readonly unknown[]>,
): string[] {
  return Object.entries(keys)
    .filter(([, key]) => isInvalidated(queryClient, key))
    .map(([name]) => name)
}

describe('useEditActivityMutation', () => {
  it('refreshes lists and aggregates but not the activity sub-resources', async () => {
    const queryClient = seededClient()
    const updated = makeActivity({ id: ACTIVITY_ID, name: 'Evening run', version: 2 })
    vi.mocked(editActivity).mockResolvedValue(updated)
    const mutation = mountMutation(queryClient, useEditActivityMutation)

    await mutation.mutateAsync({ id: ACTIVITY_ID, input: editInput, version: 1 })
    await flushPromises()

    expect(invalidatedNames(queryClient, AGGREGATE_KEYS)).toEqual(Object.keys(AGGREGATE_KEYS))
    expect(invalidatedNames(queryClient, UNAFFECTED_ACTIVITY_KEYS)).toEqual([])
    expect(invalidatedNames(queryClient, UNAFFECTED_GEAR_KEYS)).toEqual([])
    expect(invalidatedNames(queryClient, GEAR_USAGE_KEYS)).toEqual([])
  })

  it('trusts the PATCH response for the edited activity instead of refetching it', async () => {
    const queryClient = seededClient()
    const updated = makeActivity({ id: ACTIVITY_ID, name: 'Evening run', version: 2 })
    vi.mocked(editActivity).mockResolvedValue(updated)
    const mutation = mountMutation(queryClient, useEditActivityMutation)

    await mutation.mutateAsync({ id: ACTIVITY_ID, input: editInput, version: 1 })
    await flushPromises()

    expect(queryClient.getQueryData(queryKeys.activities.detail(ACTIVITY_ID))).toEqual(updated)
    expect(isInvalidated(queryClient, queryKeys.activities.detail(ACTIVITY_ID))).toBe(false)
  })

  it('refetches only the edited activity when the save fails, so a stale copy is replaced', async () => {
    const queryClient = seededClient()
    vi.mocked(editActivity).mockRejectedValue(new Error('412'))
    const mutation = mountMutation(queryClient, useEditActivityMutation)

    await expect(
      mutation.mutateAsync({ id: ACTIVITY_ID, input: editInput, version: 1 }),
    ).rejects.toThrow('412')
    await flushPromises()

    expect(isInvalidated(queryClient, queryKeys.activities.detail(ACTIVITY_ID))).toBe(true)
    expect(invalidatedNames(queryClient, UNAFFECTED_ACTIVITY_KEYS)).toEqual([])
  })
})

describe('useSetActivityGearMutation', () => {
  it('marks the gear totals stale without refetching the activity sub-resources or gear lists', async () => {
    const queryClient = seededClient()
    const updated = makeActivity({ id: ACTIVITY_ID, gearId: GEAR_ID, version: 2 })
    vi.mocked(setActivityGear).mockResolvedValue(updated)
    const mutation = mountMutation(queryClient, useSetActivityGearMutation)

    await mutation.mutateAsync({ activity: makeActivity({ id: ACTIVITY_ID }), gearId: GEAR_ID })
    await flushPromises()

    expect(invalidatedNames(queryClient, AGGREGATE_KEYS)).toEqual(Object.keys(AGGREGATE_KEYS))
    expect(invalidatedNames(queryClient, GEAR_USAGE_KEYS)).toEqual(Object.keys(GEAR_USAGE_KEYS))
    expect(invalidatedNames(queryClient, UNAFFECTED_ACTIVITY_KEYS)).toEqual([])
    expect(invalidatedNames(queryClient, UNAFFECTED_GEAR_KEYS)).toEqual([])
    expect(queryClient.getQueryData(queryKeys.activities.detail(ACTIVITY_ID))).toEqual(updated)
  })

  it('does not refetch the gear card that is on screen; it is replaced by the new gear anyway', async () => {
    const queryClient = seededClient()
    const fetchGear = vi.fn<() => Promise<unknown[]>>(() => Promise.resolve([]))
    const observer = new QueryObserver(queryClient, {
      queryKey: queryKeys.gears.detail(GEAR_ID),
      queryFn: fetchGear,
      staleTime: Number.POSITIVE_INFINITY,
    })
    const unsubscribe = observer.subscribe(() => undefined)
    vi.mocked(setActivityGear).mockResolvedValue(makeActivity({ id: ACTIVITY_ID, gearId: null }))
    const mutation = mountMutation(queryClient, useSetActivityGearMutation)

    await mutation.mutateAsync({ activity: makeActivity({ id: ACTIVITY_ID }), gearId: null })
    await flushPromises()
    unsubscribe()

    expect(fetchGear).not.toHaveBeenCalled()
    expect(isInvalidated(queryClient, queryKeys.gears.detail(GEAR_ID))).toBe(true)
  })
})

describe('useDeleteActivityMutation', () => {
  it('drops the deleted activity and its sub-resources instead of refetching them', async () => {
    const queryClient = seededClient()
    vi.mocked(deleteActivity).mockResolvedValue()
    const mutation = mountMutation(queryClient, useDeleteActivityMutation)

    await mutation.mutateAsync(ACTIVITY_ID)
    await flushPromises()

    const activityKeys = [
      queryKeys.activities.detail(ACTIVITY_ID),
      UNAFFECTED_ACTIVITY_KEYS.streams,
      UNAFFECTED_ACTIVITY_KEYS.laps,
      UNAFFECTED_ACTIVITY_KEYS.workoutSteps,
      UNAFFECTED_ACTIVITY_KEYS.sets,
      UNAFFECTED_ACTIVITY_KEYS.media,
    ]
    expect(activityKeys.filter((key) => queryClient.getQueryState(key) !== undefined)).toEqual([])
  })

  it('keeps unrelated activities and static data, and refreshes lists, aggregates and gear usage', async () => {
    const queryClient = seededClient()
    vi.mocked(deleteActivity).mockResolvedValue()
    const mutation = mountMutation(queryClient, useDeleteActivityMutation)

    await mutation.mutateAsync(ACTIVITY_ID)
    await flushPromises()

    expect(invalidatedNames(queryClient, AGGREGATE_KEYS)).toEqual(Object.keys(AGGREGATE_KEYS))
    expect(invalidatedNames(queryClient, GEAR_USAGE_KEYS)).toEqual(Object.keys(GEAR_USAGE_KEYS))
    expect(
      invalidatedNames(queryClient, {
        otherDetail: UNAFFECTED_ACTIVITY_KEYS.otherDetail,
        exerciseTitles: UNAFFECTED_ACTIVITY_KEYS.exerciseTitles,
        owner: UNAFFECTED_ACTIVITY_KEYS.owner,
        ...UNAFFECTED_GEAR_KEYS,
      }),
    ).toEqual([])
  })

  it('keeps the activity cached when the delete fails', async () => {
    const queryClient = seededClient()
    vi.mocked(deleteActivity).mockRejectedValue(new Error('500'))
    const mutation = mountMutation(queryClient, useDeleteActivityMutation)

    await expect(mutation.mutateAsync(ACTIVITY_ID)).rejects.toThrow('500')
    await flushPromises()

    expect(queryClient.getQueryState(queryKeys.activities.detail(ACTIVITY_ID))).toBeDefined()
    expect(queryClient.getQueryState(UNAFFECTED_ACTIVITY_KEYS.streams)).toBeDefined()
  })
})
