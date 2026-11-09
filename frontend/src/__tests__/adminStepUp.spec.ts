import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref, type Plugin } from 'vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import type { IdpStepUpResume } from '@/features/security/composables/useIdpStepUp'
import type { ManagedUser, UserIdentityProvider, UserSession } from '@/features/users/types'

import i18n from '@/i18n'
import { HttpError } from '@/services/http'
import UserDeleteDialog from '@/features/users/components/UserDeleteDialog.vue'
import UserDetailView from '@/features/users/views/UserDetailView.vue'
import UserFormDialog from '@/features/users/components/UserFormDialog.vue'
import UserIdentityProvidersList from '@/features/users/components/UserIdentityProvidersList.vue'
import UserSessionsList from '@/features/users/components/UserSessionsList.vue'

const mocks = vi.hoisted(() => ({
  deleteMutate: vi.fn<(...args: unknown[]) => void>(),
  unlinkMutate: vi.fn<(...args: unknown[]) => void>(),
  providers: [] as UserIdentityProvider[],
  mfaResetMutate: vi.fn<(...args: unknown[]) => void>(),
  requireChangeMutate: vi.fn<(...args: unknown[]) => void>(),
  revokeMutate: vi.fn<(...args: unknown[]) => void>(),
  revokeOthersMutate: vi.fn<(...args: unknown[]) => void>(),
  sessions: [] as UserSession[],
  toastError: vi.fn<(message: string) => void>(),
  push: vi.fn<(to: unknown) => void>(),
  user: null as ManagedUser | null,
}))

vi.mock('vue-router', () => ({
  RouterLink: { template: '<a><slot /></a>' },
  useRoute: () => ({ params: { id: '7' }, path: '/settings/users/7' }),
  useRouter: () => ({ push: mocks.push }),
}))
vi.mock('@/composables/useToasts', () => ({
  useToasts: () => ({ success: vi.fn<() => void>(), error: mocks.toastError }),
}))
vi.mock('@/features/auth/composables/useCurrentUser', () => ({
  useCurrentUser: () => ({ data: ref({ id: 1 }) }),
}))
vi.mock('@/features/security/composables/useAdminStepUp', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/security/composables/useAdminStepUp')>()),
  useAdminStepUp: () => ({ requirePassword: ref(true), requireMfa: ref(false) }),
}))
vi.mock('@/features/users/composables/useUsers', () => ({
  useDeleteUserMutation: () => ({ mutate: mocks.deleteMutate, isPending: ref(false) }),
  useResetUserMfaMutation: () => ({ mutate: mocks.mfaResetMutate, isPending: ref(false) }),
  useRequireUserPasswordChangeMutation: () => ({
    mutate: mocks.requireChangeMutate,
    isPending: ref(false),
  }),
  useApproveUserMutation: () => ({ mutate: vi.fn<() => void>(), isPending: ref(false) }),
  useDeleteUserPhotoMutation: () => ({ mutate: vi.fn<() => void>(), isPending: ref(false) }),
  useUploadUserPhotoMutation: () => ({ mutate: vi.fn<() => void>(), isPending: ref(false) }),
  useUserQuery: () => ({
    data: ref(mocks.user),
    isPending: ref(false),
    isError: ref(false),
    refetch: vi.fn<() => void>(),
  }),
}))
vi.mock('@/features/users/composables/useUserIdentityProviders', () => ({
  useUserIdentityProvidersQuery: () => ({
    data: ref(mocks.providers),
    isPending: ref(false),
    isError: ref(false),
    refetch: vi.fn<() => void>(),
  }),
  useUnlinkUserIdentityProviderMutation: () => ({
    mutate: mocks.unlinkMutate,
    isPending: ref(false),
  }),
}))

vi.mock('@/features/auth/stores/auth', () => ({
  useAuthStore: () => ({ sessionId: ref('current') }),
}))
vi.mock('@/features/users/composables/useUserSessions', () => ({
  useUserSessionsQuery: () => ({
    data: ref(mocks.sessions),
    isPending: ref(false),
    isError: ref(false),
    refetch: vi.fn<() => void>(),
  }),
  useRevokeUserSessionMutation: () => ({ mutate: mocks.revokeMutate, isPending: ref(false) }),
  useRevokeOtherUserSessionsMutation: () => ({
    mutate: mocks.revokeOthersMutate,
    isPending: ref(false),
  }),
}))

