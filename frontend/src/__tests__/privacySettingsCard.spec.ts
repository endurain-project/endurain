import { afterEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'

import type { PrivacySettings } from '@/features/profile/types'

import i18n from '@/i18n'
import PrivacySettingsCard from '@/features/profile/components/PrivacySettingsCard.vue'

const mutateAsync = vi.hoisted(() => vi.fn<(privacy: PrivacySettings) => Promise<void>>())

vi.mock('@/composables/useToasts', () => ({
  useToasts: () => ({
    success: vi.fn<(message: string) => void>(),
    error: vi.fn<(message: string) => void>(),
  }),
}))
vi.mock('@/features/profile/composables/useProfile', () => ({
  useUpdatePrivacyMutation: () => ({ mutateAsync, isPending: ref(false) }),
  useUpdateExistingActivitiesVisibilityMutation: () => ({
    mutateAsync: vi.fn<() => Promise<void>>(),
    isPending: ref(false),
  }),
}))

const privacy: PrivacySettings = {
  version: 1,
  defaultActivityVisibility: 'private',
  hideStartTime: false,
  hideLocation: false,
  hideMap: false,
  hideHr: false,
  hidePower: false,
  hideCadence: false,
  hideElevation: false,
  hideSpeed: false,
  hidePace: false,
  hideLaps: false,
  hideWorkoutSetsSteps: false,
  hideGear: false,
  discoverable: true,
}

afterEach(() => {
  vi.clearAllMocks()
})

describe('PrivacySettingsCard', () => {
  it('offers the search opt-out and saves the choice', async () => {
    mutateAsync.mockResolvedValue(undefined)
    const wrapper = mount(PrivacySettingsCard, {
      props: { privacy },
      global: { plugins: [i18n], stubs: { ConfirmDialog: true } },
    })

    const toggle = wrapper
      .findAll<HTMLInputElement>('input[type="checkbox"]')
      .find((input) => input.element.closest('label')?.textContent?.includes('find me in search'))
    if (!toggle) {
      throw new Error('The discoverable switch is missing')
    }
    expect(toggle.element.checked).toBe(true)

    await toggle.setValue(false)
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(mutateAsync).toHaveBeenCalledWith(expect.objectContaining({ discoverable: false }))
    wrapper.unmount()
  })
})
