import { beforeEach, describe, expect, it, vi } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import type { GearComponentDto } from '@/features/gears/types'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import GearComponentFormDialog from '@/features/gears/components/GearComponentFormDialog.vue'
import { GEAR_TYPE } from '@/features/gears/utils/gearType'

// Replace only the network seam; keep a real `HttpError` for the dialog's
// `instanceof` check in its error path.
vi.mock('@/services/http', () => {
  class HttpError extends Error {
    constructor(
      public status: number,
      message?: string,
    ) {
      super(message)
    }
  }
  return { apiFetch: vi.fn<typeof apiFetch>(), HttpError }
})

const createdDto: GearComponentDto = {
  id: 7,
  user_id: 1,
  gear_id: 5,
  type: 'chain',
  brand: 'Shimano',
  model: 'XT',
  purchase_date: '2024-01-10',
  retired_date: null,
  active: true,
  expected_kms: 5_000_000,
  purchase_value: 45,
  current_distance: 0,
  current_time: 0,
  version: 1,
}

/** Passthrough stub so the reka-ui portal/focus-trap is skipped and the form
 * renders inline where the test can drive it. */
const passthrough = { template: '<div><slot /></div>' }

function mountDialog() {
  return mount(GearComponentFormDialog, {
    props: {
      open: true,
      gearId: 5,
      gearType: GEAR_TYPE.BICYCLE,
      availableTypes: ['chain'],
      units: 'metric' as const,
      currency: 'euro' as const,
    },
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
}

describe('GearComponentFormDialog submit', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('creates the component when the numeric fields hold a value', async () => {
    // Regression: `<input type="number">` + `v-model` yields a `number`, which
    // previously crashed `toNumberOrNull` (`value.trim()`) before any request,
    // so the submit button silently did nothing.
    vi.mocked(apiFetch).mockResolvedValue(createdDto)

    const wrapper = mountDialog()

    await wrapper.find('select').setValue('chain')
    await wrapper.find('input[name="brand"]').setValue('Shimano')
    await wrapper.find('input[name="model"]').setValue('XT')
    await wrapper.find('input[type="date"]').setValue('2024-01-10')
    await wrapper.find('input[step="0.1"]').setValue('5000') // expected distance (km)
    await wrapper.find('input[step="0.01"]').setValue('45') // purchase value

    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(apiFetch).toHaveBeenCalledTimes(1)
    expect(apiFetch).toHaveBeenCalledWith('/gear-components', {
      method: 'POST',
      body: JSON.stringify({
        gear_id: 5,
        type: 'chain',
        brand: 'Shimano',
        model: 'XT',
        purchase_date: '2024-01-10',
        retired_date: null,
        active: true,
        expected_kms: 5_000_000,
        purchase_value: 45,
      }),
    })
    expect(wrapper.emitted('success')).toBeTruthy()
  })
})
