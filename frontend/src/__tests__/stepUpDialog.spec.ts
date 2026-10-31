import { afterEach, describe, expect, it, vi } from 'vitest'
import { computed } from 'vue'
import { mount } from '@vue/test-utils'

import i18n from '@/i18n'
import StepUpDialog from '@/features/security/components/StepUpDialog.vue'

const start = vi.fn<(...args: unknown[]) => Promise<void>>()

vi.mock('@/composables/useToasts', () => ({
  useToasts: () => ({ success: vi.fn<() => void>(), error: vi.fn<() => void>() }),
}))
vi.mock('@/features/security/composables/useIdpStepUp', () => ({
  useIdpStepUp: () => ({ start }),
}))
vi.mock('@/features/security/composables/useLinkedAccounts', () => ({
  useLinkedProvidersQuery: () => ({
    data: computed(() => [
      { id: 1, idpId: 11, name: 'Keycloak', slug: 'kc', icon: null },
      { id: 2, idpId: 12, name: 'Authentik', slug: 'ak', icon: null },
    ]),
    isPending: computed(() => false),
    isError: computed(() => false),
  }),
}))

const passthrough = { template: '<div><slot /></div>' }
const mounted: Array<{ unmount: () => void }> = []

function mountDialog(props: Record<string, unknown>) {
  const wrapper = mount(StepUpDialog, {
    props: {
      open: true,
      title: 'Title',
      description: 'Desc',
      confirmLabel: 'Confirm',
      pending: false,
      action: 'mfa_disable',
      requirePassword: true,
      ...props,
    },
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
  mounted.push(wrapper)
  return wrapper
}

describe('StepUpDialog', () => {
  afterEach(() => {
    start.mockReset()
    mounted.splice(0).forEach((wrapper) => wrapper.unmount())
  })

  it('keeps the password mode unchanged', async () => {
    const wrapper = mountDialog({ requirePassword: true, requireMfa: false })
    expect(wrapper.find('#stepup-password').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('Keycloak')
    await wrapper.find('#stepup-password').setValue('pw')
    await wrapper.find('form').trigger('submit')
    expect(wrapper.emitted('confirm')?.[0]).toEqual([
      { currentPassword: 'pw', mfaCode: null, idpReauth: null },
    ])
  })

  it('offers one button per linked provider before a ticket exists and starts the flow', async () => {
    const wrapper = mountDialog({
      requirePassword: false,
      requireMfa: true,
      pendingContext: { type: 'x' },
    })
    expect(wrapper.find('#stepup-password').exists()).toBe(false)
    expect(wrapper.find('#stepup-mfa').exists()).toBe(false)
    const buttons = wrapper.findAll('button[type="button"]')
    const labels = buttons.map((button) => button.text())
    expect(labels).toContain('Continue with Keycloak')
    expect(labels).toContain('Continue with Authentik')
    await buttons[labels.indexOf('Continue with Authentik')]!.trigger('click')
    expect(start).toHaveBeenCalledWith(12, 'mfa_disable', { type: 'x' })
  })

  it('shows the confirmed state and MFA field once a ticket exists, and emits the proof', async () => {
    const wrapper = mountDialog({
      requirePassword: false,
      requireMfa: true,
      reauth: { ticket: 't', codeVerifier: 'v' },
    })
    expect(wrapper.text()).not.toContain('Continue with Keycloak')
    await wrapper.find('#stepup-mfa').setValue(' 123456 ')
    await wrapper.find('form').trigger('submit')
    expect(wrapper.emitted('confirm')?.[0]).toEqual([
      {
        currentPassword: null,
        mfaCode: '123456',
        idpReauth: { ticket: 't', codeVerifier: 'v' },
      },
    ])
  })

  it('does not submit without a ticket', async () => {
    const wrapper = mountDialog({ requirePassword: false, requireMfa: false })
    await wrapper.find('form').trigger('submit')
    const submit = wrapper.find('button[type="submit"]')
    expect(submit.attributes('disabled')).toBeDefined()
  })

  it('returns to the provider buttons when the user signs in again', async () => {
    const wrapper = mountDialog({
      requirePassword: false,
      requireMfa: false,
      reauth: { ticket: 't', codeVerifier: 'v' },
    })
    const restart = wrapper.findAll('button').find((b) => b.text() === 'Sign in again')
    await restart!.trigger('click')
    expect(wrapper.emitted('update:reauth')?.[0]).toEqual([null])
  })

  it('carries the typed confirmation phrase through the identity-provider sign-in', async () => {
    const wrapper = mountDialog({
      requirePassword: false,
      requireMfa: false,
      confirmPhrase: 'joao',
      pendingContext: { type: 'x' },
    })
    await wrapper.find('#stepup-confirm-phrase').setValue('joao')
    const buttons = wrapper.findAll('button[type="button"]')
    await buttons.find((button) => button.text() === 'Continue with Keycloak')!.trigger('click')
    expect(start).toHaveBeenCalledWith(11, 'mfa_disable', { type: 'x', typedPhrase: 'joao' })
  })

  it('refills the confirmation phrase on the reopen that resumes the sign-in, and only then', async () => {
    const wrapper = mountDialog({
      requirePassword: false,
      requireMfa: false,
      confirmPhrase: 'joao',
      reauth: { ticket: 't', codeVerifier: 'v' },
      restoredContext: { typedPhrase: 'joao' },
    })
    const phrase = wrapper.find<HTMLInputElement>('#stepup-confirm-phrase')
    expect(phrase.element.value).toBe('joao')
    expect(wrapper.find('button[type="submit"]').attributes('disabled')).toBeUndefined()

    await wrapper.setProps({ open: false })
    await wrapper.setProps({ open: true })
    expect(wrapper.find<HTMLInputElement>('#stepup-confirm-phrase').element.value).toBe('')
  })
})