const passthrough = { template: '<div><slot /></div>' }
const stubs = {
  Dialog: passthrough,
  DialogContent: passthrough,
  DialogHeader: passthrough,
  DialogTitle: passthrough,
  DialogDescription: passthrough,
  DialogFooter: passthrough,
}
const plugins = (): (Plugin | [Plugin, ...unknown[]])[] => [
  i18n,
  [VueQueryPlugin, { queryClient: new QueryClient() }],
]

function managedUser(overrides: Partial<ManagedUser> = {}): ManagedUser {
  return { id: 7, version: 3, name: 'Bob', username: 'bob', ...overrides } as ManagedUser
}

function resumeFor(action: IdpStepUpResume['action'], pending: Record<string, unknown>) {
  return { action, reauth: { ticket: 't1', codeVerifier: 'v1' }, pending } as IdpStepUpResume
}

beforeEach(() => {
  mocks.deleteMutate.mockReset()
  mocks.unlinkMutate.mockReset()
  mocks.revokeMutate.mockReset()
  mocks.mfaResetMutate.mockReset()
  mocks.requireChangeMutate.mockReset()
  mocks.revokeOthersMutate.mockReset()
  mocks.sessions = []
  mocks.toastError.mockReset()
  mocks.push.mockReset()
  mocks.providers = []
  mocks.user = null
  sessionStorage.clear()
  history.replaceState(null, '', '/settings/users/7')
})

describe('UserDeleteDialog', () => {
  function mountDialog(props: Record<string, unknown>) {
    return mount(UserDeleteDialog, {
      props: { open: false, user: managedUser(), variant: 'delete', resume: null, ...props },
      global: { plugins: plugins(), stubs },
    })
  }

  it('sends the administrator step-up with the version it read', async () => {
    const wrapper = mountDialog({ open: true })
    await wrapper.get('#stepup-password').setValue('admin-pw')
    await wrapper.get('form').trigger('submit')

    expect(mocks.deleteMutate).toHaveBeenCalledWith(
      {
        id: 7,
        version: 3,
        stepUp: { currentPassword: 'admin-pw', mfaCode: null, idpReauth: null },
      },
      expect.any(Object),
    )
  })

  it('keeps the dialog open and reports invalid credentials on a refused step-up', async () => {
    const wrapper = mountDialog({ open: true })
    await wrapper.get('#stepup-password').setValue('wrong')
    await wrapper.get('form').trigger('submit')
    const { onError } = mocks.deleteMutate.mock.calls[0]![1] as { onError: (e: unknown) => void }

    onError(new HttpError(403, 'Forbidden', null, 'urn:endurain:error:step-up-failed'))

    expect(mocks.toastError).toHaveBeenCalledWith(
      i18n.global.t('settings.security.linked.invalidCredentials'),
    )
    expect(wrapper.emitted('update:open')).toBeUndefined()
  })

  it('reopens for the same user and variant after the identity-provider return', async () => {
    const resume = resumeFor('admin_user_delete', { userId: 7, variant: 'delete' })
    const wrapper = mountDialog({ resume })
    await flushPromises()

    expect(wrapper.emitted('update:open')?.[0]).toEqual([true])
  })

  it.each([
    ['another user', { userId: 8, variant: 'delete' }],
    ['the other variant', { userId: 7, variant: 'reject' }],
  ])('ignores a return that was started for %s', async (_label, pending) => {
    const wrapper = mountDialog({ resume: resumeFor('admin_user_delete', pending) })
    await flushPromises()

    expect(wrapper.emitted('update:open')).toBeUndefined()
  })
})

