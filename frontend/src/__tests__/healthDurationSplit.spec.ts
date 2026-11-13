import { describe, expect, it, vi } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import type { Component } from 'vue'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import { authedPinia } from './fixtures/authedPinia'
import type { Goal } from '@/features/goals/types'
import type { HealthTargets, SleepListEntry } from '@/features/health/types'
import GoalListItem from '@/features/goals/components/GoalListItem.vue'
import HealthFastingTargetDialog from '@/features/health/components/HealthFastingTargetDialog.vue'
import HealthSleepFormDialog from '@/features/health/components/HealthSleepFormDialog.vue'
import HealthSleepTargetDialog from '@/features/health/components/HealthSleepTargetDialog.vue'

vi.mock('@/services/http', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/http')>()),
  apiFetch: vi.fn<typeof apiFetch>(),
}))

/** 7 h 59 m 45 s: rounds up to 8 h 0 m, never "7 h 60 m". */
const ALMOST_EIGHT_HOURS = 7 * 3600 + 59 * 60 + 45

const passthrough = { template: '<div><slot /></div>' }

const targets: HealthTargets = {
  id: '00000000-0000-4000-8000-000000000001',
  userId: '00000000-0000-4000-8000-000000000001',
  version: 3,
  sleepSeconds: ALMOST_EIGHT_HOURS,
  steps: null,
  weightKg: null,
  fastingSeconds: ALMOST_EIGHT_HOURS,
  waterMl: null,
  poopCount: null,
}

async function openDialog(component: Component, props: Record<string, unknown>) {
  const wrapper = mount(component, {
    props: { open: false, ...props },
    global: {
      plugins: [i18n, authedPinia(), [VueQueryPlugin, { queryClient: new QueryClient() }]],
      stubs: {
        Dialog: passthrough,
        DialogContent: passthrough,
        DialogHeader: passthrough,
        DialogTitle: passthrough,
        DialogDescription: passthrough,
        DialogFooter: passthrough,
      },
    },
  })
  await wrapper.setProps({ open: true })
  return wrapper
}

const inputValues = (wrapper: Awaited<ReturnType<typeof openDialog>>) =>
  wrapper.findAll('input').map((input) => (input.element as HTMLInputElement).value)

describe('hours and minutes seeded from a duration', () => {
  it.each([
    ['sleep target', HealthSleepTargetDialog],
    ['fasting target', HealthFastingTargetDialog],
  ])('seeds the %s as 8 h 0 m', async (_name, component) => {
    const wrapper = await openDialog(component, { targets })
    expect(inputValues(wrapper).slice(0, 2)).toEqual(['8', '0'])
  })

  it('seeds the sleep form total as 8 h 0 m', async () => {
    const entry = {
      id: '00000000-0000-4000-8000-000000000001',
      userId: '00000000-0000-4000-8000-000000000001',
      version: 1,
      date: '2026-10-30',
      sleepStartTimeLocal: null,
      sleepEndTimeLocal: null,
      totalSleepSeconds: ALMOST_EIGHT_HOURS,
      deepSleepSeconds: null,
      lightSleepSeconds: null,
      remSleepSeconds: null,
      awakeSleepSeconds: null,
      hasSleepStages: false,
    } as unknown as SleepListEntry
    vi.mocked(apiFetch).mockResolvedValue({
      id: '00000000-0000-4000-8000-000000000001',
      user_id: '00000000-0000-4000-8000-000000000001',
      version: 1,
      date: '2026-10-30',
      total_sleep_seconds: ALMOST_EIGHT_HOURS,
      sleep_stages: [],
    })
    const wrapper = await openDialog(HealthSleepFormDialog, { entry })
    await flushPromises()
    const values = inputValues(wrapper)
    expect(values).toContain('8')
    expect(values).not.toContain('60')
  })

  it('shows a duration goal as 8h 0m', () => {
    const goal = {
      id: '00000000-0000-4000-8000-000000000001',
      userId: '00000000-0000-4000-8000-000000000001',
      version: 1,
      interval: 'weekly',
      activityType: 'run',
      goalType: 'duration',
      calories: null,
      activitiesNumber: null,
      distanceMeters: null,
      elevationMeters: null,
      durationSeconds: ALMOST_EIGHT_HOURS,
    } as Goal
    const wrapper = mount(GoalListItem, {
      props: { goal, units: 'metric' },
      global: { plugins: [i18n] },
    })
    expect(wrapper.text()).toContain('8h 0m')
    expect(wrapper.text()).not.toContain('60m')
  })
})
