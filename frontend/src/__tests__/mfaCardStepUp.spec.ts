import { beforeEach, describe, expect, it, vi } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia } from 'pinia'

import { apiFetch, HttpError } from '@/services/http'
import i18n from '@/i18n'
import { useAuthStore } from '@/features/auth/stores/auth'
import MfaCard from '@/features/security/components/MfaCard.vue'

const mocks = vi.hoisted(() => ({ toastError: vi.fn<(message: string) => void>() }))

vi.mock('@/services/http', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/http')>()),
  apiFetch: vi.fn<typeof apiFetch>(),
}))
vi.mock('@/composables/useToasts', () => ({
  useToasts: () => ({ success: vi.fn<() => void>(), error: mocks.toastError }),
}))

/** Passthrough stub so the reka-ui portal/focus-trap is skipped and the form renders inline. */
const passthrough = { template: '<div><slot /></div>' }

async function mountCard() {
  const pinia = createPinia()
  useAuthStore(pinia).isAuthenticated = true
  const wrapper = mount(MfaCard, {
    props: { hasLocalPassword: true, resume: null },
    global: {
      plugins: [pinia, i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]],
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
  await flushPromises()
  return wrapper
}

/** Opens the dialog behind a button and fills its step-up fields; returns the open dialog. */
async function openDialog(wrapper: Awaited<ReturnType<typeof mountCard>>, buttonLabel: string) {
  await wrapper
    .findAll('button')
    .find((button) => button.text() === buttonLabel)!
    .trigger('click')
  await flushPromises()
  const dialog = wrapper.get('div[open="true"]')
  await dialog.get('#stepup-password').setValue('pw')
  await dialog.get('#stepup-mfa').setValue('123456')
  return dialog
}

describe('MfaCard refused step-up', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiFetch).mockImplementation((path) => {
      if (path === '/profile/mfa/status') {
        return Promise.resolve({ mfa_enabled: true })
      }
      if (path === '/profile/mfa/backup-codes/status') {
        return Promise.resolve({
          has_codes: true,
          total: 10,
          unused: 10,
          used: 0,
          created_at: null,
        })
      }
      return Promise.reject(
        new HttpError(403, 'Forbidden', null, 'urn:endurain:error:step-up-failed'),
      )
    })
  })

  it.each(['Disable', 'Regenerate backup codes'])(
    'reports invalid credentials when %s is refused',
    async (label) => {
      const wrapper = await mountCard()

      const dialog = await openDialog(wrapper, label)
      await dialog.get('form').trigger('submit')
      await flushPromises()

      expect(mocks.toastError).toHaveBeenCalledWith(
        i18n.global.t('settings.security.linked.invalidCredentials'),
      )
    },
  )
})
