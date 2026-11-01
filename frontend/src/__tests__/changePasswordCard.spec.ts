import { computed, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import i18n from '@/i18n'
import ChangePasswordCard from '@/features/security/components/ChangePasswordCard.vue'
import type { PasswordChangeInput } from '@/features/security/types'
import { HttpError } from '@/services/http'

const { mutateAsync, toastError } = vi.hoisted(() => ({
  toastError: vi.fn<(message: string) => void>(),
  mutateAsync: vi.fn<(input: PasswordChangeInput) => Promise<void>>().mockResolvedValue(undefined),
}))

vi.mock('@/features/config/composables/usePublicServerSettings', () => ({
  usePublicServerSettings: () => ({
    serverSettings: ref({
      password_length_regular_users: 12,
      password_length_admin_users: 12,
    }),
  }),
}))

vi.mock('@/composables/useToasts', () => ({
  useToasts: () => ({ success: vi.fn<() => void>(), error: toastError }),
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
    mutateAsync.mockReset()
    mutateAsync.mockResolvedValue(undefined)
    toastError.mockClear()
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

describe('ChangePasswordCard server refusals', () => {
  /** Fills the form and submits it. */
  async function submitFilled() {
    const wrapper = mount(ChangePasswordCard, {
      props: { mfaEnabled: false, accessType: 'regular' },
      global: { plugins: [i18n] },
    })
    await wrapper.get('#security-current-password').setValue('CurrentPassw0rd!')
    await wrapper.get('#security-new-password').setValue('Str0ng!Passw0rd')
    await wrapper.get('#security-confirm-password').setValue('Str0ng!Passw0rd')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
  }

  beforeEach(() => {
    mutateAsync.mockReset()
    toastError.mockClear()
  })

  it('names the weak new password instead of blaming the current one on a 422', async () => {
    mutateAsync.mockRejectedValue(
      new HttpError(422, 'Unprocessable', null, 'urn:endurain:error:password-too-common'),
    )
    await submitFilled()

    expect(toastError).toHaveBeenCalledWith(i18n.global.t('app.password.tooCommon'))
  })

  it('still reports a wrong current password on a 401', async () => {
    mutateAsync.mockRejectedValue(new HttpError(401, 'Unauthorized'))
    await submitFilled()

    expect(toastError).toHaveBeenCalledWith(
      i18n.global.t('settings.security.password.invalidCredentials'),
    )
  })

  it('falls back to the generic error for an unrelated 422', async () => {
    mutateAsync.mockRejectedValue(
      new HttpError(422, 'Unprocessable', null, 'urn:endurain:error:invalid-input'),
    )
    await submitFilled()

    expect(toastError).toHaveBeenCalledWith(i18n.global.t('settings.security.password.error'))
  })
})
