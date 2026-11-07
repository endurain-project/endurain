import { beforeEach, describe, expect, it, vi } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia } from 'pinia'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import { useAuthStore } from '@/features/auth/stores/auth'
import MfaCard from '@/features/security/components/MfaCard.vue'

vi.mock('@/services/http', () => ({ apiFetch: vi.fn<typeof apiFetch>() }))
vi.mock('@/composables/useToasts', () => ({
  useToasts: () => ({ success: vi.fn<() => void>(), error: vi.fn<() => void>() }),
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

/** Returns the body of the last request sent to a path. */
function sentBody(path: string): Record<string, unknown> {
  const calls = vi.mocked(apiFetch).mock.calls.filter(([url]) => url === path)
  return JSON.parse(String(calls[calls.length - 1]![1]?.body)) as Record<string, unknown>
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

describe('MfaCard sign out other devices', () => {
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
      if (path === '/profile/mfa/backup-codes') {
        return Promise.resolve({ codes: ['A'], created_at: '2026-01-01T00:00:00Z' })
      }
      return Promise.resolve(undefined)
    })
  })

  it('signs out the other devices when disabling MFA, by default', async () => {
    const wrapper = await mountCard()

    const dialog = await openDialog(wrapper, 'Disable')
    expect(dialog.get<HTMLInputElement>('input[role="switch"]').element.checked).toBe(true)
    await dialog.get('form').trigger('submit')
    await flushPromises()

    expect(sentBody('/profile/mfa/disable').revoke_other_sessions).toBe(true)
  })

  it('keeps the other devices when disabling MFA with the switch off', async () => {
    const wrapper = await mountCard()

    const dialog = await openDialog(wrapper, 'Disable')
    await dialog.get('input[role="switch"]').setValue(false)
    await dialog.get('form').trigger('submit')
    await flushPromises()

    expect(sentBody('/profile/mfa/disable').revoke_other_sessions).toBe(false)
  })

  it('sends the choice with new backup codes', async () => {
    const wrapper = await mountCard()

    const dialog = await openDialog(wrapper, 'Regenerate backup codes')
    await dialog.get('input[role="switch"]').setValue(false)
    await dialog.get('form').trigger('submit')
    await flushPromises()

    expect(sentBody('/profile/mfa/backup-codes').revoke_other_sessions).toBe(false)
  })
})
