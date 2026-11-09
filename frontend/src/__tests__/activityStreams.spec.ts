import { describe, expect, it } from 'vitest'

import type { ActivityStream, ActivityStreamType } from '@/features/activities/types'
import type { UnitKey } from '@/i18n'

import {
  buildStreamChart,
  buildStreamCharts,
  extractTrackPoints,
  isMetricRelevantForType,
  METRIC_PRIVACY_FIELD,
} from '@/features/activities/utils/streams'

import { makeActivity } from './fixtures/activity'

/** Resolves a unit key to itself; every tested key reads the same in English. */
function unitLabel(unit: UnitKey): string {
  return unit
}

/** Builds a stream fixture. */
function stream(
  streamType: ActivityStreamType,
  waypoints: ActivityStream['waypoints'],
): ActivityStream {
  return { id: 1, streamType, waypoints, hrZones: null }
}

describe('buildStreamChart', () => {
  it('builds a heart-rate line chart with formatting, zoom and stats', () => {
    const chart = buildStreamChart(
      stream('heart_rate', [{ hr: 120 }, { hr: 130 }]),
      makeActivity({ activityType: 'run', distance: 10000 }),
      'metric',
      unitLabel,
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

  it('renders every unit through the supplied resolver', () => {
    const resolve = (unit: UnitKey): string => `<${unit}>`
    const chart = buildStreamChart(
      stream('heart_rate', [{ hr: 120 }, { hr: 130 }]),
      makeActivity({ activityType: 'run', distance: 10000 }),
      'imperial',
      resolve,
    )
    expect(chart?.render.valueFormat?.(120)).toBe('120 <bpm>')
    expect(chart?.render.xUnit).toBe('<mi>')
    const temperature = buildStreamChart(
      stream('temperature', [{ temp: 20 }]),
      makeActivity({ activityType: 'run', distance: 1000 }),
      'metric',
      resolve,
    )
    expect(temperature?.render.valueFormat?.(21.5)).toBe('21.5 <celsius>')
  })

  it('falls back to time labels when the activity has no distance (e.g. strength)', () => {
    const chart = buildStreamChart(
      stream('heart_rate', [{ hr: 120 }, { hr: 140 }, { hr: 130 }]),
      makeActivity({
        activityType: 'strength_training',
        distance: 0,
        totalTimerTime: null,
        totalElapsedTime: 600,
      }),
      'metric',
      unitLabel,
    )
    // Without distance the x-axis falls back to the activity duration; labels must be
    // non-empty and aligned to the sample count or the line never draws.
    expect(chart?.render.labels).toEqual(['00:00', '05:00', '10:00'])
    expect(chart?.render.xUnit).toBe('')
    expect(chart?.render.series[0]?.data).toEqual([120, 140, 130])
  })

  it('spans the time axis over the timer time, or elapsed time when the timer time is 0', () => {
    const hr = stream('heart_rate', [{ hr: 120 }, { hr: 140 }, { hr: 130 }])
    const timer = buildStreamChart(
      hr,
      makeActivity({
        activityType: 'strength_training',
        distance: 0,
        totalTimerTime: 600,
        totalElapsedTime: 1200,
      }),
      'metric',
      unitLabel,
    )
    expect(timer?.render.labels).toEqual(['00:00', '05:00', '10:00'])

    const elapsed = buildStreamChart(
      hr,
      makeActivity({
        activityType: 'strength_training',
        distance: 0,
        totalTimerTime: 0,
        totalElapsedTime: 1200,
      }),
      'metric',
      unitLabel,
    )
    expect(elapsed?.render.labels).toEqual(['00:00', '10:00', '20:00'])
  })

  it('adds elapsed time to the pace stats only when it differs from the timer time', () => {
    const paceStream = stream('pace', [{ pace: 0.3 }])
    const withStops = buildStreamChart(
      paceStream,
      makeActivity({ activityType: 'run', totalTimerTime: 3500, totalElapsedTime: 3600 }),
      'metric',
      unitLabel,
    )
    expect(withStops?.stats.map((stat) => stat.labelKey)).toEqual([
      'activities.metrics.avgPace',
      'activities.metrics.elapsedTime',
    ])
    expect(withStops?.stats[1]?.value).toBe('1:00:00')

    const noStops = buildStreamChart(
      paceStream,
      makeActivity({ activityType: 'run', totalTimerTime: 3600, totalElapsedTime: 3600 }),
      'metric',
      unitLabel,
    )
    expect(noStops?.stats.map((stat) => stat.labelKey)).toEqual(['activities.metrics.avgPace'])
  })

  it('adds elapsed time to the speed stats when it differs from the timer time', () => {
    const chart = buildStreamChart(
      stream('speed', [{ vel: 8 }]),
      makeActivity({
        activityType: 'ride',
        averageSpeed: 8,
        totalTimerTime: 3500,
        totalElapsedTime: 3600,
      }),
      'metric',
      unitLabel,
    )
    expect(chart?.stats.map((stat) => stat.labelKey)).toEqual([
      'activities.metrics.avgSpeed',
      'activities.metrics.elapsedTime',
    ])
  })

  it('falls back to sample indices when there is neither distance nor time', () => {
    const chart = buildStreamChart(
      stream('heart_rate', [{ hr: 120 }, { hr: 130 }]),
      makeActivity({
        activityType: 'strength_training',
        distance: 0,
        totalElapsedTime: null,
        totalTimerTime: null,
      }),
      'metric',
      unitLabel,
    )
    expect(chart?.render.labels).toEqual(['1', '2'])
  })

  it('renders elevation as a line (consistent fill) and converts to feet', () => {
    const metric = buildStreamChart(
      stream('elevation', [{ ele: 100 }, { ele: 200 }]),
      makeActivity({ activityType: 'run', distance: 1000 }),
      'metric',
      unitLabel,
    )
    expect(metric?.render.kind).toBe('line')
    expect(metric?.render.series[0]?.data).toEqual([100, 200])

    const imperial = buildStreamChart(
      stream('elevation', [{ ele: 100 }]),
      makeActivity({ activityType: 'run', distance: 1000 }),
      'imperial',
      unitLabel,
    )
    expect(imperial?.render.series[0]?.data[0]).toBeCloseTo(328.084)
  })

  it('plots pace on a normal (non-inverted) axis and drops outlier samples', () => {
    // 0.3 s/m → 300 s/km (kept); 2.0 s/m → 2000 s/km exceeds the 1200 s threshold.
    const chart = buildStreamChart(
      stream('pace', [{ pace: 0.3 }, { pace: 2.0 }]),
      makeActivity({ activityType: 'run', distance: 1000 }),
      'metric',
      unitLabel,
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
      stream('cadence', [{ cad: 170 }]),
      makeActivity({ activityType: 'run' }),
      'metric',
      unitLabel,
    )
    expect(chart?.render.series[0]?.data).toEqual([170])
    expect(chart?.render.valueFormat?.(170)).toBe('170 spm')
  })

  it('returns null for unknown stream types, empty or all-missing samples', () => {
    expect(
      buildStreamChart(
        stream('bogus' as ActivityStreamType, [{ hr: 100 }]),
        makeActivity(),
        'metric',
        unitLabel,
      ),
    ).toBeNull()
    expect(
      buildStreamChart(stream('heart_rate', []), makeActivity(), 'metric', unitLabel),
    ).toBeNull()
    expect(
      buildStreamChart(stream('heart_rate', [{ hr: null }]), makeActivity(), 'metric', unitLabel),
    ).toBeNull()
  })
})

describe('isMetricRelevantForType', () => {
  it('shows pace for running and speed for cycling', () => {
    expect(isMetricRelevantForType('pace', 'run')).toBe(true)
    expect(isMetricRelevantForType('velocity', 'run')).toBe(false)
    expect(isMetricRelevantForType('pace', 'ride')).toBe(false)
    expect(isMetricRelevantForType('velocity', 'ride')).toBe(true)
  })

  it('hides elevation for swimming but allows always-relevant metrics', () => {
    expect(isMetricRelevantForType('elevation', 'lap_swimming')).toBe(false)
    expect(isMetricRelevantForType('elevation', 'run')).toBe(true)
    expect(isMetricRelevantForType('hr', 'run')).toBe(true)
    expect(isMetricRelevantForType('temperature', 'lap_swimming')).toBe(true)
  })
})

describe('buildStreamCharts', () => {
  it('filters by visibility and type relevance, in display order (running)', () => {
    const streams = [
      stream('heart_rate', [{ hr: 120 }]),
      stream('elevation', [{ ele: 10 }]),
      stream('speed', [{ vel: 5 }]),
      stream('pace', [{ pace: 0.3 }]),
    ]
    // Running: velocity is not type-relevant; hr is hidden by the predicate.
    const charts = buildStreamCharts(
      streams,
      makeActivity({ activityType: 'run' }),
      'metric',
      unitLabel,
      (metric) => metric !== 'hr',
    )
    expect(charts.map((chart) => chart.metric)).toEqual(['pace', 'elevation'])
  })

  it('shows speed (not pace) for cycling', () => {
    const streams = [stream('speed', [{ vel: 8 }]), stream('pace', [{ pace: 0.3 }])]
    const charts = buildStreamCharts(
      streams,
      makeActivity({ activityType: 'ride', averageSpeed: 8 }),
      'metric',
      unitLabel,
      () => true,
    )
    expect(charts.map((chart) => chart.metric)).toEqual(['velocity'])
  })
})

describe('extractTrackPoints', () => {
  it('extracts lat/lon coordinates from the GPS stream (lon → GeoPoint lng)', () => {
    const streams = [
      stream('heart_rate', [{ hr: 100 }]),
      stream('map', [
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
    expect(extractTrackPoints([stream('heart_rate', [{ hr: 100 }])])).toEqual([])
  })
})

describe('METRIC_PRIVACY_FIELD', () => {
  it('maps metrics to their privacy flags and leaves temperature ungated', () => {
    expect(METRIC_PRIVACY_FIELD.hr).toBe('hideHr')
    expect(METRIC_PRIVACY_FIELD.velocity).toBe('hideSpeed')
    expect(METRIC_PRIVACY_FIELD.temperature).toBeNull()
  })
})
