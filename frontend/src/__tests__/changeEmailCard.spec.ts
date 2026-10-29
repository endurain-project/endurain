import { afterEach, describe, expect, it, vi } from 'vitest'
import { computed, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'

import type { IdpStepUpResume } from '@/features/security/composables/useIdpStepUp'

import i18n from '@/i18n'
import ChangeEmailCard from '@/features/security/components/ChangeEmailCard.vue'

const start = vi.fn<(...args: unknown[]) => Promise<void>>()

vi.mock('@/composables/useToasts', () => ({
  useToasts: () => ({ success: vi.fn<() => void>(), error: vi.fn<() => void>() }),
}))
vi.mock('@/features/security/composables/useIdpStepUp', () => ({
  useIdpStepUp: () => ({ start }),
  useIdpReauthChallenge: () => () => false,
}))
vi.mock('@/features/security/composables/useSecurity', () => ({
  useChangeEmailMutation: () => ({ mutate: vi.fn<() => void>(), isPending: ref(false) }),
}))
vi.mock('@/features/security/composables/useLinkedAccounts', () => ({
  useLinkedProvidersQuery: () => ({
    data: computed(() => [{ id: 1, idpId: 11, name: 'Keycloak', slug: 'kc', icon: null }]),
    isPending: computed(() => false),
    isError: computed(() => false),
  }),
}))

const mounted: Array<{ unmount: () => void }> = []

function mountCard(resume: IdpStepUpResume | null = null) {
  const wrapper = mount(ChangeEmailCard, {
    props: { email: 'joao@example.com', hasLocalPassword: false, mfaEnabled: false, resume },
    global: { plugins: [i18n] },
  })
  mounted.push(wrapper)
  return wrapper
}

describe('ChangeEmailCard', () => {
  afterEach(() => {
    start.mockReset()
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
})
