import { beforeEach, describe, expect, it, vi } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import { HttpError, apiFetch } from '@/services/http'
import i18n from '@/i18n'
import IdentityProviderFormDialog from '@/features/identityProviders/components/IdentityProviderFormDialog.vue'

// Replace only the network seam; keep the real `HttpError` for the dialog's
// `instanceof` checks in its error path.
vi.mock('@/services/http', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/http')>()),
  apiFetch: vi.fn<typeof import('@/services/http').apiFetch>(),
}))

/** Passthrough stub so the reka-ui portal/focus-trap is skipped and the form
 * renders inline where the test can drive it. */
const passthrough = { template: '<div><slot /></div>' }

function mountDialog() {
  return mount(IdentityProviderFormDialog, {
    props: { open: true, provider: null, templates: [] },
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

/** Fills the create form with valid values and submits it. */
async function submitValidForm(wrapper: ReturnType<typeof mountDialog>) {
  await wrapper.find('input[name="name"]').setValue('Authentik')
  await wrapper.find('input[name="slug"]').setValue('authentik')
  await wrapper.find('input[name="issuerUrl"]').setValue('https://auth.example.com')
  await wrapper.find('input[name="clientId"]').setValue('endurain')
  await wrapper.find('input[name="clientSecret"]').setValue('secret')
  await wrapper.find('form').trigger('submit')
  await flushPromises()
}

describe('IdentityProviderFormDialog save errors', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('explains a refused issuer URL when the backend answers 400', async () => {
    vi.mocked(apiFetch).mockRejectedValue(new HttpError(400, 'Bad Request'))

    const wrapper = mountDialog()
    await submitValidForm(wrapper)

    expect(apiFetch).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('error')).toEqual([
      [i18n.global.t('settings.idp.form.issuerUrlRefused')],
    ])
  })

  it('keeps the generic save error for other failures', async () => {
    vi.mocked(apiFetch).mockRejectedValue(new HttpError(500, 'Internal Server Error'))

    const wrapper = mountDialog()
    await submitValidForm(wrapper)

    expect(wrapper.emitted('error')).toEqual([[i18n.global.t('settings.idp.form.saveError')]])
  })
})
