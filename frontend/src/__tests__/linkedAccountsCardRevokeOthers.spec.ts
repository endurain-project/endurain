import { afterEach, describe, expect, it, vi } from 'vitest'
import { computed } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import i18n from '@/i18n'
import LinkedAccountsCard from '@/features/security/components/LinkedAccountsCard.vue'

const mocks = vi.hoisted(() => ({
  startLink: vi.fn<(variables: unknown, options?: unknown) => void>(),
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {}, path: '/settings/security' }),
  useRouter: () => ({ replace: vi.fn<() => Promise<void>>() }),
}))
vi.mock('@/composables/useToasts', () => ({
  useToasts: () => ({ success: vi.fn<() => void>(), error: vi.fn<() => void>() }),
}))
vi.mock('@/features/security/composables/useIdpStepUp', () => ({
  useIdpStepUp: () => ({ start: vi.fn<() => Promise<void>>() }),
  useIdpReauthChallenge: () => () => false,
  isStepUpFailed: () => false,
}))
vi.mock('@/features/security/composables/useLinkedAccounts', () => ({
  useLinkedProvidersQuery: () => ({
    data: computed(() => [
      {
        id: 1,
        idpId: 11,
        name: 'Keycloak',
        slug: 'kc',
        icon: null,
        iconUploaded: false,
        subject: 's',
        linkedAt: '2026-01-01T00:00:00Z',
      },
    ]),
    isPending: computed(() => false),
    isError: computed(() => false),
  }),
  useAvailableProvidersQuery: () => ({
    data: computed(() => [{ id: 12, name: 'Authentik', slug: 'ak', icon: null }]),
  }),
  useUnlinkProviderMutation: () => ({
    mutate: vi.fn<() => void>(),
    isPending: computed(() => false),
  }),
  useStartProviderLinkMutation: () => ({
    mutate: mocks.startLink,
    isPending: computed(() => false),
  }),
}))

const passthrough = { template: '<div><slot /></div>' }
const mounted: Array<{ unmount: () => void }> = []

async function openLinkDialog() {
  const wrapper = mount(LinkedAccountsCard, {
    props: { hasLocalPassword: true, mfaEnabled: false, resume: null },
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
  mounted.push(wrapper)
  await wrapper
    .findAll('button')
    .find((button) => button.text() === 'Authentik')!
    .trigger('click')
  await flushPromises()
  const dialog = wrapper.get('div[open="true"]')
  await dialog.get('#stepup-password').setValue('pw')
  return dialog
}

describe('LinkedAccountsCard sign out other devices', () => {
  afterEach(() => {
    mocks.startLink.mockReset()
    mounted.splice(0).forEach((wrapper) => wrapper.unmount())
  })

  it('starts the link signing out the other devices, by default', async () => {
    const dialog = await openLinkDialog()

    expect(dialog.get<HTMLInputElement>('input[role="switch"]').element.checked).toBe(true)
    await dialog.get('form').trigger('submit')

    expect(mocks.startLink.mock.calls[0]![0]).toMatchObject({
      idpId: 12,
      revokeOtherSessions: true,
    })
  })

  it('starts the link keeping the other devices when the switch is off', async () => {
    const dialog = await openLinkDialog()

    await dialog.get('input[role="switch"]').setValue(false)
    await dialog.get('form').trigger('submit')

    expect(mocks.startLink.mock.calls[0]![0]).toMatchObject({
      idpId: 12,
      revokeOtherSessions: false,
    })
  })
})
