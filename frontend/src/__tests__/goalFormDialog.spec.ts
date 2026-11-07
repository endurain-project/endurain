import { describe, expect, it } from 'vitest'

import { mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import i18n from '@/i18n'
import GoalFormDialog from '@/features/goals/components/GoalFormDialog.vue'

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
})
