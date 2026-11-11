import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import i18n from '@/i18n'
import KnownDevicesCard from '@/features/security/components/KnownDevicesCard.vue'
import StepUpDialog from '@/features/security/components/StepUpDialog.vue'

const mocks = vi.hoisted(() => ({
  devices: [] as unknown[],
  forgetOthersMutate: vi.fn<(...args: unknown[]) => void>(),
}))

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
    data: ref(mocks.devices),
    isPending: ref(false),
    isError: ref(false),
    refetch: vi.fn<() => void>(),
  }),
  useForgetKnownDeviceMutation: () => ({ mutate: vi.fn<() => void>(), isPending: ref(false) }),
  useForgetOtherKnownDevicesMutation: () => ({
    mutate: mocks.forgetOthersMutate,
    isPending: ref(false),
  }),
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

mocks.devices = [device(1, true), device(2, false)]

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

describe('KnownDevicesCard forget other devices', () => {
  function mountCard() {
    return mount(KnownDevicesCard, {
      props: { hasLocalPassword: true, mfaEnabled: false, resume: null },
      global: {
        plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]],
        stubs: { StepUpDialog: true },
      },
    })
  }

  const forgetOthers = i18n.global.t('settings.security.devices.forgetOthers')

  it('hides the button when no other device is known', () => {
    mocks.devices = [device(1, true)]

    expect(mountCard().text()).not.toContain(forgetOthers)
  })

  it('opens the confirmation and forgets the other devices with the step-up', async () => {
    mocks.devices = [device(1, true), device(2, false)]
    const wrapper = mountCard()
    const button = wrapper.findAll('button').find((b) => b.text() === forgetOthers)!
    await button.trigger('click')
    const dialog = wrapper
      .findAllComponents(StepUpDialog)
      .find((d) => d.props('action') === 'profile_devices_forget_others')!

    expect(dialog.props('open')).toBe(true)

    const input = { currentPassword: 'pw', mfaCode: null }
    dialog.vm.$emit('confirm', input)

    expect(mocks.forgetOthersMutate).toHaveBeenCalledWith(input, expect.any(Object))
  })
})