describe('UserIdentityProvidersList unlink', () => {
  const provider: UserIdentityProvider = {
    id: 3,
    idpId: 11,
    name: 'Authelia',
    slug: 'authelia',
    providerType: 'oidc',
    subject: 'sub-1',
    linkedAt: '2026-01-01T00:00:00Z',
    lastLogin: null,
  }

  it('sends the administrator step-up for the chosen provider', async () => {
    mocks.providers = [provider]
    const wrapper = mount(UserIdentityProvidersList, {
      props: { userId: 7, resume: null },
      global: { plugins: plugins(), stubs },
    })
    await wrapper.get('button[aria-label]').trigger('click')
    await wrapper.get('#stepup-password').setValue('admin-pw')
    await wrapper.get('form').trigger('submit')

    expect(mocks.unlinkMutate).toHaveBeenCalledWith(
      {
        userId: 7,
        idpId: 11,
        stepUp: { currentPassword: 'admin-pw', mfaCode: null, idpReauth: null },
      },
      expect.any(Object),
    )
  })

  it('explains that the last sign-in method cannot be unlinked', async () => {
    mocks.providers = [provider]
    const wrapper = mount(UserIdentityProvidersList, {
      props: { userId: 7, resume: null },
      global: { plugins: plugins(), stubs },
    })
    await wrapper.get('button[aria-label]').trigger('click')
    await wrapper.get('#stepup-password').setValue('admin-pw')
    await wrapper.get('form').trigger('submit')
    const { onError } = mocks.unlinkMutate.mock.calls[0]![1] as { onError: (e: unknown) => void }

    onError(new HttpError(409, 'Conflict', null, 'urn:endurain:error:last-sign-in-method'))

    expect(mocks.toastError).toHaveBeenCalledWith(
      i18n.global.t('settings.users.identityProviders.unlinkLastError'),
    )
  })

  it('reopens the unlink dialog for the provider the return was started for', async () => {
    mocks.providers = [provider]
    const wrapper = mount(UserIdentityProvidersList, {
      props: { userId: 7, resume: resumeFor('admin_idp_unlink', { userId: 7, idpId: 11 }) },
      global: { plugins: plugins(), stubs },
    })
    await flushPromises()

    expect(wrapper.text()).toContain(
      i18n.global.t('settings.users.identityProviders.unlinkBody', { provider: 'Authelia' }),
    )
  })
})

describe('UserSessionsList revoke', () => {
  function session(id: string): UserSession {
    return {
      id,
      ipAddress: '203.0.113.5',
      deviceType: 'desktop',
      operatingSystem: 'macOS',
      operatingSystemVersion: '15',
      browser: 'Chrome',
      browserVersion: '148',
      createdAt: '2026-06-01T10:00:00Z',
      lastActivityAt: '2026-06-02T11:00:00Z',
      expiresAt: '2026-06-08T10:00:00Z',
    }
  }

  function mountList(resume: IdpStepUpResume | null = null) {
    mocks.sessions = [session('current'), session('other')]
    return mount(UserSessionsList, {
      props: { userId: 7, resume },
      global: { plugins: plugins(), stubs },
    })
  }

  const stepUp = { currentPassword: 'admin-pw', mfaCode: null, idpReauth: null }

  it('sends the administrator step-up when revoking one session', async () => {
    const wrapper = mountList()
    await wrapper.findAll('ul button')[1]!.trigger('click')
    await wrapper.get('#stepup-password').setValue('admin-pw')
    await wrapper.get('form').trigger('submit')

    expect(mocks.revokeMutate).toHaveBeenCalledWith(
      { sessionId: 'other', userId: 7, stepUp },
      expect.any(Object),
    )
  })

  it('sends the administrator step-up when revoking the other sessions', async () => {
    const wrapper = mountList()
    await wrapper.get('.justify-between button').trigger('click')
    // Both revoke dialogs render in the stubbed page; the bulk one is the second.
    await wrapper.findAll('#stepup-password')[1]!.setValue('admin-pw')
    await wrapper.findAll('form')[1]!.trigger('submit')

    expect(mocks.revokeOthersMutate).toHaveBeenCalledWith(
      { userId: 7, stepUp, excludeSessionId: 'current' },
      expect.any(Object),
    )
  })

  it('keeps the dialog open and reports invalid credentials on a refused step-up', async () => {
    const wrapper = mountList()
    await wrapper.findAll('ul button')[1]!.trigger('click')
    await wrapper.get('#stepup-password').setValue('wrong')
    await wrapper.get('form').trigger('submit')
    const { onError } = mocks.revokeMutate.mock.calls[0]![1] as { onError: (e: unknown) => void }

    onError(new HttpError(403, 'Forbidden', null, 'urn:endurain:error:step-up-failed'))

    expect(mocks.toastError).toHaveBeenCalledWith(
      i18n.global.t('settings.security.linked.invalidCredentials'),
    )
    expect(wrapper.find('#stepup-password').exists()).toBe(true)
  })

  it('reopens the revoke dialog for the session the return was started for', async () => {
    const wrapper = mountList(resumeFor('admin_sessions_revoke', { userId: 7, sessionId: 'other' }))
    await flushPromises()

    expect(wrapper.findAllComponents({ name: 'StepUpDialog' })[0]!.props('open')).toBe(true)
    expect(wrapper.findAllComponents({ name: 'StepUpDialog' })[1]!.props('open')).toBe(false)
  })

  it('reopens the revoke-others dialog after the return', async () => {
    const wrapper = mountList(resumeFor('admin_sessions_revoke', { userId: 7, others: true }))
    await flushPromises()

    expect(wrapper.findAllComponents({ name: 'StepUpDialog' })[0]!.props('open')).toBe(false)
    expect(wrapper.findAllComponents({ name: 'StepUpDialog' })[1]!.props('open')).toBe(true)
  })
})

