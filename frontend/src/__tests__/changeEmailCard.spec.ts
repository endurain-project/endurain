import { afterEach, describe, expect, it, vi } from 'vitest'
import { computed, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'

import type { IdpStepUpResume } from '@/features/security/composables/useIdpStepUp'

import i18n from '@/i18n'
import ChangeEmailCard from '@/features/security/components/ChangeEmailCard.vue'

const start = vi.fn<(...args: unknown[]) => Promise<void>>()

const toastSuccess = vi.fn<(message: string) => void>()
vi.mock('@/composables/useToasts', () => ({
  useToasts: () => ({ success: toastSuccess, error: vi.fn<() => void>() }),
}))
vi.mock('@/features/security/composables/useIdpStepUp', () => ({
  useIdpStepUp: () => ({ start }),
  useIdpReauthChallenge: () => () => false,
}))
const resend = vi.fn<(...args: unknown[]) => void>()
const cancel = vi.fn<(...args: unknown[]) => void>()
const change = vi.fn<(...args: unknown[]) => void>()
vi.mock('@/features/security/composables/useSecurity', () => ({
  useChangeEmailMutation: () => ({ mutate: change, isPending: ref(false) }),
  useResendEmailChangeMutation: () => ({ mutate: resend, isPending: ref(false) }),
  useCancelEmailChangeMutation: () => ({ mutate: cancel, isPending: ref(false) }),
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
  pending: { pendingEmail: string | null; pendingEmailExpiresAt: string | null } = {
    pendingEmail: null,
    pendingEmailExpiresAt: null,
  },
) {
  const wrapper = mount(ChangeEmailCard, {
    props: {
      email: 'joao@example.com',
      ...pending,
      hasLocalPassword: false,
      mfaEnabled: false,
      resume,
    },
    global: { plugins: [i18n] },
  })
  mounted.push(wrapper)
  return wrapper
}

describe('ChangeEmailCard', () => {
  afterEach(() => {
    start.mockReset()
    toastSuccess.mockReset()
    change.mockReset()
    resend.mockReset()
    cancel.mockReset()
    mounted.splice(0).forEach((wrapper) => wrapper.unmount())
  })

  it('carries the sign-out-other-sessions choice through the identity-provider sign-in', async () => {
    const wrapper = mountCard()
    await wrapper.find('[role="switch"]').setValue(true)
    const button = wrapper.findAll('button').find((b) => b.text() === 'Continue with Keycloak')
    await button!.trigger('click')
    expect(start).toHaveBeenCalledWith(11, 'email_change', { revokeOtherSessions: true })
  })

  it('restores the choice when the sign-in returns, but never a new address', async () => {
    const wrapper = mountCard({
      action: 'email_change',
      reauth: { ticket: 't', codeVerifier: 'v' },
      pending: { revokeOtherSessions: true },
    })
    await nextTick()
    expect(wrapper.find<HTMLInputElement>('[role="switch"]').element.checked).toBe(true)
    expect(wrapper.find<HTMLInputElement>('#security-new-email').element.value).toBe('')
  })

  it('does not submit the current address as a change', async () => {
    const wrapper = mountCard({
      action: 'email_change',
      reauth: { ticket: 't', codeVerifier: 'v' },
      pending: {},
    })
    await nextTick()
    await wrapper.find('#security-new-email').setValue(' Joao@Example.com ')
    expect(wrapper.text()).toContain('This is already your email address.')
    expect(wrapper.find<HTMLButtonElement>('button[type="submit"]').element.disabled).toBe(true)

    await wrapper.find('#security-new-email').setValue('other@example.com')
    expect(wrapper.find<HTMLButtonElement>('button[type="submit"]').element.disabled).toBe(false)
  })

  it.each([
    [true, 'Confirmation link sent to the new address. Your email changes once you confirm it.'],
    [false, 'Email changed.'],
  ])('tells whether the change is pending (%s) in its success toast', async (pending, message) => {
    change.mockImplementation((_input, options) =>
      (options as { onSuccess: (pending: boolean) => void }).onSuccess(pending),
    )
    const wrapper = mountCard({
      action: 'email_change',
      reauth: { ticket: 't', codeVerifier: 'v' },
      pending: {},
    })
    await nextTick()
    await wrapper.find('#security-new-email').setValue('other@example.com')
    await wrapper.find('form').trigger('submit')

    expect(change).toHaveBeenCalledTimes(1)
    expect(toastSuccess).toHaveBeenCalledWith(message)
  })

  it('shows no pending state without a pending change', () => {
    const wrapper = mountCard()
    expect(wrapper.text()).not.toContain('Pending change')
  })

  it('shows the pending address and expiry, and resends or cancels on request', async () => {
    const wrapper = mountCard(null, {
      pendingEmail: 'new@example.com',
      pendingEmailExpiresAt: '2026-11-01T10:00:00Z',
    })
    expect(wrapper.text()).toContain('Pending change to new@example.com')
    expect(wrapper.text()).toContain('The confirmation link expires')

    const button = (label: string) => wrapper.findAll('button').find((b) => b.text() === label)!
    await button('Resend link').trigger('click')
    expect(resend).toHaveBeenCalledTimes(1)
    await button('Cancel change').trigger('click')
    expect(cancel).toHaveBeenCalledTimes(1)
  })
})
