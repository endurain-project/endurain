import { describe, expect, it, vi } from 'vitest'

import { mount } from '@vue/test-utils'
import { ref } from 'vue'

import type { MapProvider, MapRenderOptions } from '@/composables/useMapProvider'

import i18n from '@/i18n'
import ActivityMap from '@/features/activities/components/ActivityMap.vue'
import { setMapProvider } from '@/composables/useMapProvider'

vi.mock('@/providers', () => ({ useRenderProvidersReady: () => ref(true) }))

const points = [
  { lat: 45, lng: 6 },
  { lat: 45.1, lng: 6.1 },
]

/** Mounts the map against a recording provider and returns the options it received. */
function mountedTrack(props: { showEndpoints?: boolean } = {}): MapRenderOptions['track'] {
  const mountProvider = vi.fn<MapProvider['mount']>(() => ({
    update() {},
    recenter() {},
    destroy() {},
  }))
  setMapProvider({ name: 'test', mount: mountProvider })

  mount(ActivityMap, { props: { points, ...props }, global: { plugins: [i18n] } })

  const options = mountProvider.mock.calls[0]?.[1]
  if (!options) {
    throw new Error('the map was not mounted')
  }
  return options.track
}

describe('ActivityMap endpoints', () => {
  it('marks the track ends as the start and finish by default', () => {
    expect(mountedTrack()).toEqual({ points, start: points[0], finish: points[1] })
  })

  it('draws the track without endpoints when they are hidden', () => {
    expect(mountedTrack({ showEndpoints: false })).toEqual({ points })
  })
})
