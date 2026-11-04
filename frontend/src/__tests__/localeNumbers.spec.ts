import { afterEach, describe, expect, it } from 'vitest'

import { mount } from '@vue/test-utils'
import { QueryClient, VueQueryPlugin } from '@tanstack/vue-query'

import type { ProfileDetails } from '@/features/profile/types'

import i18n from '@/i18n'
import ProfileInfoCard from '@/features/profile/components/ProfileInfoCard.vue'
import { formatDistance, formatElevation, formatSpeed } from '@/features/activities/utils/format'
import {
  formatBmi,
  formatBodyMass,
  formatSkinTempDeviation,
  formatSteps,
  formatWater,
  formatWeight,
} from '@/features/health/utils/healthFormat'
import {
  formatSummaryCalories,
  formatSummaryDistance,
  formatSummaryElevation,
} from '@/features/summary/utils/summaryFormat'
import { buildChartConfiguration } from '@/providers/chartJsChartProvider'
import { formatFixed, formatNumber } from '@/utils/formatNumber'

const RUN = 1
const label = (unit: string) => unit

/** Runs `fn` with the app language switched to `locale`, restoring English afterwards. */
function inLocale<T>(locale: string, fn: () => T): T {
  i18n.global.locale.value = locale as 'en'
  try {
    return fn()
  } finally {
    i18n.global.locale.value = 'en'
  }
}

afterEach(() => {
  i18n.global.locale.value = 'en'
})

describe('formatNumber', () => {
  it('groups and separates by the app language', () => {
    expect(formatNumber(1234.5, { maximumFractionDigits: 1 })).toBe('1,234.5')
    expect(inLocale('de', () => formatNumber(1234.5, { maximumFractionDigits: 1 }))).toBe('1.234,5')
  })

  it('pads fixed decimals and rounds to whole numbers by default', () => {
    expect(formatFixed(2, 2)).toBe('2.00')
    expect(inLocale('de', () => formatFixed(2, 2))).toBe('2,00')
    expect(inLocale('de', () => formatNumber(1234.6))).toBe('1.235')
  })
})

describe('display formatters follow the app language', () => {
  it('distance', () => {
    expect(formatDistance(12345, RUN, 'metric').value).toBe('12.35')
    expect(inLocale('de', () => formatDistance(12345, RUN, 'metric').value)).toBe('12,35')
    expect(inLocale('de', () => formatDistance(1500000, RUN, 'metric').value)).toBe('1.500,00')
  })

  it('speed and elevation', () => {
    expect(formatSpeed(3, RUN, 'metric').value).toBe('10.80')
    expect(inLocale('de', () => formatSpeed(3, RUN, 'metric').value)).toBe('10,80')
    expect(inLocale('de', () => formatElevation(1234.4, 'metric').value)).toBe('1.234')
  })

  it('steps', () => {
    expect(formatSteps(12345)).toBe('12,345')
    expect(inLocale('de', () => formatSteps(12345))).toBe('12.345')
  })

  it('weight, body mass, BMI, water and skin temperature', () => {
    expect(formatWeight(72.5, 'metric', label)).toBe('72.5 kg')
    expect(inLocale('de', () => formatWeight(72.5, 'metric', label))).toBe('72,5 kg')
    expect(inLocale('de', () => formatBodyMass(5.2, 'metric', label))).toBe('5,20 kg')
    expect(inLocale('de', () => formatBmi(22.46))).toBe('22,5')
    expect(inLocale('de', () => formatWater(1500, 'metric', label))).toBe('1.500 ml')
    expect(inLocale('de', () => formatSkinTempDeviation(-1.2, 'metric', label))).toBe(
      '-1,2 celsius',
    )
  })

  it('summary totals', () => {
    expect(formatSummaryDistance(1234500, 'metric').value).toBe('1,234.50')
    expect(inLocale('de', () => formatSummaryDistance(1234500, 'metric').value)).toBe('1.234,50')
    expect(formatSummaryElevation(2500, 'metric').value).toBe('2,500')
    expect(inLocale('de', () => formatSummaryElevation(2500, 'metric').value)).toBe('2.500')
    expect(formatSummaryCalories(12345.6).value).toBe('12,346')
    expect(inLocale('de', () => formatSummaryCalories(12345.6).value)).toBe('12.346')
  })
})

describe('Chart.js', () => {
  it('uses the app language for its own number formatting', () => {
    const options = { kind: 'line' as const, series: [{ label: 'a', data: [1] }] }
    expect(buildChartConfiguration(options).options?.locale).toBe('en')
    expect(inLocale('de', () => buildChartConfiguration(options).options?.locale)).toBe('de')
  })
})

describe('ProfileInfoCard birthdate', () => {
  function birthdate(): string {
    const wrapper = mount(ProfileInfoCard, {
      props: {
        profile: { birthdate: '1990-01-01', units: 'metric', gender: 'female' } as ProfileDetails,
      },
      global: {
        plugins: [i18n, [VueQueryPlugin, { queryClient: new QueryClient() }]],
        stubs: { ProfileFormDialog: true, ConfirmDialog: true },
      },
    })
    const row = wrapper.findAll('dl > div').find((node) => node.find('dt').text() === 'Birth date')
    return row?.find('dd').text() ?? ''
  }

  it('is formatted in the app language without a day shift', () => {
    expect(birthdate()).toBe('Jan 1, 1990')
    expect(inLocale('de', birthdate)).toBe('01.01.1990')
  })
})
