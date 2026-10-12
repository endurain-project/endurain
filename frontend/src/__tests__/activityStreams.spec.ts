import { describe, expect, it } from 'vitest'

import type { ActivityStream } from '@/features/activities/types'

import {
  buildStreamChart,
  buildStreamCharts,
  extractTrackPoints,
  isMetricRelevantForType,
  METRIC_PRIVACY_FIELD,
} from '@/features/activities/utils/streams'

import { makeActivity } from './fixtures/activity'

/** Builds a stream fixture. */
function stream(streamType: number, waypoints: ActivityStream['waypoints']): ActivityStream {
  return { id: streamType, streamType, waypoints, hrZones: null }
}

describe('buildStreamChart', () => {
  it('builds a heart-rate line chart with formatting, zoom and stats', () => {
    const chart = buildStreamChart(
      stream(1, [{ hr: 120 }, { hr: 130 }]),
      makeActivity({ activityType: 1, distance: 10000 }),
      'metric',
    )
    expect(chart).not.toBeNull()
    expect(chart?.metric).toBe('hr')
    expect(chart?.titleKey).toBe('activities.streams.heartRate')
    expect(chart?.render.kind).toBe('line')
    expect(chart?.render.invertY).toBeFalsy()
    expect(chart?.render.zoom).toBe(true)
    expect(chart?.render.series[0]?.data).toEqual([120, 130])
    expect(chart?.render.valueFormat?.(120.6)).toBe('121 bpm')
    // Distance labels are evenly spaced across the total distance (10 km).
    expect(chart?.render.labels).toEqual(['0.0', '10.0'])
    expect(chart?.render.xUnit).toBe('km')
    // Aggregate stats are shown beneath the chart.
    expect(chart?.stats).toEqual([
      { labelKey: 'activities.metrics.avgHr', value: '150', unit: 'bpm' },
      { labelKey: 'activities.metrics.maxHr', value: '175', unit: 'bpm' },
    ])
  })

  it('falls back to time labels when the activity has no distance (e.g. strength)', () => {
    const chart = buildStreamChart(
      stream(1, [{ hr: 120 }, { hr: 140 }, { hr: 130 }]),
      makeActivity({ activityType: 19, distance: 0, totalElapsedTime: 600 }),
      'metric',
    )
    // Without distance the x-axis falls back to elapsed time; labels must be
    // non-empty and aligned to the sample count or the line never draws.
    expect(chart?.render.labels).toEqual(['00:00', '05:00', '10:00'])
    expect(chart?.render.xUnit).toBe('')
    expect(chart?.render.series[0]?.data).toEqual([120, 140, 130])
  })

  it('falls back to sample indices when there is neither distance nor time', () => {
    const chart = buildStreamChart(
      stream(1, [{ hr: 120 }, { hr: 130 }]),
      makeActivity({
        activityType: 19,
        distance: 0,
        totalElapsedTime: null,
        totalTimerTime: null,
      }),
      'metric',
    )
    expect(chart?.render.labels).toEqual(['1', '2'])
  })

  it('renders elevation as a line (consistent fill) and converts to feet', () => {
    const metric = buildStreamChart(
      stream(4, [{ ele: 100 }, { ele: 200 }]),
      makeActivity({ activityType: 1, distance: 1000 }),
      'metric',
    )
    expect(metric?.render.kind).toBe('line')
    expect(metric?.render.series[0]?.data).toEqual([100, 200])

    const imperial = buildStreamChart(
      stream(4, [{ ele: 100 }]),
      makeActivity({ activityType: 1, distance: 1000 }),
      'imperial',
    )
    expect(imperial?.render.series[0]?.data[0]).toBeCloseTo(328.084)
  })

  it('plots pace on a normal (non-inverted) axis and drops outlier samples', () => {
    // 0.3 s/m → 300 s/km (kept); 2.0 s/m → 2000 s/km exceeds the 1200 s threshold.
    const chart = buildStreamChart(
      stream(6, [{ pace: 0.3 }, { pace: 2.0 }]),
      makeActivity({ activityType: 1, distance: 1000 }),
      'metric',
    )
    expect(chart?.metric).toBe('pace')
    expect(chart?.render.invertY).toBeFalsy()
    const data = chart?.render.series[0]?.data ?? []
    expect(data[0]).toBeCloseTo(300)
    expect(Number.isNaN(data[1])).toBe(true)
    expect(chart?.render.valueFormat?.(300)).toBe('5:00')
  })

  it('plots stored cadence as-is (backend already normalizes running to SPM)', () => {
    const chart = buildStreamChart(
      stream(3, [{ cad: 170 }]),
      makeActivity({ activityType: 1 }),
      'metric',
    )
    expect(chart?.render.series[0]?.data).toEqual([170])
    expect(chart?.render.valueFormat?.(170)).toBe('170 spm')
  })

  it('returns null for unknown stream types, empty or all-missing samples', () => {
    expect(buildStreamChart(stream(99, [{ hr: 100 }]), makeActivity(), 'metric')).toBeNull()
    expect(buildStreamChart(stream(1, []), makeActivity(), 'metric')).toBeNull()
    expect(buildStreamChart(stream(1, [{ hr: null }]), makeActivity(), 'metric')).toBeNull()
  })
})

