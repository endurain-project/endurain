import { describe, expect, it, vi } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import { HttpError, apiFetch } from '@/services/http'
import i18n from '@/i18n'
import GoalFormDialog from '@/features/goals/components/GoalFormDialog.vue'

// Only the network seam is replaced; the real `HttpError` stays so `instanceof` checks hold.
vi.mock('@/services/http', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/http')>()),
  apiFetch: vi.fn<typeof apiFetch>(),
}))

/** Passthrough stub so the reka-ui portal/focus-trap is skipped and the form renders inline. */
const passthrough = { template: '<div><slot /></div>' }

describe('GoalFormDialog', () => {
  it('explains why Save is disabled when the target is 0', async () => {
    const wrapper = mount(GoalFormDialog, {
      props: { open: false, goal: null, units: 'metric' },
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
    const message = 'Enter a value greater than 0.'

    expect(wrapper.text()).not.toContain(message)

    await wrapper.get('input[type="number"]').setValue('0')

    expect(wrapper.text()).toContain(message)
  })

  it('shows a 422 on the target field instead of a toast', async () => {
    vi.mocked(apiFetch).mockRejectedValue(
      new HttpError(
        422,
        'Unprocessable Content',
        null,
        'urn:endurain:error:validation-failed',
        null,
        [{ field: 'body.goal_distance', message: 'm', type: 'less_than_equal' }],
      ),
    )
    const wrapper = mount(GoalFormDialog, {
      props: { open: false, goal: null, units: 'metric' },
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
    const type = wrapper.findAll('select')[2]!
    await type.setValue('distance')
    await wrapper.get('input[type="number"]').setValue('999999')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain(i18n.global.t('app.fieldError.tooLarge'))
    expect(wrapper.emitted('error')).toBeUndefined()
  })
})
