import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { ManagedUser } from '@/features/users/types'

import i18n from '@/i18n'
import UserListItem from '@/features/users/components/UserListItem.vue'

const base: ManagedUser = {
  id: 2,
  version: 1,
  name: 'Ada',
  username: 'ada',
  email: 'ada@example.com',
  accessType: 'regular',
  active: false,
  emailVerified: true,
  pendingEmail: null,
  pendingEmailExpiresAt: null,
  pendingAdminApproval: true,
  mfaEnabled: false,
  externalAuthCount: 0,
  preferredLanguage: 'en',
  gender: 'unspecified',
  units: 'metric',
  currency: 'euro',
  firstDayOfWeek: 'monday',
  city: null,
  birthdate: null,
  height: null,
  maxHeartRate: null,
  photoPath: null,
  avatarUrl: null,
}

function mountItem(user: ManagedUser) {
  return mount(UserListItem, {
    props: { user, isSelf: false },
    global: {
      plugins: [i18n],
      stubs: { RouterLink: { template: '<a><slot /></a>' } },
    },
  })
}

function button(wrapper: ReturnType<typeof mountItem>, label: string) {
  return wrapper.find(`button[aria-label="${label}"]`)
}

describe('UserListItem approval actions', () => {
  it('emits approve and reject for a pending sign-up', async () => {
    const wrapper = mountItem(base)

    await button(wrapper, 'Approve').trigger('click')
    await button(wrapper, 'Reject').trigger('click')

    expect(wrapper.emitted('approve')).toEqual([[base]])
    expect(wrapper.emitted('reject')).toEqual([[base]])
  })

  it('disables both actions until the email is verified', () => {
    const wrapper = mountItem({ ...base, emailVerified: false })

    expect(button(wrapper, 'Approve').attributes('disabled')).toBeDefined()
    expect(button(wrapper, 'Reject').attributes('disabled')).toBeDefined()
  })

  it('hides the actions for a user that is not pending', () => {
    const wrapper = mountItem({ ...base, pendingAdminApproval: false })

    expect(button(wrapper, 'Approve').exists()).toBe(false)
    expect(button(wrapper, 'Reject').exists()).toBe(false)
  })
})
