import { computed, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

import i18n from '@/i18n'
import ChangePasswordCard from '@/features/security/components/ChangePasswordCard.vue'

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
    isPending: computed(() => false),
  }),
}))

describe('ChangePasswordCard', () => {
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
})
