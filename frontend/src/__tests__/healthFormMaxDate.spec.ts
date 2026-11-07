import { describe, expect, it, vi } from 'vitest'

import { mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import type { Component } from 'vue'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import { todayIsoDate } from '@/utils/datetime'
import HealthFastingFormDialog from '@/features/health/components/HealthFastingFormDialog.vue'
import HealthPoopFormDialog from '@/features/health/components/HealthPoopFormDialog.vue'
import HealthSleepFormDialog from '@/features/health/components/HealthSleepFormDialog.vue'
import HealthStepsFormDialog from '@/features/health/components/HealthStepsFormDialog.vue'
import HealthWaterFormDialog from '@/features/health/components/HealthWaterFormDialog.vue'
import HealthWeightFormDialog from '@/features/health/components/HealthWeightFormDialog.vue'

vi.mock('@/services/http', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/http')>()),
  apiFetch: vi.fn<typeof apiFetch>(),
}))

/** Passthrough stub so the reka-ui portal/focus-trap is skipped and the form renders inline. */
const passthrough = { template: '<div><slot /></div>' }

/** Opens a health dialog and returns its mounted wrapper. */
async function openDialog(component: Component, props: Record<string, unknown> = {}) {
  const wrapper = mount(component, {
    props: { open: false, entry: null, ...props },
    global: {
      plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]],
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

describe('health forms cap the date inputs at today', () => {
  it.each([
    ['water', HealthWaterFormDialog, { units: 'metric' }],
    ['weight', HealthWeightFormDialog, { weightUnits: 'metric' }],
    ['steps', HealthStepsFormDialog, {}],
    ['sleep', HealthSleepFormDialog, {}],
  ])('%s date', async (_name, component, props) => {
    const wrapper = await openDialog(component, props)
    const input = wrapper.get('input[type="date"]')

    expect(input.attributes('max')).toBe(todayIsoDate())
  })

  it.each([
    ['fasting', HealthFastingFormDialog, 1],
    ['poop', HealthPoopFormDialog, 1],
    ['sleep', HealthSleepFormDialog, 2],
  ])('%s date-time', async (_name, component, expected) => {
    const wrapper = await openDialog(component)
    const inputs = wrapper.findAll('input[type="datetime-local"]').slice(0, expected)

    expect(inputs).toHaveLength(expected)
    for (const input of inputs) {
      expect(input.attributes('max')).toBe(`${todayIsoDate()}T23:59`)
    }
  })
})
