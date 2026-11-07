import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ref } from 'vue'
import { shallowMount } from '@vue/test-utils'

import type { FastingEntry } from '@/features/health/types'

import i18n from '@/i18n'
import HealthFastingView from '@/features/health/views/HealthFastingView.vue'
import HealthFastingActiveCard from '@/features/health/components/HealthFastingActiveCard.vue'
import { ConfirmDialog } from '@/components/ui/confirm-dialog'

const active = { id: 5, version: 2 } as FastingEntry
const mutate = vi.fn<(...args: unknown[]) => void>()

function query<T>(data: T) {
  return {
    data: ref(data),
    isPending: ref(false),
    isError: ref(false),
    refetch: vi.fn<() => void>(),
  }
}

vi.mock('@/features/health/composables/useHealth', () => ({
  useActiveFastingQuery: () => query(active),
  useFastingStatsQuery: () => query(null),
  useFastingEntriesQuery: () => query({ records: [], total: 0 }),
  useHealthTargetsQuery: () => query(null),
  useCompleteFastingEntryMutation: () => ({ mutate, isPending: ref(false) }),
  useDeleteFastingEntryMutation: () => ({ mutate: vi.fn<() => void>(), isPending: ref(false) }),
}))
vi.mock('@/features/config/composables/useRecordsPerPage', () => ({
  useRecordsPerPage: () => ({ recordsPerPage: ref(10) }),
}))
vi.mock('@/composables/useToasts', () => ({
  useToasts: () => ({ success: vi.fn<() => void>(), error: vi.fn<() => void>() }),
}))

function mountView() {
  return shallowMount(HealthFastingView, { global: { plugins: [i18n] } })
}

/** The confirm dialog that guards ending a fast early (the first one; delete is second). */
function endDialog(wrapper: ReturnType<typeof mountView>) {
  return wrapper.findAllComponents(ConfirmDialog)[0]!
}

describe('HealthFastingView ending a fast early', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it.each(['broken', 'cancelled'] as const)('asks before a %s fast is saved', async (status) => {
    const wrapper = mountView()
    wrapper.findComponent(HealthFastingActiveCard).vm.$emit('complete', status)
    await wrapper.vm.$nextTick()

    expect(mutate).not.toHaveBeenCalled()
    expect(endDialog(wrapper).props('open')).toBe(true)

    endDialog(wrapper).vm.$emit('confirm')
    expect(mutate).toHaveBeenCalledTimes(1)
    expect(mutate.mock.calls[0]![0]).toMatchObject({ id: 5, status, version: 2 })
  })

  it('completes a reached target without asking', async () => {
    const wrapper = mountView()
    wrapper.findComponent(HealthFastingActiveCard).vm.$emit('complete', 'completed')
    await wrapper.vm.$nextTick()

    expect(mutate).toHaveBeenCalledTimes(1)
    expect(endDialog(wrapper).props('open')).toBe(false)
  })
})
