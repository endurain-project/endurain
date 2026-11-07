import { beforeEach, describe, expect, it, vi } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import MfaSetupDialog from '@/features/security/components/MfaSetupDialog.vue'

vi.mock('@/services/http', () => ({ apiFetch: vi.fn<typeof apiFetch>() }))

/** Passthrough stub so the reka-ui portal/focus-trap is skipped and the form renders inline. */
const passthrough = { template: '<div><slot /></div>' }

async function openDialog() {
  const wrapper = mount(MfaSetupDialog, {
    props: { open: false, requirePassword: true },
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
  await flushPromises()
  return wrapper
}

describe('MfaSetupDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiFetch).mockImplementation((path) =>
      Promise.resolve(
        path === '/profile/mfa/setup'
          ? { secret: 'SEC', qr_code: 'data:image/png;base64,AAA', app_name: 'Endurain' }
          : { backup_codes: ['A'] },
      ),
    )
  })

  it('sends a code typed in groups of three without the space', async () => {
    const wrapper = await openDialog()

    await wrapper.find('#mfa-enable-code').setValue('022 643')
    await wrapper.find('#mfa-enable-password').setValue('secret')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    const enable = vi.mocked(apiFetch).mock.calls.find(([path]) => path === '/profile/mfa/enable')!
    expect(JSON.parse(String(enable[1]?.body)).mfa_code).toBe('022643')
  })

  it('sends the other-devices choice, signing them out by default', async () => {
    const wrapper = await openDialog()

    const toggle = wrapper.get<HTMLInputElement>('input[role="switch"]')
    expect(toggle.element.checked).toBe(true)

    await wrapper.find('#mfa-enable-code').setValue('022643')
    await wrapper.find('#mfa-enable-password').setValue('secret')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    const enable = vi.mocked(apiFetch).mock.calls.find(([path]) => path === '/profile/mfa/enable')!
    expect(JSON.parse(String(enable[1]?.body)).revoke_other_sessions).toBe(true)
  })

  it('keeps the other devices when the switch is turned off', async () => {
    const wrapper = await openDialog()

    await wrapper.get('input[role="switch"]').setValue(false)
    await wrapper.find('#mfa-enable-code').setValue('022643')
    await wrapper.find('#mfa-enable-password').setValue('secret')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    const enable = vi.mocked(apiFetch).mock.calls.find(([path]) => path === '/profile/mfa/enable')!
    expect(JSON.parse(String(enable[1]?.body)).revoke_other_sessions).toBe(false)
  })

  it('lets the grouping space be typed', async () => {
    const wrapper = await openDialog()

    expect(wrapper.find('#mfa-enable-code').attributes('maxlength')).toBe('7')
    expect(wrapper.find('#mfa-enable-code').attributes('inputmode')).toBe('numeric')
  })
})
