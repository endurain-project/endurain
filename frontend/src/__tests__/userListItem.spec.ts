import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { ManagedUser } from '@/features/users/types'

import i18n from '@/i18n'
import UserListItem from '@/features/users/components/UserListItem.vue'
import { userUuid } from './fixtures/activity'

const base: ManagedUser = {
  id: userUuid(2),
  version: 1,
  name: 'Ada',
  username: 'ada',
  email: 'ada@example.com',
  accessType: 'regular',
  active: false,
  emailVerified: true,
  pendingEmail: null,
  pendingEmailExpiresAt: null,
  deletionRequestedAt: null,
  pendingAdminApproval: true,
  mfaEnabled: false,
  externalAuthCount: 0,
  preferredLanguage: 'en',
  gender: 'unspecified',
  units: 'metric',
  weightUnits: null,
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
      stubs: { RouterLink: { template: '<a><slot /></a>' }, UserDeletionBadge: true },
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

describe('UserListItem name', () => {
  it('isolates the name so its text direction cannot reorder the text beside it', () => {
    const wrapper = mountItem({ ...base, name: 'Ada ‮evil' })

    expect(wrapper.find('bdi').text()).toBe('Ada ‮evil')
  })
})

describe('UserListItem deletion badge', () => {
  it('marks a user whose deletion is queued', () => {
    const wrapper = mountItem({ ...base, deletionRequestedAt: '2026-11-08T10:00:00Z' })

    expect(wrapper.findComponent({ name: 'UserDeletionBadge' }).exists()).toBe(true)
  })

  it('leaves the mark off a user who is not being deleted', () => {
    const wrapper = mountItem(base)

    expect(wrapper.findComponent({ name: 'UserDeletionBadge' }).exists()).toBe(false)
  })
})
