import { beforeEach, describe, expect, it, vi } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import type { Component } from 'vue'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import type { HealthTargets } from '@/features/health/types'
import HealthFastingTargetDialog from '@/features/health/components/HealthFastingTargetDialog.vue'
import HealthPoopTargetDialog from '@/features/health/components/HealthPoopTargetDialog.vue'
import HealthSleepTargetDialog from '@/features/health/components/HealthSleepTargetDialog.vue'
import HealthStepsTargetDialog from '@/features/health/components/HealthStepsTargetDialog.vue'
import HealthWaterTargetDialog from '@/features/health/components/HealthWaterTargetDialog.vue'
import HealthWeightTargetDialog from '@/features/health/components/HealthWeightTargetDialog.vue'

vi.mock('@/services/http', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/http')>()),
  apiFetch: vi.fn<typeof apiFetch>(),
}))

/** Passthrough stub so the reka-ui portal/focus-trap is skipped and the form renders inline. */
const passthrough = { template: '<div><slot /></div>' }

const ERROR = 'Enter a value greater than 0, or leave it empty to remove the target.'

const targets: HealthTargets = {
  id: 1,
  userId: 1,
  version: 3,
  sleepSeconds: 28800,
  steps: 10000,
  weightKg: 70,
  fastingSeconds: 57600,
  waterMl: 2000,
  poopCount: 1,
}

async function openDialog(component: Component, extraProps: Record<string, unknown>) {
  const wrapper = mount(component, {
    props: { open: false, targets, ...extraProps },
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

const single = [
  ['steps', HealthStepsTargetDialog, {}],
  ['poop', HealthPoopTargetDialog, {}],
  ['water', HealthWaterTargetDialog, { units: 'metric' }],
  ['weight', HealthWeightTargetDialog, { weightUnits: 'metric' }],
] as const

const pairs = [
  ['sleep', HealthSleepTargetDialog],
  ['fasting', HealthFastingTargetDialog],
] as const

describe('health target dialogs', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiFetch).mockResolvedValue({} as never)
  })

  describe.each(single)('%s target', (_name, component, extraProps) => {
    it('blocks a zero target with an error and sends no request', async () => {
      const wrapper = await openDialog(component, extraProps)
      await wrapper.get('input').setValue('0')
      await wrapper.find('form').trigger('submit')
      await flushPromises()

      expect(wrapper.text()).toContain(ERROR)
      expect(apiFetch).not.toHaveBeenCalled()
    })

    it('clears the target when the field is empty', async () => {
      const wrapper = await openDialog(component, extraProps)
      await wrapper.get('input').setValue('')
      await wrapper.find('form').trigger('submit')
      await flushPromises()

      expect(wrapper.text()).not.toContain(ERROR)
      expect(apiFetch).toHaveBeenCalledTimes(1)
      const body = JSON.stringify(vi.mocked(apiFetch).mock.calls[0])
      expect(body).toContain('null')
    })
  })

  describe.each([
    ['water', HealthWaterTargetDialog, { units: 'imperial' }],
    ['weight', HealthWeightTargetDialog, { weightUnits: 'imperial' }],
  ] as const)('%s target in imperial units', (_name, component, extraProps) => {
    it('sends nothing when saved unchanged, so the stored value does not drift', async () => {
      const wrapper = await openDialog(component, extraProps)
      await wrapper.find('form').trigger('submit')
      await flushPromises()

      expect(apiFetch).not.toHaveBeenCalled()
      expect(wrapper.emitted('update:open')?.[0]).toEqual([false])
    })
  })

  describe.each(pairs)('%s target', (_name, component) => {
    it('blocks a zero total with an error and sends no request', async () => {
      const wrapper = await openDialog(component, {})
      const [hours, minutes] = wrapper.findAll('input')
      await hours!.setValue('0')
      await minutes!.setValue('0')
      await wrapper.find('form').trigger('submit')
      await flushPromises()

      expect(wrapper.text()).toContain(ERROR)
      expect(apiFetch).not.toHaveBeenCalled()
    })

    it('clears the target when both fields are empty', async () => {
      const wrapper = await openDialog(component, {})
      const [hours, minutes] = wrapper.findAll('input')
      await hours!.setValue('')
      await minutes!.setValue('')
      await wrapper.find('form').trigger('submit')
      await flushPromises()

      expect(wrapper.text()).not.toContain(ERROR)
      expect(apiFetch).toHaveBeenCalledTimes(1)
      expect(JSON.stringify(vi.mocked(apiFetch).mock.calls[0])).toContain('null')
    })
  })
})