describe('isMetricRelevantForType', () => {
  it('shows pace for running and speed for cycling', () => {
    expect(isMetricRelevantForType('pace', 1)).toBe(true)
    expect(isMetricRelevantForType('velocity', 1)).toBe(false)
    expect(isMetricRelevantForType('pace', 4)).toBe(false)
    expect(isMetricRelevantForType('velocity', 4)).toBe(true)
  })

  it('hides elevation for swimming but allows always-relevant metrics', () => {
    expect(isMetricRelevantForType('elevation', 8)).toBe(false)
    expect(isMetricRelevantForType('elevation', 1)).toBe(true)
    expect(isMetricRelevantForType('hr', 1)).toBe(true)
    expect(isMetricRelevantForType('temperature', 8)).toBe(true)
  })
})

describe('buildStreamCharts', () => {
  it('filters by visibility and type relevance, in display order (running)', () => {
    const streams = [
      stream(1, [{ hr: 120 }]),
      stream(4, [{ ele: 10 }]),
      stream(5, [{ vel: 5 }]),
      stream(6, [{ pace: 0.3 }]),
    ]
    // Running: velocity is not type-relevant; hr is hidden by the predicate.
    const charts = buildStreamCharts(
      streams,
      makeActivity({ activityType: 1 }),
      'metric',
      (metric) => metric !== 'hr',
    )
    expect(charts.map((chart) => chart.metric)).toEqual(['pace', 'elevation'])
  })

  it('shows speed (not pace) for cycling', () => {
    const streams = [stream(5, [{ vel: 8 }]), stream(6, [{ pace: 0.3 }])]
    const charts = buildStreamCharts(
      streams,
      makeActivity({ activityType: 4, averageSpeed: 8 }),
      'metric',
      () => true,
    )
    expect(charts.map((chart) => chart.metric)).toEqual(['velocity'])
  })
})

describe('extractTrackPoints', () => {
  it('extracts lat/lon coordinates from the GPS stream (lon → GeoPoint lng)', () => {
    const streams = [
      stream(1, [{ hr: 100 }]),
      stream(7, [
        { lat: 1, lon: 2 },
        { lat: 3, lon: 4 },
      ]),
    ]
    expect(extractTrackPoints(streams)).toEqual([
      { lat: 1, lng: 2 },
      { lat: 3, lng: 4 },
    ])
  })

  it('returns an empty array when no stream carries coordinates', () => {
    expect(extractTrackPoints([stream(1, [{ hr: 100 }])])).toEqual([])
  })
})

describe('METRIC_PRIVACY_FIELD', () => {
  it('maps metrics to their privacy flags and leaves temperature ungated', () => {
    expect(METRIC_PRIVACY_FIELD.hr).toBe('hideHr')
    expect(METRIC_PRIVACY_FIELD.velocity).toBe('hideSpeed')
    expect(METRIC_PRIVACY_FIELD.temperature).toBeNull()
  })
})
