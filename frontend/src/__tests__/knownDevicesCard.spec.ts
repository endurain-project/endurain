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
  forgetAllMutate: vi.fn<(...args: unknown[]) => void>(),
}))

const device = (id: string, current: boolean) => ({
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
  useForgetAllKnownDevicesMutation: () => ({
    mutate: mocks.forgetAllMutate,
    isPending: ref(false),
  }),
  useForgetOtherKnownDevicesMutation: () => ({
    mutate: mocks.forgetOthersMutate,
    isPending: ref(false),
  }),
}))

function mountCard() {
  return mount(KnownDevicesCard, {
    props: { hasLocalPassword: true, mfaEnabled: false, resume: null },
    global: {
      plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]],
      stubs: { StepUpDialog: true },
    },
  })
}

describe('KnownDevicesCard forget one device', () => {
  it('disables the forget button of the current device only', () => {
    mocks.devices = [
      device('00000000-0000-4000-8000-000000000001', true),
      device('00000000-0000-4000-8000-000000000002', false),
    ]
    const rows = mountCard().findAll('li')

    expect(rows[0]!.find('button').attributes('disabled')).toBeDefined()
    expect(rows[1]!.find('button').attributes('disabled')).toBeUndefined()
  })

  it('opens the forget dialog for another device', async () => {
    mocks.devices = [
      device('00000000-0000-4000-8000-000000000001', true),
      device('00000000-0000-4000-8000-000000000002', false),
    ]
    const wrapper = mountCard()
    await wrapper.findAll('li')[1]!.find('button').trigger('click')
    const dialog = wrapper
      .findAllComponents(StepUpDialog)
      .find((d) => d.props('action') === 'profile_device_forget')!

    expect(dialog.props('open')).toBe(true)
    expect(dialog.props('description')).toBe(
      i18n.global.t('settings.security.devices.forgetDescription'),
    )
  })
})

describe('KnownDevicesCard forget other devices', () => {
  const forgetOthers = i18n.global.t('settings.security.devices.forgetOthers')

  it('hides the button when no other device is known', () => {
    mocks.devices = [device('00000000-0000-4000-8000-000000000001', true)]

    expect(mountCard().text()).not.toContain(forgetOthers)
  })

  it('opens the confirmation and forgets the other devices with the step-up', async () => {
    mocks.devices = [
      device('00000000-0000-4000-8000-000000000001', true),
      device('00000000-0000-4000-8000-000000000002', false),
    ]
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

describe('KnownDevicesCard forget all devices', () => {
  const forgetAll = i18n.global.t('settings.security.devices.forgetAll')

  it('shows the button even when the current device is the only one', () => {
    mocks.devices = [device('00000000-0000-4000-8000-000000000001', true)]

    expect(mountCard().text()).toContain(forgetAll)
  })

  it('opens the confirmation and forgets every device with the step-up', async () => {
    mocks.devices = [device('00000000-0000-4000-8000-000000000001', true)]
    const wrapper = mountCard()
    const button = wrapper.findAll('button').find((b) => b.text() === forgetAll)!
    await button.trigger('click')
    const dialog = wrapper
      .findAllComponents(StepUpDialog)
      .find((d) => d.props('action') === 'profile_devices_forget_all')!

    expect(dialog.props('open')).toBe(true)

    const input = { currentPassword: 'pw', mfaCode: null }
    dialog.vm.$emit('confirm', input)

    expect(mocks.forgetAllMutate).toHaveBeenCalledWith(input, expect.any(Object))
  })
})
