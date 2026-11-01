import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import i18n from '@/i18n'
import UserPasswordDialog from '@/features/users/components/UserPasswordDialog.vue'
import { HttpError } from '@/services/http'

const { mutateAsync } = vi.hoisted(() => ({
  mutateAsync: vi.fn<(input: unknown) => Promise<void>>(),
}))

vi.mock('@/features/users/composables/useUsers', () => ({
  useChangeUserPasswordMutation: () => ({ mutateAsync }),
}))
vi.mock('@/features/config/composables/usePublicServerSettings', () => ({
  usePublicServerSettings: () => ({
    serverSettings: ref({ password_length_regular_users: 8, password_length_admin_users: 20 }),
  }),
}))

/** Passthrough stub so the dialog portal is skipped and the form renders inline. */
const passthrough = { template: '<div><slot /></div>' }

/**
 * Opens the dialog, fills a valid password and submits.
 *
 * @returns The mounted wrapper after the submit settled.
 */
async function submitFilled() {
  const wrapper = mount(UserPasswordDialog, {
    props: { open: false, userId: 2, username: 'bob', accessType: 'admin' },
    global: {
      plugins: [i18n],
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
  await wrapper.get('input[name="new-password"]').setValue('a-long-enough-password-1')
  await wrapper.get('input[name="confirm-password"]').setValue('a-long-enough-password-1')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  return wrapper
}

describe('UserPasswordDialog weak password', () => {
  beforeEach(() => {
    mutateAsync.mockReset()
  })

  it('emits the minimum of the target user tier when the password is too short', async () => {
    mutateAsync.mockRejectedValue(
      new HttpError(422, 'Unprocessable', null, 'urn:endurain:error:password-too-short'),
    )
    const wrapper = await submitFilled()

    expect(wrapper.emitted('error')?.[0]).toEqual([
      i18n.global.t('app.password.tooShort', { min: 20 }),
    ])
  })

  it('keeps the generic message for any other 422', async () => {
    mutateAsync.mockRejectedValue(
      new HttpError(422, 'Unprocessable', null, 'urn:endurain:error:invalid-input'),
    )
    const wrapper = await submitFilled()

    expect(wrapper.emitted('error')?.[0]).toEqual([i18n.global.t('app.password.invalid')])
  })
})
