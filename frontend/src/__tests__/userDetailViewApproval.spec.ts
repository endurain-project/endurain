import { beforeEach, describe, expect, it, vi } from 'vitest'

import { computed, ref } from 'vue'
import { mount } from '@vue/test-utils'

import type { ManagedUser } from '@/features/users/types'

import i18n from '@/i18n'
import UserDetailView from '@/features/users/views/UserDetailView.vue'
import { userUuid } from './fixtures/activity'

const state = vi.hoisted(() => ({
  requireVerification: false,
  user: null as unknown,
}))

vi.mock('vue-router', () => ({
  RouterLink: { template: '<a><slot /></a>' },
  useRoute: () => ({ params: { id: '00000000-0000-4000-8000-000000000002' }, path: '' }),
  useRouter: () => ({ push: vi.fn<(to: unknown) => Promise<void>>() }),
}))
vi.mock('@/features/config/composables/usePublicServerSettings', () => ({
  usePublicServerSettings: () => ({
    serverSettings: computed(() => ({
      signup_require_email_verification: state.requireVerification,
    })),
  }),
}))
vi.mock('@/features/auth/composables/useCurrentUser', () => ({
  useCurrentUser: () => ({ data: ref(null) }),
}))
vi.mock('@/features/security/composables/useIdpStepUp', () => ({
  consumeIdpStepUpReturn: () => null,
}))
vi.mock('@/features/users/composables/useUsers', () => ({
  useApproveUserMutation: () => ({ isPending: ref(false), mutate: vi.fn<() => void>() }),
  useDeleteUserPhotoMutation: () => ({ isPending: ref(false), mutate: vi.fn<() => void>() }),
  useUploadUserPhotoMutation: () => ({ isPending: ref(false), mutate: vi.fn<() => void>() }),
  useUserQuery: () => ({
    data: ref(state.user),
    isPending: ref(false),
    isError: ref(false),
    refetch: vi.fn<() => void>(),
  }),
}))

function pendingUser(emailVerified: boolean): ManagedUser {
  return {
    id: userUuid(2),
    version: 1,
    name: 'Ada',
    username: 'ada',
    email: 'ada@example.com',
    accessType: 'regular',
    active: false,
    emailVerified,
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
}

function mountView() {
  return mount(UserDetailView, {
    global: {
      plugins: [i18n],
      stubs: {
        UserCredentialActionDialog: true,
        UserDeleteDialog: true,
        UserFormDialog: true,
        UserIdentityProvidersList: true,
        UserPasswordDialog: true,
        UserApiKeysList: true,
        UserSessionsList: true,
        UserStatusBadges: true,
        ConfirmDialog: true,
      },
    },
  })
}

function actionButton(wrapper: ReturnType<typeof mountView>, key: string) {
  const label = i18n.global.t(key)
  return wrapper.findAll('button').find((b) => b.text() === label)
}

describe('UserDetailView pending sign-up actions', () => {
  beforeEach(() => {
    state.requireVerification = false
  })

  it('disables approve, not reject, and shows the hint when verification is required', () => {
    state.requireVerification = true
    state.user = pendingUser(false)
    const wrapper = mountView()

    expect(
      actionButton(wrapper, 'settings.users.approval.approve')?.attributes('disabled'),
    ).toBeDefined()
    expect(
      actionButton(wrapper, 'settings.users.approval.reject')?.attributes('disabled'),
    ).toBeUndefined()
    expect(wrapper.text()).toContain(i18n.global.t('settings.users.approval.emailUnverifiedHint'))
  })

  it('enables both and hides the hint when verification is not required', () => {
    state.user = pendingUser(false)
    const wrapper = mountView()

    expect(
      actionButton(wrapper, 'settings.users.approval.approve')?.attributes('disabled'),
    ).toBeUndefined()
    expect(
      actionButton(wrapper, 'settings.users.approval.reject')?.attributes('disabled'),
    ).toBeUndefined()
    expect(wrapper.text()).not.toContain(
      i18n.global.t('settings.users.approval.emailUnverifiedHint'),
    )
  })
})
