import { beforeEach, describe, expect, it, vi } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import ActivityEditDialog from '@/features/activities/components/ActivityEditDialog.vue'
import { makeActivity } from './fixtures/activity'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
  HttpError: class extends Error {},
}))

/** Passthrough stub so the reka-ui portal/focus-trap is skipped and the form renders inline. */
const passthrough = { template: '<div><slot /></div>' }

async function openDialog() {
  const wrapper = mount(ActivityEditDialog, {
    props: { open: false, activity: makeActivity() },
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

describe('ActivityEditDialog name', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows a required-name error for a blank name and sends no request', async () => {
    const wrapper = await openDialog()
    const name = wrapper.find('input')

    await name.setValue('   ')
    await name.trigger('blur')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain(i18n.global.t('activities.edit.nameRequired'))
    expect(apiFetch).not.toHaveBeenCalled()
  })
})
