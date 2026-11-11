import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import type { SleepListEntry } from '@/features/health/types'

import { apiFetch } from '@/services/http'
import i18n from '@/i18n'
import HealthSleepHypnogram from '@/features/health/components/HealthSleepHypnogram.vue'
import HealthSleepListItem from '@/features/health/components/HealthSleepListItem.vue'
import { authedPinia } from './fixtures/authedPinia'

vi.mock('@/services/http', () => ({ apiFetch: vi.fn<typeof apiFetch>() }))
vi.mock('@/features/auth/composables/useCurrentUser', () => ({
  useCurrentUser: () => ({ data: ref({ units: 'metric' }) }),
}))

/** A list row: the record's metrics and the flag, with no stage rows. */
function makeRow(overrides: Partial<SleepListEntry> = {}): SleepListEntry {
  return {
    id: 5,
    userId: 9,
    version: 1,
    date: '2026-06-25',
    sleepStartTimeLocal: null,
    sleepEndTimeLocal: null,
    totalSleepSeconds: 8 * 3600,
    deepSleepSeconds: null,
    lightSleepSeconds: null,
    remSleepSeconds: null,
    awakeSleepSeconds: null,
    sleepScoreOverall: 82,
    sleepScoreDuration: null,
    sleepScoreQuality: null,
    deepPercentageScore: null,
    lightPercentageScore: null,
    remPercentageScore: null,
    awakeCountScore: null,
    restingHeartRate: null,
    avgHeartRate: null,
    minHeartRate: null,
    maxHeartRate: null,
    avgSkinTempDeviation: null,
    hrvStatus: null,
    avgSpo2: null,
    lowestSpo2: null,
    highestSpo2: null,
    avgRespiration: null,
    lowestRespiration: null,
    highestRespiration: null,
    avgSleepStress: null,
    awakeCount: null,
    source: null,
    hasSleepStages: true,
    ...overrides,
  }
}

const fullDto = {
  id: 5,
  user_id: 9,
  version: 1,
  date: '2026-06-25',
  sleep_stages: [
    {
      stage_type: 'deep',
      start_time_gmt: '2026-06-24T23:00:00',
      end_time_gmt: '2026-06-25T00:30:00',
      duration_seconds: 5400,
    },
  ],
}

function mountRow(entry: SleepListEntry, retry = true) {
  return mount(HealthSleepListItem, {
    props: { entry },
    global: {
      plugins: [
        i18n,
        authedPinia(),
        [
          VueQueryPlugin,
          { queryClient: new QueryClient({ defaultOptions: { queries: { retry } } }) },
        ],
      ],
    },
  })
}

const toggle = (wrapper: ReturnType<typeof mountRow>) =>
  wrapper.get(`button[aria-label="${i18n.global.t('health.sleep.toggleDetails')}"]`)

describe('HealthSleepListItem stage timeline', () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset()
  })

  it('reads no record until the row is expanded', async () => {
    const wrapper = mountRow(makeRow())
    await flushPromises()

    expect(apiFetch).not.toHaveBeenCalled()
    expect(wrapper.findComponent(HealthSleepHypnogram).exists()).toBe(false)
  })

  it('reads the record when expanded and draws the hypnogram from its stages', async () => {
    let resolve: (value: unknown) => void = () => undefined
    vi.mocked(apiFetch).mockReturnValue(new Promise((done) => (resolve = done)))
    const wrapper = mountRow(makeRow())

    await toggle(wrapper).trigger('click')

    expect(apiFetch).toHaveBeenCalledWith('/health/sleep/5', expect.anything())
    expect(wrapper.text()).toContain(i18n.global.t('health.sleep.detail.stagesLoading'))
    expect(wrapper.findComponent(HealthSleepHypnogram).exists()).toBe(false)

    resolve(fullDto)
    await flushPromises()

    const hypnogram = wrapper.findComponent(HealthSleepHypnogram)
    expect(hypnogram.exists()).toBe(true)
    expect(hypnogram.props('stages')).toEqual([
      {
        stageType: 'deep',
        startTimeGmt: '2026-06-24T23:00:00',
        endTimeGmt: '2026-06-25T00:30:00',
        durationSeconds: 5400,
      },
    ])
  })

  it('shows an error when the record cannot be read', async () => {
    vi.mocked(apiFetch).mockRejectedValue(new Error('boom'))
    const wrapper = mountRow(makeRow(), false)

    await toggle(wrapper).trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain(i18n.global.t('health.sleep.detail.stagesError'))
    expect(wrapper.findComponent(HealthSleepHypnogram).exists()).toBe(false)
  })

  it('never reads the record for a night without stages', async () => {
    const wrapper = mountRow(makeRow({ hasSleepStages: false }))

    await toggle(wrapper).trigger('click')
    await flushPromises()

    expect(apiFetch).not.toHaveBeenCalled()
    expect(wrapper.findComponent(HealthSleepHypnogram).exists()).toBe(false)
  })
})
