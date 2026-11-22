import { afterEach, describe, expect, it } from 'vitest'
import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'

import i18n from '@/i18n'
import { useUnitFormat } from '@/composables/useUnitFormat'

/** Runs the composable inside a component so `useI18n` has an app to bind to. */
function setup(): ReturnType<typeof useUnitFormat> {
  let api!: ReturnType<typeof useUnitFormat>
  mount(
    defineComponent({
      setup() {
        api = useUnitFormat()
        return () => null
      },
    }),
    { global: { plugins: [i18n] } },
  )
  return api
}

describe('useUnitFormat', () => {
  afterEach(() => {
    i18n.global.locale.value = 'en'
  })

  it('resolves unit symbols from the units namespace', () => {
    const { unitLabel, withUnit, formatMetric } = setup()

    expect(unitLabel('flOz')).toBe('fl oz')
    expect(withUnit('72.0', 'kg')).toBe('72.0 kg')
    expect(withUnit('12', null)).toBe('12')
    expect(formatMetric({ value: '5:30', unit: 'minPerKm' })).toBe('5:30 min/km')
  })

  it('drops a zero hours part unless asked to keep it', () => {
    const { duration } = setup()

    expect(duration(8, 5)).toBe('8h 5m')
    expect(duration(0, 5)).toBe('5m')
    expect(duration(0, 5, true)).toBe('0h 5m')
  })

  it('formats percentages in the active locale', () => {
    const { percent } = setup()

    expect(percent(42)).toBe('42%')
    expect(percent(18.25, 1)).toBe('18.3%')
    i18n.global.locale.value = 'tr'
    expect(percent(42)).toBe('%42')
  })
})
