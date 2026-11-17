import { mount } from '@vue/test-utils'
import { computed } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ManagedUser } from '@/features/users/types'

import i18n from '@/i18n'
import UserListItem from '@/features/users/components/UserListItem.vue'
import { userUuid } from './fixtures/activity'

const { requireVerification } = vi.hoisted(() => ({ requireVerification: { value: false } }))

vi.mock('@/features/config/composables/usePublicServerSettings', () => ({
  usePublicServerSettings: () => ({
    serverSettings: computed(() => ({
      signup_require_email_verification: requireVerification.value,
    })),
  }),
}))

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
  beforeEach(() => {
    requireVerification.value = false
  })

  it('emits approve and reject for a pending sign-up', async () => {
    const wrapper = mountItem(base)

    await button(wrapper, 'Approve').trigger('click')
    await button(wrapper, 'Reject').trigger('click')

    expect(wrapper.emitted('approve')).toEqual([[base]])
    expect(wrapper.emitted('reject')).toEqual([[base]])
  })

  it('disables approve, not reject, for an unverified email when the server requires verification', () => {
    requireVerification.value = true
    const wrapper = mountItem({ ...base, emailVerified: false })

    expect(button(wrapper, 'Approve').attributes('disabled')).toBeDefined()
    expect(button(wrapper, 'Reject').attributes('disabled')).toBeUndefined()
  })

  it('allows approve for an unverified email when the server does not require verification', () => {
    const wrapper = mountItem({ ...base, emailVerified: false })

    expect(button(wrapper, 'Approve').attributes('disabled')).toBeUndefined()
    expect(button(wrapper, 'Reject').attributes('disabled')).toBeUndefined()
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
