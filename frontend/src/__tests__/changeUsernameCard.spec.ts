import { afterEach, describe, expect, it, vi } from 'vitest'
import { computed, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'

import type { IdpStepUpResume } from '@/features/security/composables/useIdpStepUp'

import i18n from '@/i18n'
import { HttpError } from '@/services/http'
import ChangeUsernameCard from '@/features/security/components/ChangeUsernameCard.vue'

const start = vi.fn<(...args: unknown[]) => Promise<void>>()

const toastSuccess = vi.fn<(message: string) => void>()
const toastError = vi.fn<(message: string) => void>()
vi.mock('@/composables/useToasts', () => ({
  useToasts: () => ({ success: toastSuccess, error: toastError }),
}))
vi.mock('@/features/security/composables/useIdpStepUp', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/security/composables/useIdpStepUp')>()),
  useIdpStepUp: () => ({ start }),
  useIdpReauthChallenge: () => () => false,
}))
const change = vi.fn<(...args: unknown[]) => void>()
vi.mock('@/features/security/composables/useSecurity', () => ({
  useChangeUsernameMutation: () => ({ mutate: change, isPending: ref(false) }),
}))
vi.mock('@/features/security/composables/useLinkedAccounts', () => ({
  useLinkedProvidersQuery: () => ({
    data: computed(() => [{ id: 1, idpId: 11, name: 'Keycloak', slug: 'kc', icon: null }]),
    isPending: computed(() => false),
    isError: computed(() => false),
  }),
}))

const mounted: Array<{ unmount: () => void }> = []

function mountCard(
  resume: IdpStepUpResume | null = null,
  props: { hasLocalPassword?: boolean; mfaEnabled?: boolean } = {},
) {
  const wrapper = mount(ChangeUsernameCard, {
    props: { username: 'joao', hasLocalPassword: false, mfaEnabled: false, resume, ...props },
    global: { plugins: [i18n] },
  })
  mounted.push(wrapper)
  return wrapper
}

const resumed: IdpStepUpResume = {
  action: 'username_change',
  reauth: { ticket: 't', codeVerifier: 'v' },
  pending: {},
}

describe('ChangeUsernameCard', () => {
  afterEach(() => {
    start.mockReset()
    toastSuccess.mockReset()
    toastError.mockReset()
    change.mockReset()
    mounted.splice(0).forEach((wrapper) => wrapper.unmount())
  })

  it('signs the other sessions out by default', () => {
    const wrapper = mountCard()
    expect(wrapper.find<HTMLInputElement>('[role="switch"]').element.checked).toBe(true)
  })

  it('carries the sign-out-other-sessions choice through the identity-provider sign-in', async () => {
    const wrapper = mountCard()
    await wrapper.find('[role="switch"]').setValue(true)
    const button = wrapper.findAll('button').find((b) => b.text() === 'Continue with Keycloak')
    await button!.trigger('click')
    expect(start).toHaveBeenCalledWith(11, 'username_change', { revokeOtherSessions: true })
  })

  it('restores the choice when the sign-in returns, but never a new username', async () => {
    const wrapper = mountCard({ ...resumed, pending: { revokeOtherSessions: true } })
    await nextTick()
    expect(wrapper.find<HTMLInputElement>('[role="switch"]').element.checked).toBe(true)
    expect(wrapper.find<HTMLInputElement>('#security-new-username').element.value).toBe('')
  })

  it('does not submit the current username, whatever its case, as a change', async () => {
    const wrapper = mountCard(resumed)
    await nextTick()
    await wrapper.find('#security-new-username').setValue(' Joao ')
    expect(wrapper.text()).toContain('This is already your username.')
    expect(wrapper.find<HTMLButtonElement>('button[type="submit"]').element.disabled).toBe(true)

    await wrapper.find('#security-new-username').setValue('other')
    expect(wrapper.find<HTMLButtonElement>('button[type="submit"]').element.disabled).toBe(false)
  })

  it('refuses characters the server does not accept', async () => {
    const wrapper = mountCard(resumed)
    await nextTick()
    await wrapper.find('#security-new-username').setValue('not valid!')
    expect(wrapper.text()).toContain(i18n.global.t('settings.users.form.usernameInvalid'))
    expect(wrapper.find<HTMLButtonElement>('button[type="submit"]').element.disabled).toBe(true)
  })

  it('asks for the password with a local password, and submits it with the new username', async () => {
    const wrapper = mountCard(null, { hasLocalPassword: true })
    await wrapper.find('#security-new-username').setValue('  other  ')
    expect(wrapper.find<HTMLButtonElement>('button[type="submit"]').element.disabled).toBe(true)

    await wrapper.find('#security-username-password').setValue('secret')
    await wrapper.find('form').trigger('submit')

    expect(change).toHaveBeenCalledWith(
      {
        username: 'other',
        stepUp: { currentPassword: 'secret', mfaCode: null, idpReauth: null },
        revokeOtherSessions: true,
      },
      expect.anything(),
    )
  })

  it('confirms the change and clears the form', async () => {
    change.mockImplementation((_input, options) =>
      (options as { onSuccess: () => void }).onSuccess(),
    )
    const wrapper = mountCard(resumed)
    await nextTick()
    await wrapper.find('#security-new-username').setValue('other')
    await wrapper.find('form').trigger('submit')

    expect(toastSuccess).toHaveBeenCalledWith('Username changed.')
    expect(wrapper.find('#security-new-username').exists()).toBe(false)
  })

  it('says so when the username is already taken (409)', async () => {
    change.mockImplementation((_input, options) =>
      (options as { onError: (error: Error) => void }).onError(new HttpError(409, 'Conflict')),
    )
    const wrapper = mountCard(resumed)
    await nextTick()
    await wrapper.find('#security-new-username').setValue('other')
    await wrapper.find('form').trigger('submit')

    expect(toastError).toHaveBeenCalledWith('That username is already in use.')
  })
})
