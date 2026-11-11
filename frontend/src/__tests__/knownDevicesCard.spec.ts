import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import i18n from '@/i18n'
import KnownDevicesCard from '@/features/security/components/KnownDevicesCard.vue'
import StepUpDialog from '@/features/security/components/StepUpDialog.vue'

const device = (id: number, current: boolean) => ({
  id,
  browser: 'Firefox',
  operatingSystem: 'Linux',
  deviceType: 'PC',
  createdAt: '2026-11-10T10:00:00Z',
  lastSeenAt: '2026-11-11T10:00:00Z',
  current,
})

vi.mock('@/features/security/composables/useSecurity', () => ({
  useKnownDevicesQuery: () => ({
    data: ref([device(1, true), device(2, false)]),
    isPending: ref(false),
    isError: ref(false),
    refetch: vi.fn<() => void>(),
  }),
  useForgetKnownDeviceMutation: () => ({ mutate: vi.fn<() => void>(), isPending: ref(false) }),
}))

/** Opens the forget dialog of the device in the given row and returns the description it shows. */
async function descriptionFor(row: number): Promise<string> {
  const wrapper = mount(KnownDevicesCard, {
    props: { hasLocalPassword: true, mfaEnabled: false, resume: null },
    global: {
      plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]],
      stubs: { StepUpDialog: true },
    },
  })
  await wrapper.findAll('li')[row]!.find('button').trigger('click')
  return wrapper.findComponent(StepUpDialog).props('description')
}

describe('KnownDevicesCard forget dialog', () => {
  it('says that forgetting the device signs it out', async () => {
    expect(await descriptionFor(1)).toBe(
      i18n.global.t('settings.security.devices.forgetDescription'),
    )
  })

  it('warns that forgetting the current device signs this browser out', async () => {
    expect(await descriptionFor(0)).toBe(
      i18n.global.t('settings.security.devices.forgetCurrentDescription'),
    )
  })
})