describe('UserDetailView identity-provider return', () => {
  function storeReturn(action: string, pending: Record<string, unknown>): void {
    sessionStorage.setItem(
      'idp_step_up',
      JSON.stringify({ action, verifier: 'v1', idpId: 3, pending, createdAt: Date.now() }),
    )
    history.replaceState(null, '', '/settings/users/7#step_up_ticket=t1')
  }

  function mountView() {
    return mount(UserDetailView, {
      global: {
        plugins: plugins(),
        stubs: {
          ...stubs,
          UserDeleteDialog: {
            props: ['variant', 'resume'],
            template: '<i :data-variant="variant" />',
          },
          UserFormDialog: { props: ['resume'], template: '<i data-test="form" />' },
          UserPasswordDialog: { props: ['resume'], template: '<i data-test="password" />' },
          UserIdentityProvidersList: { props: ['resume'], template: '<i data-test="idps" />' },
          UserSessionsList: true,
        },
      },
    })
  }

  it('hands the consumed return to the dialogs and strips the fragment', () => {
    mocks.user = managedUser({ avatarUrl: null, emailVerified: true })
    storeReturn('admin_user_delete', { userId: 7, variant: 'delete' })
    const wrapper = mountView()

    const dialogs = wrapper.findAllComponents(UserDeleteDialog)
    expect(dialogs).toHaveLength(2)
    for (const dialog of dialogs) {
      expect(dialog.props('resume')).toMatchObject({
        action: 'admin_user_delete',
        reauth: { ticket: 't1', codeVerifier: 'v1' },
        pending: { userId: 7, variant: 'delete' },
      })
    }
    expect(window.location.hash).toBe('')
  })

  it.each([
    ['another administrator', true, false, false],
    ['a user with MFA', false, true, true],
    ['a user without MFA', false, false, false],
  ])('shows the credential actions for %s as expected', (_label, isSelf, mfaEnabled, showsMfa) => {
    mocks.user = managedUser({
      id: isSelf ? 1 : 7,
      avatarUrl: null,
      emailVerified: true,
      mfaEnabled,
    })
    const wrapper = mount(UserDetailView, {
      global: {
        plugins: plugins(),
        stubs: {
          ...stubs,
          UserDeleteDialog: true,
          UserFormDialog: true,
          UserPasswordDialog: true,
          UserCredentialActionDialog: true,
          UserIdentityProvidersList: true,
          UserSessionsList: true,
        },
      },
    })
    const text = wrapper.text()

    expect(text.includes(i18n.global.t('settings.users.mfaReset.button'))).toBe(showsMfa)
    expect(text.includes(i18n.global.t('settings.users.requirePasswordChange.button'))).toBe(
      !isSelf,
    )
  })

  it('reports a return that was not fresh and passes no resume down', async () => {
    mocks.user = managedUser({ avatarUrl: null, emailVerified: true })
    storeReturn('admin_user_delete', { userId: 7, variant: 'delete' })
    history.replaceState(null, '', '/settings/users/7#step_up_error=not_fresh')
    const wrapper = mountView()
    await flushPromises()

    expect(mocks.toastError).toHaveBeenCalledWith(
      i18n.global.t('settings.security.stepUp.notFresh'),
    )
    expect(wrapper.findComponent(UserFormDialog).props('resume')).toBeNull()
  })
})
