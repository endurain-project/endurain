import { defineComponent, h, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { Gear, GearInput, GearsPage } from '@/features/gears/types'

import {
  useCreateGearMutation,
  useDeleteGearMutation,
  useGearsQuery,
  useUpdateGearMutation,
} from '@/features/gears/composables/useGears'
import { createGear, deleteGear, fetchGears, updateGear } from '@/features/gears/services/gears'
import { queryKeys } from '@/services/queryKeys'

vi.mock('@/features/gears/services/gears', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/gears/services/gears')>()),
  createGear: vi.fn<(input: GearInput) => Promise<Gear>>(),
  deleteGear: vi.fn<(id: number) => Promise<void>>(),
  fetchGears: vi.fn<() => Promise<GearsPage>>(),
  updateGear: vi.fn<(id: number, input: GearInput, version: number) => Promise<Gear>>(),
}))

vi.mock('pinia', async (importOriginal) => ({
  ...(await importOriginal<typeof import('pinia')>()),
  storeToRefs: () => ({ isAuthenticated: ref(true) }),
}))

vi.mock('@/features/auth/stores/auth', () => ({ useAuthStore: () => ({}) }))

const GEAR_ID = 3

/** What a write to a gear itself changes: where the gear is listed, searched and picked. */
const GEAR_KEYS = {
  list: queryKeys.gears.list({ page: 1 }),
  search: queryKeys.gears.search('road'),
  detail: queryKeys.gears.detail(GEAR_ID),
  typeOptions: queryKeys.gears.typeOptions(),
  byType: queryKeys.gears.byType(1),
}

/** Data a gear write never changes: its components, the static catalogue and its activity rows. */
const UNAFFECTED_KEYS = {
  components: queryKeys.gears.components(GEAR_ID),
  componentTypes: queryKeys.gears.componentTypes(),
  activities: queryKeys.gears.activities(GEAR_ID, { page: 1 }),
}

const gearInput = {} as GearInput
const gear = {} as Gear

let wrapper: ReturnType<typeof mount> | undefined

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.clearAllMocks()
})

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

function mountQuery(queryClient: QueryClient): void {
  wrapper = mount(
    defineComponent({
      setup() {
        useGearsQuery(1, 25, false)
        return () => h('div')
      },
    }),
    { global: { plugins: [[VueQueryPlugin, { queryClient }]] } },
  )
}

function seededClient(): QueryClient {
  const queryClient = new QueryClient()
  for (const key of [...Object.values(GEAR_KEYS), ...Object.values(UNAFFECTED_KEYS)]) {
    queryClient.setQueryData(key, [])
  }
  return queryClient
}

/** Names of the entries whose cached query is marked invalidated, in the order given. */
function invalidatedNames(
  queryClient: QueryClient,
  keys: Record<string, readonly unknown[]>,
): string[] {
  return Object.entries(keys)
    .filter(([, key]) => queryClient.getQueryState(key)?.isInvalidated)
    .map(([name]) => name)
}

describe('gear write mutations', () => {
  it('create refreshes the gear lists and pickers, not components or gear activities', async () => {
    const queryClient = seededClient()
    vi.mocked(createGear).mockResolvedValue(gear)
    const mutation = mountMutation(queryClient, useCreateGearMutation)

    await mutation.mutateAsync(gearInput)
    await flushPromises()

    expect(invalidatedNames(queryClient, GEAR_KEYS)).toEqual(Object.keys(GEAR_KEYS))
    expect(invalidatedNames(queryClient, UNAFFECTED_KEYS)).toEqual([])
  })

  it('update refreshes the gear lists and pickers, not components or gear activities', async () => {
    const queryClient = seededClient()
    vi.mocked(updateGear).mockResolvedValue(gear)
    const mutation = mountMutation(queryClient, useUpdateGearMutation)

    await mutation.mutateAsync({ id: GEAR_ID, input: gearInput, version: 1 })
    await flushPromises()

    expect(invalidatedNames(queryClient, GEAR_KEYS)).toEqual(Object.keys(GEAR_KEYS))
    expect(invalidatedNames(queryClient, UNAFFECTED_KEYS)).toEqual([])
  })

  it('delete refreshes the gear lists and pickers, not components or gear activities', async () => {
    const queryClient = seededClient()
    vi.mocked(deleteGear).mockResolvedValue()
    const mutation = mountMutation(queryClient, useDeleteGearMutation)

    await mutation.mutateAsync(GEAR_ID)
    await flushPromises()

    expect(invalidatedNames(queryClient, GEAR_KEYS)).toEqual(Object.keys(GEAR_KEYS))
    expect(invalidatedNames(queryClient, UNAFFECTED_KEYS)).toEqual([])
  })
})

describe('gear list caching', () => {
  it('keeps a gear list fresh for one minute', async () => {
    vi.mocked(fetchGears).mockResolvedValue({ records: [], total: 0 })
    const queryClient = new QueryClient()
    mountQuery(queryClient)
    await flushPromises()

    const query = queryClient.getQueryCache().find({
      queryKey: queryKeys.gears.list({ page: 1, numRecords: 25, showInactive: false }),
    })
    expect((query?.options as { staleTime?: number } | undefined)?.staleTime).toBe(60_000)
  })
})
