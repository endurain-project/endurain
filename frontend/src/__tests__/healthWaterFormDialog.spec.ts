import { beforeEach, describe, expect, it, vi } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import type { WaterEntry } from '@/features/health/types'

import { HttpError, apiFetch } from '@/services/http'
import i18n from '@/i18n'
import HealthWaterFormDialog from '@/features/health/components/HealthWaterFormDialog.vue'

// Only the network seam is replaced; the real `HttpError` stays so `instanceof` checks hold.
vi.mock('@/services/http', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/http')>()),
  apiFetch: vi.fn<typeof apiFetch>(),
}))

/** Passthrough stub so the reka-ui portal/focus-trap is skipped and the form renders inline. */
const passthrough = { template: '<div><slot /></div>' }

async function openDialog(entry: WaterEntry | null = null) {
  const wrapper = mount(HealthWaterFormDialog, {
    props: { open: false, entry, units: 'metric' },
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

describe('HealthWaterFormDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('tells the user to edit the entry when the day already has one', async () => {
    vi.mocked(apiFetch).mockRejectedValue(
      new HttpError(409, 'Conflict', null, 'urn:endurain:error:conflict'),
    )
    const wrapper = await openDialog()
    await wrapper.get('input[type="number"]').setValue('500')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.emitted('error')?.[0]).toEqual([
      'A water entry for that day already exists. Edit it instead of adding another.',
    ])
  })

  it('shows a 422 on the amount field instead of a toast', async () => {
    vi.mocked(apiFetch).mockRejectedValue(
      new HttpError(
        422,
        'Unprocessable Content',
        null,
        'urn:endurain:error:validation-failed',
        null,
        [{ field: 'body.amount_ml', message: 'm', type: 'less_than_equal' }],
      ),
    )
    const wrapper = await openDialog()
    await wrapper.get('input[type="number"]').setValue('500')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain(i18n.global.t('app.fieldError.tooLarge'))
    expect(wrapper.emitted('error')).toBeUndefined()
  })

  it('keeps the generic message for other failures', async () => {
    vi.mocked(apiFetch).mockRejectedValue(new HttpError(500, 'Server Error'))
    const wrapper = await openDialog()
    await wrapper.get('input[type="number"]').setValue('500')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.emitted('error')?.[0]).toEqual([
      "Couldn't save your water entry. Please try again.",
    ])
  })

  it('sends no request and closes when an edit changed nothing', async () => {
    const wrapper = await openDialog({
      id: '00000000-0000-4000-8000-000000000007',
      userId: 1,
      version: 2,
      date: '2026-10-30',
      amountMl: 1500,
      source: null,
    })
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(apiFetch).not.toHaveBeenCalled()
    expect(wrapper.emitted('update:open')?.slice(-1)[0]).toEqual([false])
  })
})
