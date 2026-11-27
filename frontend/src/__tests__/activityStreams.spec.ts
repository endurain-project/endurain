import { describe, expect, it } from 'vitest'

import type { ActivityStreams } from '@/features/activities/types'
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

/** Builds a samples fixture: unset channels are null and the offsets are one second apart. */
function samples(channels: Partial<ActivityStreams>): ActivityStreams {
  const length = Object.values(channels).find((value) => Array.isArray(value))?.length ?? 0
  return {
    offsetsMs: Array.from({ length }, (_, index) => index * 1000),
    latitude: null,
    longitude: null,
    elevation: null,
    heartRate: null,
    power: null,
    cadence: null,
    speed: null,
    pace: null,
    temperature: null,
    hrZones: null,
    ...channels,
  }
}

describe('buildStreamChart', () => {
  it('builds a heart-rate line chart with formatting, zoom and stats', () => {
    const chart = buildStreamChart(
      samples({ heartRate: [120, 130] }),
      'hr',
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
      samples({ heartRate: [120, 130] }),
      'hr',
      makeActivity({ activityType: 'run', distance: 10000 }),
      'imperial',
      resolve,
    )
    expect(chart?.render.valueFormat?.(120)).toBe('120 <bpm>')
    expect(chart?.render.xUnit).toBe('<mi>')
    const temperature = buildStreamChart(
      samples({ temperature: [20] }),
      'temperature',
      makeActivity({ activityType: 'run', distance: 1000 }),
      'metric',
      resolve,
    )
    expect(temperature?.render.valueFormat?.(21.5)).toBe('21.5 <celsius>')
  })

  it('falls back to time labels when the activity has no distance (e.g. strength)', () => {
    const chart = buildStreamChart(
      { ...samples({ heartRate: [120, 140, 130] }), offsetsMs: [0, 300_000, 600_000] },
      'hr',
      makeActivity({
        activityType: 'strength_training',
        distance: 0,
        totalTimerTime: null,
        totalElapsedTime: 600,
      }),
      'metric',
      unitLabel,
    )
    // Without distance the x-axis shows each sample's offset; labels must be
    // non-empty and aligned to the sample count or the line never draws.
    expect(chart?.render.labels).toEqual(['00:00', '05:00', '10:00'])
    expect(chart?.render.xUnit).toBe('')
    expect(chart?.render.series[0]?.data).toEqual([120, 140, 130])
  })

  it('adds elapsed time to the pace stats only when it differs from the timer time', () => {
    const paceStream = samples({ pace: [0.3] })
    const withStops = buildStreamChart(
      paceStream,
      'pace',
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
      'pace',
      makeActivity({ activityType: 'run', totalTimerTime: 3600, totalElapsedTime: 3600 }),
      'metric',
      unitLabel,
    )
    expect(noStops?.stats.map((stat) => stat.labelKey)).toEqual(['activities.metrics.avgPace'])
  })

  it('adds elapsed time to the speed stats when it differs from the timer time', () => {
    const chart = buildStreamChart(
      samples({ speed: [8] }),
      'velocity',
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

  it('labels the samples by their offsets even when the activity has neither distance nor time', () => {
    const chart = buildStreamChart(
      samples({ heartRate: [120, 130] }),
      'hr',
      makeActivity({
        activityType: 'strength_training',
        distance: 0,
        totalElapsedTime: null,
        totalTimerTime: null,
      }),
      'metric',
      unitLabel,
    )
    expect(chart?.render.labels).toEqual(['00:00', '00:01'])
  })

  it('renders elevation as a line (consistent fill) and converts to feet', () => {
    const metric = buildStreamChart(
      samples({ elevation: [100, 200] }),
      'elevation',
      makeActivity({ activityType: 'run', distance: 1000 }),
      'metric',
      unitLabel,
    )
    expect(metric?.render.kind).toBe('line')
    expect(metric?.render.series[0]?.data).toEqual([100, 200])

    const imperial = buildStreamChart(
      samples({ elevation: [100] }),
      'elevation',
      makeActivity({ activityType: 'run', distance: 1000 }),
      'imperial',
      unitLabel,
    )
    expect(imperial?.render.series[0]?.data[0]).toBeCloseTo(328.084)
  })

  it('plots pace on a normal (non-inverted) axis and drops outlier samples', () => {
    // 0.3 s/m → 300 s/km (kept); 2.0 s/m → 2000 s/km exceeds the 1200 s threshold.
    const chart = buildStreamChart(
      samples({ pace: [0.3, 2.0] }),
      'pace',
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
      samples({ cadence: [170] }),
      'cadence',
      makeActivity({ activityType: 'run' }),
      'metric',
      unitLabel,
    )
    expect(chart?.render.series[0]?.data).toEqual([170])
    expect(chart?.render.valueFormat?.(170)).toBe('170 spm')
  })

  it('returns null for a null, empty or all-missing channel', () => {
    expect(buildStreamChart(samples({}), 'hr', makeActivity(), 'metric', unitLabel)).toBeNull()
    expect(
      buildStreamChart(samples({ heartRate: [] }), 'hr', makeActivity(), 'metric', unitLabel),
    ).toBeNull()
    expect(
      buildStreamChart(
        samples({ heartRate: [null, null] }),
        'hr',
        makeActivity(),
        'metric',
        unitLabel,
      ),
    ).toBeNull()
  })

  it('draws a gap for a sample without a value and keeps the others', () => {
    const chart = buildStreamChart(
      samples({ heartRate: [120, null, 130] }),
      'hr',
      makeActivity({ activityType: 'run', distance: 1000 }),
      'metric',
      unitLabel,
    )
    const data = chart?.render.series[0]?.data ?? []
    expect([data[0], data[2]]).toEqual([120, 130])
    expect(Number.isNaN(data[1])).toBe(true)
  })

  it('builds the time axis from the real sample offsets when there is no distance', () => {
    const chart = buildStreamChart(
      { ...samples({ heartRate: [120, 140, 130] }), offsetsMs: [0, 1000, 3_600_000] },
      'hr',
      makeActivity({
        activityType: 'strength_training',
        distance: 0,
        totalTimerTime: 3600,
        totalElapsedTime: 3600,
      }),
      'metric',
      unitLabel,
    )
    // Evenly spaced fractions of the duration would give 0:00, 30:00 and 1:00:00.
    expect(chart?.render.labels).toEqual(['00:00', '00:01', '1:00:00'])
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
    const data = samples({
      heartRate: [120],
      elevation: [10],
      speed: [5],
      pace: [0.3],
    })
    // Running: velocity is not type-relevant; hr is hidden by the predicate.
    const charts = buildStreamCharts(
      data,
      makeActivity({ activityType: 'run' }),
      'metric',
      unitLabel,
      (metric) => metric !== 'hr',
    )
    expect(charts.map((chart) => chart.metric)).toEqual(['pace', 'elevation'])
  })

  it('shows speed (not pace) for cycling', () => {
    const charts = buildStreamCharts(
      samples({ speed: [8], pace: [0.3] }),
      makeActivity({ activityType: 'ride', averageSpeed: 8 }),
      'metric',
      unitLabel,
      () => true,
    )
    expect(charts.map((chart) => chart.metric)).toEqual(['velocity'])
  })

  it('gives no chart for a null channel', () => {
    const charts = buildStreamCharts(
      samples({ heartRate: [120], power: null }),
      makeActivity({ activityType: 'ride' }),
      'metric',
      unitLabel,
      () => true,
    )
    expect(charts.map((chart) => chart.metric)).toEqual(['hr'])
  })
})

describe('extractTrackPoints', () => {
  it('builds the track from the latitude and longitude channels (longitude becomes lng)', () => {
    expect(
      extractTrackPoints(
        samples({
          latitude: [1, 3],
          longitude: [2, 4],
        }),
      ),
    ).toEqual([
      { lat: 1, lng: 2 },
      { lat: 3, lng: 4 },
    ])
  })

  it('skips samples without a full position', () => {
    expect(
      extractTrackPoints(
        samples({
          latitude: [1, null, 5, 7],
          longitude: [2, 4, null, 8],
        }),
      ),
    ).toEqual([
      { lat: 1, lng: 2 },
      { lat: 7, lng: 8 },
    ])
  })

  it('returns an empty array when there are no coordinates or no streams', () => {
    expect(extractTrackPoints(samples({ heartRate: [100] }))).toEqual([])
    expect(extractTrackPoints(null)).toEqual([])
    expect(extractTrackPoints(undefined)).toEqual([])
  })
})

describe('METRIC_PRIVACY_FIELD', () => {
  it('maps metrics to their privacy flags and leaves temperature ungated', () => {
    expect(METRIC_PRIVACY_FIELD.hr).toBe('hideHr')
    expect(METRIC_PRIVACY_FIELD.velocity).toBe('hideSpeed')
    expect(METRIC_PRIVACY_FIELD.temperature).toBeNull()
  })
})
