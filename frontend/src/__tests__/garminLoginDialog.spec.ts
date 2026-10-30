import { beforeEach, describe, expect, it, vi } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import GarminLoginDialog from '@/features/integrations/components/GarminLoginDialog.vue'

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

vi.mock('@/composables/useRealtime', () => ({
  useRealtime: () => ({ on: () => () => {} }),
}))

/** Passthrough stub so the reka-ui portal/focus-trap is skipped and the form
 * renders inline where the test can drive it. */
const passthrough = { template: '<div><slot /></div>' }

function mountDialog() {
  return mount(GarminLoginDialog, {
    props: { open: true },
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

describe('GarminLoginDialog submit', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('starts only one Garmin login while the first is still pending', async () => {
    // The link request stays pending while the backend waits for the MFA code.
    // Regression: Enter in a field or a double click sent a second link, which
    // made Garmin issue a second code, so one of the two logins always failed.
    vi.mocked(apiFetch).mockReturnValue(new Promise(() => {}))
    const wrapper = mountDialog()

    await wrapper.find('#garmin-username').setValue('rider@example.com')
    await wrapper.find('input[type="password"]').setValue('pw')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    const linkCalls = vi
      .mocked(apiFetch)
      .mock.calls.filter(([path]) => path === '/garminconnect/link')
    expect(linkCalls).toHaveLength(1)
  })
})
