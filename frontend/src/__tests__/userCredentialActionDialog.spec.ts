import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import type { IdpStepUpResume } from '@/features/security/composables/useIdpStepUp'

import i18n from '@/i18n'
import { HttpError } from '@/services/http'
import UserCredentialActionDialog from '@/features/users/components/UserCredentialActionDialog.vue'

const mocks = vi.hoisted(() => ({
  mfaMutate: vi.fn<(...args: unknown[]) => void>(),
  passwordMutate: vi.fn<(...args: unknown[]) => void>(),
  toastError: vi.fn<(message: string) => void>(),
  toastSuccess: vi.fn<(message: string) => void>(),
}))

vi.mock('@/composables/useToasts', () => ({
  useToasts: () => ({ success: mocks.toastSuccess, error: mocks.toastError }),
}))
vi.mock('@/features/security/composables/useAdminStepUp', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/security/composables/useAdminStepUp')>()),
  useAdminStepUp: () => ({ requirePassword: ref(true), requireMfa: ref(false) }),
}))
vi.mock('@/features/users/composables/useUsers', () => ({
  useResetUserMfaMutation: () => ({ mutate: mocks.mfaMutate, isPending: ref(false) }),
  useRequireUserPasswordChangeMutation: () => ({
    mutate: mocks.passwordMutate,
    isPending: ref(false),
  }),
}))

const passthrough = { template: '<div><slot /></div>' }
const stepUp = { currentPassword: 'admin-pw', mfaCode: null, idpReauth: null }

function mountDialog(props: Record<string, unknown>) {
  return mount(UserCredentialActionDialog, {
    props: {
      open: false,
      userId: '00000000-0000-4000-8000-000000000007',
      username: 'bob',
      variant: 'mfa-reset',
      resume: null,
      ...props,
    },
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
}

async function submit(wrapper: ReturnType<typeof mountDialog>): Promise<void> {
  await wrapper.get('#stepup-password').setValue('admin-pw')
  await wrapper.get('form').trigger('submit')
}

beforeEach(() => {
  mocks.mfaMutate.mockReset()
  mocks.passwordMutate.mockReset()
  mocks.toastError.mockReset()
  mocks.toastSuccess.mockReset()
})

describe('UserCredentialActionDialog', () => {
  it('resets the MFA with the administrator step-up', async () => {
    await submit(mountDialog({ open: true, variant: 'mfa-reset' }))

    expect(mocks.mfaMutate).toHaveBeenCalledWith(
      { userId: '00000000-0000-4000-8000-000000000007', stepUp },
      expect.any(Object),
    )
    expect(mocks.passwordMutate).not.toHaveBeenCalled()
  })

  it('requires a password change with the administrator step-up', async () => {
    await submit(mountDialog({ open: true, variant: 'password-change' }))

    expect(mocks.passwordMutate).toHaveBeenCalledWith(
      { userId: '00000000-0000-4000-8000-000000000007', stepUp },
      expect.any(Object),
    )
    expect(mocks.mfaMutate).not.toHaveBeenCalled()
  })

  it.each([
    ['mfa-reset', 'settings.users.mfaReset.description'],
    ['password-change', 'settings.users.requirePasswordChange.description'],
  ])('tells the administrator that the sessions end (%s)', (variant, key) => {
    const wrapper = mountDialog({ open: true, variant })

    expect(wrapper.text()).toContain(i18n.global.t(key, { username: 'bob' }))
    expect(i18n.global.t(key, { username: 'bob' })).toContain('sessions end')
  })

  it('closes and confirms on success', async () => {
    const wrapper = mountDialog({ open: true })
    await submit(wrapper)
    const { onSuccess } = mocks.mfaMutate.mock.calls[0]![1] as { onSuccess: () => void }

    onSuccess()

    expect(mocks.toastSuccess).toHaveBeenCalledWith(
      i18n.global.t('settings.users.mfaReset.success'),
    )
    expect(wrapper.emitted('update:open')?.[0]).toEqual([false])
  })

  it('reports a refused step-up and stays open', async () => {
    const wrapper = mountDialog({ open: true })
    await submit(wrapper)
    const { onError } = mocks.mfaMutate.mock.calls[0]![1] as { onError: (e: unknown) => void }

    onError(new HttpError(403, 'Forbidden', null, 'urn:endurain:error:step-up-failed'))

    expect(mocks.toastError).toHaveBeenCalledWith(
      i18n.global.t('settings.security.linked.invalidCredentials'),
    )
    expect(wrapper.emitted('update:open')).toBeUndefined()
  })

  it('says the user has no password when the backend answers 409', async () => {
    const wrapper = mountDialog({ open: true, variant: 'password-change' })
    await submit(wrapper)
    const { onError } = mocks.passwordMutate.mock.calls[0]![1] as { onError: (e: unknown) => void }

    onError(new HttpError(409, 'Conflict', null, 'urn:endurain:error:conflict'))

    expect(mocks.toastError).toHaveBeenCalledWith(
      i18n.global.t('settings.users.requirePasswordChange.refused'),
    )
  })

  it('says MFA is not on when the MFA reset answers 409', async () => {
    const wrapper = mountDialog({ open: true, variant: 'mfa-reset' })
    await submit(wrapper)
    const { onError } = mocks.mfaMutate.mock.calls[0]![1] as { onError: (e: unknown) => void }

    onError(new HttpError(409, 'Conflict', null, 'urn:endurain:error:conflict'))

    expect(mocks.toastError).toHaveBeenCalledWith(i18n.global.t('settings.users.mfaReset.refused'))
  })

  it('shows the generic error for a 400, which neither route raises', async () => {
    const wrapper = mountDialog({ open: true, variant: 'mfa-reset' })
    await submit(wrapper)
    const { onError } = mocks.mfaMutate.mock.calls[0]![1] as { onError: (e: unknown) => void }

    onError(new HttpError(400, 'Bad Request', null, 'urn:endurain:error:invalid-input'))

    expect(mocks.toastError).toHaveBeenCalledWith(i18n.global.t('settings.users.mfaReset.error'))
  })

  it('reopens after the identity-provider return that was started for its action and user', async () => {
    const resume = {
      action: 'admin_mfa_reset',
      reauth: { ticket: 't1', codeVerifier: 'v1' },
      pending: { userId: '00000000-0000-4000-8000-000000000007' },
    } as IdpStepUpResume
    const wrapper = mountDialog({ resume })
    await flushPromises()

    expect(wrapper.emitted('update:open')?.[0]).toEqual([true])
  })

  it.each([
    [
      'the other action',
      'admin_credential_change_require',
      { userId: '00000000-0000-4000-8000-000000000007' },
    ],
    ['another user', 'admin_mfa_reset', { userId: '00000000-0000-4000-8000-000000000008' }],
  ])('ignores a return that was started for %s', async (_label, action, pending) => {
    const resume = {
      action,
      reauth: { ticket: 't1', codeVerifier: 'v1' },
      pending,
    } as IdpStepUpResume
    const wrapper = mountDialog({ resume })
    await flushPromises()

    expect(wrapper.emitted('update:open')).toBeUndefined()
  })
})
