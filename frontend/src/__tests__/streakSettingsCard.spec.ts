import { beforeEach, describe, expect, it, vi } from 'vitest'

import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import type { StreakSettings } from '@/features/streaks/types'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import StreakSettingsCard from '@/features/streaks/components/StreakSettingsCard.vue'

vi.mock('@/services/http', () => ({
  apiFetch: vi.fn<typeof apiFetch>(),
}))

const stored: StreakSettings = { minActivitiesPerWeek: 1, activityTypes: null, showOnProfile: true }

function mountCard(settings: StreakSettings = stored) {
  return mount(StreakSettingsCard, {
    props: { settings },
    global: { plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]] },
  })
}

/** Submits the form and returns the body of the resulting PUT. */
async function submitAndReadBody(wrapper: ReturnType<typeof mountCard>) {
  vi.mocked(apiFetch).mockResolvedValue({
    user_id: 1,
    min_activities_per_week: 1,
    activity_types: null,
    show_on_profile: false,
  })
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  const [, init] = vi.mocked(apiFetch).mock.calls[0]!
  return JSON.parse(String(init?.body)) as Record<string, unknown>
}

describe('StreakSettingsCard', () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset()
  })

  it('adopts refreshed settings for fields the user has not edited', async () => {
    const wrapper = mountCard()
    await wrapper.get('input[name="minActivitiesPerWeek"]').setValue(3)

    // Another tab turned the profile streak off; the query refreshes the prop.
    await wrapper.setProps({ settings: { ...stored, showOnProfile: false } })

    const body = await submitAndReadBody(wrapper)
    expect(body).toEqual({ min_activities_per_week: 3, activity_types: null, show_on_profile: false })
  })

  it('keeps an edit in progress when the same field is refreshed', async () => {
    const wrapper = mountCard()
    await wrapper.get('input[name="minActivitiesPerWeek"]').setValue(3)

    await wrapper.setProps({ settings: { ...stored, minActivitiesPerWeek: 2 } })

    const body = await submitAndReadBody(wrapper)
    expect(body.min_activities_per_week).toBe(3)
  })
})
