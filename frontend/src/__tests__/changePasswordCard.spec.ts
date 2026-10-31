import { computed, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import i18n from '@/i18n'
import ChangePasswordCard from '@/features/security/components/ChangePasswordCard.vue'
import type { PasswordChangeInput } from '@/features/security/types'

const { mutateAsync } = vi.hoisted(() => ({
  mutateAsync: vi.fn<(input: PasswordChangeInput) => Promise<void>>().mockResolvedValue(undefined),
}))

vi.mock('@/features/config/composables/usePublicServerSettings', () => ({
  usePublicServerSettings: () => ({
    serverSettings: ref({
      password_type: 'strict',
      password_length_regular_users: 12,
      password_length_admin_users: 12,
    }),
  }),
}))

vi.mock('@/features/security/composables/useSecurity', () => ({
  useChangePasswordMutation: () => ({
    mutate: vi.fn<() => void>(),
    mutateAsync,
    isPending: computed(() => false),
  }),
}))

/** Returns the "sign out of other devices" switch's native checkbox. */
function revokeSwitch(wrapper: ReturnType<typeof mount>) {
  return wrapper.get<HTMLInputElement>('input[role="switch"]')
}

describe('ChangePasswordCard', () => {
  beforeEach(() => {
    mutateAsync.mockClear()
  })

  it('shows the requirements hint as an error only once the new password is invalid', async () => {
    const wrapper = mount(ChangePasswordCard, {
      props: { mfaEnabled: false, accessType: 'regular' },
      global: { plugins: [i18n] },
    })
    const hint = wrapper.get('#security-new-password-hint')

    expect(hint.classes()).toContain('text-hint')
    expect(hint.classes()).not.toContain('text-field-error')

    await wrapper.get('#security-new-password').setValue('short')

    expect(hint.classes()).toContain('text-field-error')
    expect(hint.classes()).not.toContain('text-hint')
  })

  it('renders the sign-out-of-other-devices switch checked by default', () => {
    const wrapper = mount(ChangePasswordCard, {
      props: { mfaEnabled: false, accessType: 'regular' },
      global: { plugins: [i18n] },
    })

    expect(revokeSwitch(wrapper).element.checked).toBe(true)
  })

  it('submits revokeOtherSessions as true without touching the switch', async () => {
    const wrapper = mount(ChangePasswordCard, {
      props: { mfaEnabled: false, accessType: 'regular' },
      global: { plugins: [i18n] },
    })

    await wrapper.get('#security-current-password').setValue('CurrentPassw0rd!')
    await wrapper.get('#security-new-password').setValue('Str0ng!Passw0rd')
    await wrapper.get('#security-confirm-password').setValue('Str0ng!Passw0rd')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(mutateAsync).toHaveBeenCalledWith(expect.objectContaining({ revokeOtherSessions: true }))
  })

  it('keeps the switch checked after a successful submit', async () => {
    const wrapper = mount(ChangePasswordCard, {
      props: { mfaEnabled: false, accessType: 'regular' },
      global: { plugins: [i18n] },
    })

    await wrapper.get('#security-current-password').setValue('CurrentPassw0rd!')
    await wrapper.get('#security-new-password').setValue('Str0ng!Passw0rd')
    await wrapper.get('#security-confirm-password').setValue('Str0ng!Passw0rd')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(revokeSwitch(wrapper).element.checked).toBe(true)
  })
})
