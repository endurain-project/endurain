import { describe, expect, it } from 'vitest'

import {
  setChartProvider,
  useChartProvider,
  type ChartProvider,
} from '@/composables/useChartProvider'
import { setMapProvider, useMapProvider, type MapProvider } from '@/composables/useMapProvider'

describe('useChartProvider', () => {
  it('defaults to the no-op provider and reports unavailable', () => {
    const { provider, isAvailable } = useChartProvider()
    expect(provider.name).toBe('noop')
    expect(isAvailable).toBe(false)
    // The no-op mount returns an inert handle that never throws.
    const instance = provider.mount(document.createElement('div'), { kind: 'line', series: [] })
    expect(() => {
      instance.update({ kind: 'bar', series: [] })
      instance.destroy()
    }).not.toThrow()
  })

  it('registers a concrete provider and reports available', () => {
    const fake: ChartProvider = {
      name: 'fake-chart',
      mount: () => ({
        update: () => {},
        fractionAt: () => null,
        cursorGeometry: () => null,
        destroy: () => {},
      }),
    }
    setChartProvider(fake)
    const { provider, isAvailable } = useChartProvider()
    expect(provider.name).toBe('fake-chart')
    expect(isAvailable).toBe(true)
  })
})

describe('useMapProvider', () => {
  it('defaults to the no-op provider and reports unavailable', () => {
    const { provider, isAvailable } = useMapProvider()
    expect(provider.name).toBe('noop')
    expect(isAvailable).toBe(false)
    const instance = provider.mount(document.createElement('div'), { track: { points: [] } })
    expect(() => {
      instance.update({ track: { points: [] } })
      instance.recenter()
      instance.setCursor(null)
      instance.setTrackHover(null)
      instance.destroy()
    }).not.toThrow()
  })

  it('registers a concrete provider and reports available', () => {
    const fake: MapProvider = {
      name: 'fake-map',
      mount: () => ({
        update: () => {},
        recenter: () => {},
        setCursor: () => {},
        setTrackHover: () => {},
        destroy: () => {},
      }),
    }
    setMapProvider(fake)
    const { provider, isAvailable } = useMapProvider()
    expect(provider.name).toBe('fake-map')
    expect(isAvailable).toBe(true)
  })
})
