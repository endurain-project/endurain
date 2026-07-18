import type { ChartRenderOptions } from '@/composables/useChartProvider'
import type { GeoPoint } from '@/composables/useMapProvider'

import { themeColor } from '@/lib/themeColor'

import type {
  Activity,
  ActivityPrivacy,
  ActivityStream,
  StreamMetric,
  StreamWaypoint,
} from '../types'
import { STREAM_TYPE } from '../types'
import {
  activityTypeIsRowing,
  activityTypeIsStandUpPaddling,
  activityTypeIsSwimming,
  activityTypeUsesPace,
} from './activityType'
import {
  cadenceUnitLabel,
  celsiusToFahrenheit,
  elevationToDisplay,
  formatElevation,
  formatHmsDuration,
  formatPace,
  formatPaceClock,
  formatSpeed,
  paceToDisplaySeconds,
  presentCadence,
  speedToDisplay,
  speedUnitLabel,
  type Units,
} from './format'

/** Maps a numeric stream type to its metric kind. */
const METRIC_BY_TYPE: Record<number, StreamMetric> = {
  [STREAM_TYPE.hr]: 'hr',
  [STREAM_TYPE.power]: 'power',
  [STREAM_TYPE.cadence]: 'cadence',
  [STREAM_TYPE.elevation]: 'elevation',
  [STREAM_TYPE.velocity]: 'velocity',
  [STREAM_TYPE.pace]: 'pace',
  [STREAM_TYPE.temperature]: 'temperature',
}

/** Stable display order for the metric charts. */
export const STREAM_METRIC_ORDER: readonly StreamMetric[] = [
  'pace',
  'velocity',
  'cadence',
  'hr',
  'power',
  'elevation',
  'temperature',
]

/** i18n label key for each metric chart title. */
const METRIC_TITLE_KEY: Record<StreamMetric, string> = {
  hr: 'activities.streams.heartRate',
  power: 'activities.streams.power',
  cadence: 'activities.streams.cadence',
  elevation: 'activities.streams.elevation',
  velocity: 'activities.streams.speed',
  pace: 'activities.streams.pace',
  temperature: 'activities.streams.temperature',
}

/**
 * Series colour for each metric. Five map directly to the design-system
 * semantic tokens; cadence and temperature have no semantic token, so they use
 * the conventional fitness-chart colours (violet / orange) that read distinctly
 * against the others.
 */
const METRIC_COLOR: Record<StreamMetric, string> = {
  hr: themeColor('--color-hr'),
  power: themeColor('--color-effort'),
  cadence: '#a855f7', // no token — conventional cadence violet
  elevation: themeColor('--color-goal'),
  velocity: themeColor('--color-info'),
  pace: themeColor('--color-brand'),
  temperature: '#f97316', // no token — conventional temperature orange
}

/**
 * Maps a metric to the privacy flag that hides it from non-owners, or `null`
 * when the metric has no privacy flag (temperature).
 */
export const METRIC_PRIVACY_FIELD: Record<StreamMetric, keyof ActivityPrivacy | null> = {
  hr: 'hideHr',
  power: 'hidePower',
  cadence: 'hideCadence',
  elevation: 'hideElevation',
  velocity: 'hideSpeed',
  pace: 'hidePace',
  temperature: null,
}

/**
 * Whether a metric is relevant to show for an activity type, mirroring v1's
 * pace-vs-speed split: pace for foot/water sports, speed for cycling and other
 * speed sports, and no elevation for swimming. HR, power, cadence and
 * temperature are always relevant when present.
 *
 * @param metric - The stream metric.
 * @param activityType - Numeric activity type.
 * @returns Whether the metric should be shown for this activity type.
 */
export function isMetricRelevantForType(metric: StreamMetric, activityType: number): boolean {
  switch (metric) {
    case 'pace':
      return activityTypeUsesPace(activityType)
    case 'velocity':
      return !activityTypeUsesPace(activityType)
    case 'elevation':
      return !activityTypeIsSwimming(activityType)
    default:
      return true
  }
}

/**
 * Pace outlier threshold (in seconds for the display unit). Values slower than
 * this are dropped as GPS noise, mirroring v1.
 *
 * @param activityType - Numeric activity type.
 * @param units - The user's unit system.
 * @returns The threshold in seconds, beyond which a pace sample is discarded.
 */
function paceThresholdSeconds(activityType: number, units: Units): number {
  if (activityTypeIsSwimming(activityType)) {
    // 10 min per 100m (metric) / per 100yd (imperial, ×1.0936).
    return units === 'imperial' ? 10 * 1.0936 * 60 : 10 * 60
  }
  if (activityTypeIsRowing(activityType) || activityTypeIsStandUpPaddling(activityType)) {
    return 10 * 60 // 10 min per 500m.
  }
  // 20 min per km (metric) / per mile (imperial, ×1.60934).
  return units === 'imperial' ? 20 * 1.60934 * 60 : 20 * 60
}

/** Reads a numeric waypoint field, returning `NaN` for missing values. */
function num(value: number | null | undefined): number {
  return value === null || value === undefined || !Number.isFinite(value) ? Number.NaN : value
}

/**
 * Extracts the converted chart value for a single waypoint and metric. Returns
 * `NaN` for missing or filtered samples so the chart renders a gap.
 */
function extractValue(
  waypoint: StreamWaypoint,
  metric: StreamMetric,
  activityType: number,
  units: Units,
): number {
  switch (metric) {
    case 'hr':
      return num(waypoint.hr)
    case 'power':
      return num(waypoint.power)
    case 'cadence': {
      const cad = num(waypoint.cad)
      return Number.isNaN(cad) ? Number.NaN : presentCadence(cad, activityType)
    }
    case 'elevation': {
      const ele = num(waypoint.ele)
      return Number.isNaN(ele) ? Number.NaN : elevationToDisplay(ele, units)
    }
    case 'velocity': {
      const vel = num(waypoint.vel)
      return Number.isNaN(vel) ? Number.NaN : speedToDisplay(vel, activityType, units)
    }
    case 'pace': {
      const pace = num(waypoint.pace)
      if (Number.isNaN(pace) || pace <= 0) {
        return Number.NaN
      }
      const seconds = paceToDisplaySeconds(pace, activityType, units)
      return seconds > paceThresholdSeconds(activityType, units) ? Number.NaN : seconds
    }
    case 'temperature': {
      const temp = num(waypoint.temp)
      return Number.isNaN(temp)
        ? Number.NaN
        : units === 'imperial'
          ? celsiusToFahrenheit(temp)
          : temp
    }
    default:
      return Number.NaN
  }
}

/** Builds the per-metric value formatter used for chart ticks and tooltips. */
function valueFormatter(
  metric: StreamMetric,
  activityType: number,
  units: Units,
): (value: number) => string {
  switch (metric) {
    case 'hr':
      return (v) => `${Math.round(v)} bpm`
    case 'power':
      return (v) => `${Math.round(v)} W`
    case 'cadence':
      return (v) => `${Math.round(v)} ${cadenceUnitLabel(activityType)}`
    case 'elevation':
      return (v) => `${Math.round(v)} ${units === 'imperial' ? 'ft' : 'm'}`
    case 'velocity':
      return (v) => `${v.toFixed(1)} ${speedUnitLabel(activityType, units)}`
    case 'pace':
      return (v) => formatPaceClock(v)
    case 'temperature':
      return (v) => `${v.toFixed(1)}°${units === 'imperial' ? 'F' : 'C'}`
    default:
      return (v) => String(v)
  }
}

/** The x-axis basis a stream chart is plotted against. */
export type XAxisBasis = 'distance' | 'time'

/** Translated words for axis titles (the builder appends the distance unit). */
export interface XAxisText {
  /** Word for the distance axis, e.g. "Distance". */
  distance: string
  /** Word for the time axis, e.g. "Time". */
  time: string
}

/** Fallback axis words for direct/tested calls; the view passes translations. */
const DEFAULT_AXIS_TEXT: XAxisText = { distance: 'Distance', time: 'Time' }

/**
 * A resolved x-axis: maps a stream's waypoints to numeric x-values plus the
 * title and tick formatter the chart renders. Numeric values drive a linear
 * (proportional) axis so ticks land on true distance/time, not sample index.
 */
export interface XAxisResolver {
  /** The basis actually used (may fall back when the request is unavailable). */
  basis: XAxisBasis
  /** Axis title text (empty for the index fallback). */
  label: string
  /** Numeric x-values for a stream's waypoints. */
  values(waypoints: StreamWaypoint[]): number[]
  /** Formats a numeric x-value for ticks and the tooltip. */
  format(x: number): string
}

const EARTH_RADIUS_M = 6371000
const METERS_PER_MILE = 1609.34

/**
 * Normalizes a heterogeneous waypoint timestamp to epoch seconds. FIT/GPX write
 * an ISO datetime string; Strava writes an integer second-offset (which parses
 * as-is). Returns `null` when absent or unparsable.
 */
function waypointSeconds(time: StreamWaypoint['time']): number | null {
  if (typeof time === 'number') {
    return Number.isFinite(time) ? time : null
  }
  if (typeof time === 'string') {
    const ms = Date.parse(time)
    return Number.isNaN(ms) ? null : ms / 1000
  }
  return null
}

/** The earliest parseable waypoint time across every stream (the axis origin). */
function firstEpochSeconds(streams: ActivityStream[]): number | null {
  let min: number | null = null
  for (const stream of streams) {
    for (const waypoint of stream.waypoints) {
      const seconds = waypointSeconds(waypoint.time)
      if (seconds !== null && (min === null || seconds < min)) {
        min = seconds
      }
    }
  }
  return min
}

/** Great-circle distance between two coordinates, in metres. */
function haversineMeters(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const toRad = (deg: number): number => (deg * Math.PI) / 180
  const dLat = toRad(lat2 - lat1)
  const dLon = toRad(lon2 - lon1)
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(a)))
}

/** Cumulative GPS distance sampled against elapsed seconds (both ascending). */
interface DistanceTrack {
  /** Elapsed seconds from the axis origin, ascending. */
  seconds: number[]
  /** Cumulative metres travelled at each sample. */
  meters: number[]
  /** Fast exact lookup for the common case of shared sample timestamps. */
  bySecond: Map<number, number>
}

/** Whether any stream carries GPS coordinates (distance can be made real). */
export function activityHasGps(streams: ActivityStream[]): boolean {
  return streams.some((stream) =>
    stream.waypoints.some(
      (waypoint) => !Number.isNaN(num(waypoint.lat)) && !Number.isNaN(num(waypoint.lon)),
    ),
  )
}

/**
 * Builds a real cumulative-distance track from the GPS stream (haversine over
 * lat/lon), keyed by elapsed seconds so any metric sample can look up the
 * distance travelled at its timestamp. Returns `null` when no timed GPS exists.
 */
function buildDistanceTrack(streams: ActivityStream[], origin: number): DistanceTrack | null {
  const gps = streams.find((stream) =>
    stream.waypoints.some(
      (waypoint) =>
        !Number.isNaN(num(waypoint.lat)) &&
        !Number.isNaN(num(waypoint.lon)) &&
        waypointSeconds(waypoint.time) !== null,
    ),
  )
  if (!gps) {
    return null
  }
  const seconds: number[] = []
  const meters: number[] = []
  const bySecond = new Map<number, number>()
  let cumulative = 0
  let prevLat: number | null = null
  let prevLon: number | null = null
  for (const waypoint of gps.waypoints) {
    const lat = num(waypoint.lat)
    const lon = num(waypoint.lon)
    const time = waypointSeconds(waypoint.time)
    if (Number.isNaN(lat) || Number.isNaN(lon) || time === null) {
      continue
    }
    if (prevLat !== null && prevLon !== null) {
      cumulative += haversineMeters(prevLat, prevLon, lat, lon)
    }
    const elapsed = time - origin
    seconds.push(elapsed)
    meters.push(cumulative)
    bySecond.set(elapsed, cumulative)
    prevLat = lat
    prevLon = lon
  }
  return seconds.length > 0 ? { seconds, meters, bySecond } : null
}

/** Interpolates the cumulative metres travelled at a given elapsed second. */
function metersAtSecond(track: DistanceTrack, elapsed: number): number {
  const exact = track.bySecond.get(elapsed)
  if (exact !== undefined) {
    return exact
  }
  const { seconds, meters } = track
  if (elapsed <= seconds[0]!) {
    return meters[0]!
  }
  const last = seconds.length - 1
  if (elapsed >= seconds[last]!) {
    return meters[last]!
  }
  // Linear interpolation between the two straddling samples.
  let hi = 1
  while (hi < seconds.length && seconds[hi]! < elapsed) {
    hi += 1
  }
  const lo = hi - 1
  const span = seconds[hi]! - seconds[lo]!
  const fraction = span === 0 ? 0 : (elapsed - seconds[lo]!) / span
  return meters[lo]! + fraction * (meters[hi]! - meters[lo]!)
}

/** Rounds an axis value to at most one decimal, dropping a trailing `.0`. */
function formatAxisNumber(value: number): string {
  return String(Math.round(value * 10) / 10)
}

/** Which x-axis bases can be offered for an activity (in toggle order). */
export function availableXAxisBases(streams: ActivityStream[], activity: Activity): XAxisBasis[] {
  const bases: XAxisBasis[] = []
  if (activity.distance > 0) {
    bases.push('distance')
  }
  const hasTime =
    firstEpochSeconds(streams) !== null ||
    (activity.totalElapsedTime ?? activity.totalTimerTime ?? 0) > 0
  if (hasTime) {
    bases.push('time')
  }
  return bases
}

/**
 * The default x-axis basis: distance only when it is *real* (GPS-derived);
 * otherwise time, which is the honest default for a synthetic-distance workout
 * (e.g. an indoor rower with a total but no per-sample distance).
 */
export function defaultXAxisBasis(streams: ActivityStream[], activity: Activity): XAxisBasis {
  if (activity.distance > 0 && activityHasGps(streams)) {
    return 'distance'
  }
  const available = availableXAxisBases(streams, activity)
  if (available.includes('time')) {
    return 'time'
  }
  return available[0] ?? 'distance'
}

/** Resolves a requested basis to one that is actually available. */
function resolveBasis(
  requested: XAxisBasis | undefined,
  streams: ActivityStream[],
  activity: Activity,
): XAxisBasis {
  const available = availableXAxisBases(streams, activity)
  if (requested && available.includes(requested)) {
    return requested
  }
  return defaultXAxisBasis(streams, activity)
}

/**
 * Builds the x-axis resolver for a chosen basis. Distance uses real GPS
 * cumulative distance when available and falls back to evenly-spaced values from
 * the activity total; time uses real per-sample timestamps and falls back to
 * evenly-spaced elapsed time. With no distance and no time it returns a bare
 * sample-index axis so a line still renders.
 *
 * @param streams - Every stream of the activity (GPS drives real distance).
 * @param activity - The activity domain model (totals, distance).
 * @param units - The user's unit system.
 * @param requested - The requested basis; coerced to an available one.
 * @param text - Translated axis words (defaults to English for direct calls).
 * @returns A resolver producing numeric x-values, a title and a formatter.
 */
export function buildXAxisResolver(
  streams: ActivityStream[],
  activity: Activity,
  units: Units,
  requested?: XAxisBasis,
  text: XAxisText = DEFAULT_AXIS_TEXT,
): XAxisResolver {
  const available = availableXAxisBases(streams, activity)
  if (available.length === 0) {
    // No distance and no time: fall back to sample indices (unitless, untitled).
    return {
      basis: 'time',
      label: '',
      values: (waypoints) => waypoints.map((_, index) => index + 1),
      format: (x) => String(x),
    }
  }

  const basis = resolveBasis(requested, streams, activity)
  const origin = firstEpochSeconds(streams) ?? 0

  if (basis === 'distance') {
    const track = buildDistanceTrack(streams, origin)
    const divisor = units === 'imperial' ? METERS_PER_MILE : 1000
    const unit = units === 'imperial' ? 'mi' : 'km'
    return {
      basis,
      label: `${text.distance} (${unit})`,
      values: (waypoints) => {
        const count = waypoints.length
        return waypoints.map((waypoint, index) => {
          const seconds = waypointSeconds(waypoint.time)
          const meters =
            track && seconds !== null
              ? metersAtSecond(track, seconds - origin)
              : count <= 1
                ? 0
                : (index / (count - 1)) * activity.distance
          return meters / divisor
        })
      },
      format: (x) => `${formatAxisNumber(x)} ${unit}`,
    }
  }

  // Time basis.
  const totalSeconds = activity.totalElapsedTime ?? activity.totalTimerTime ?? 0
  return {
    basis,
    label: text.time,
    values: (waypoints) => {
      const count = waypoints.length
      const localOrigin = waypoints.map((w) => waypointSeconds(w.time)).find((s) => s !== null)
      return waypoints.map((waypoint, index) => {
        const seconds = waypointSeconds(waypoint.time)
        if (seconds !== null && localOrigin != null) {
          return seconds - localOrigin
        }
        return count <= 1 ? 0 : (index / (count - 1)) * totalSeconds
      })
    },
    format: (x) => formatHmsDuration(Math.round(x)),
  }
}

/** A single stat shown beneath a stream chart (e.g. avg/max for that metric). */
export interface StreamStat {
  /** i18n label key. */
  labelKey: string
  /** Formatted value. */
  value: string
  /** Unit suffix (may be empty). */
  unit: string
}

/** Whether a numeric activity field is present and finite. */
function statPresent(value: number | null | undefined): value is number {
  return value !== null && value !== undefined && Number.isFinite(value)
}

/**
 * Builds the summary stats shown beneath a metric's chart, drawn from the
 * activity's aggregate fields (avg/max for the metric), mirroring v1's per-chart
 * stat rows.
 *
 * @param metric - The chart metric.
 * @param activity - The activity domain model.
 * @param units - The user's unit system.
 * @returns The ordered stats to render under the chart.
 */
function buildStreamStats(metric: StreamMetric, activity: Activity, units: Units): StreamStat[] {
  const type = activity.activityType
  const stats: StreamStat[] = []
  const push = (labelKey: string, formatted: { value: string; unit: string }): void => {
    stats.push({ labelKey, value: formatted.value, unit: formatted.unit })
  }
  const watts = (labelKey: string, value: number): void => {
    stats.push({ labelKey, value: String(Math.round(value)), unit: 'W' })
  }

  switch (metric) {
    case 'hr':
      if (statPresent(activity.averageHr)) {
        stats.push({
          labelKey: 'activities.metrics.avgHr',
          value: String(Math.round(activity.averageHr)),
          unit: 'bpm',
        })
      }
      if (statPresent(activity.maxHr)) {
        stats.push({
          labelKey: 'activities.metrics.maxHr',
          value: String(Math.round(activity.maxHr)),
          unit: 'bpm',
        })
      }
      break
    case 'power':
      if (statPresent(activity.averagePower)) {
        watts('activities.metrics.avgPower', activity.averagePower)
      }
      if (statPresent(activity.maxPower)) {
        watts('activities.metrics.maxPower', activity.maxPower)
      }
      if (statPresent(activity.normalizedPower)) {
        watts('activities.metrics.normalizedPower', activity.normalizedPower)
      }
      break
    case 'cadence':
      if (statPresent(activity.averageCadence)) {
        stats.push({
          labelKey: 'activities.metrics.avgCadence',
          value: String(Math.round(presentCadence(activity.averageCadence, type))),
          unit: cadenceUnitLabel(type),
        })
      }
      if (statPresent(activity.maxCadence)) {
        stats.push({
          labelKey: 'activities.metrics.maxCadence',
          value: String(Math.round(presentCadence(activity.maxCadence, type))),
          unit: cadenceUnitLabel(type),
        })
      }
      break
    case 'elevation':
      if (statPresent(activity.elevationGain)) {
        push('activities.metrics.elevationGain', formatElevation(activity.elevationGain, units))
      }
      if (statPresent(activity.elevationLoss)) {
        push('activities.metrics.elevationLoss', formatElevation(activity.elevationLoss, units))
      }
      break
    case 'velocity':
      if (statPresent(activity.averageSpeed)) {
        push('activities.metrics.avgSpeed', formatSpeed(activity.averageSpeed, type, units))
      }
      if (statPresent(activity.maxSpeed)) {
        push('activities.metrics.maxSpeed', formatSpeed(activity.maxSpeed, type, units))
      }
      break
    case 'pace':
      if (statPresent(activity.pace)) {
        push('activities.metrics.avgPace', formatPace(activity.pace, type, units))
      }
      if (statPresent(activity.totalTimerTime)) {
        stats.push({
          labelKey: 'activities.metrics.movingTime',
          value: formatHmsDuration(activity.totalTimerTime),
          unit: '',
        })
      }
      break
    case 'temperature':
      break
    default:
      break
  }
  return stats
}

/** A renderable metric chart derived from one stream. */
export interface StreamChart {
  /** The metric this chart plots. */
  metric: StreamMetric
  /** i18n key for the chart title. */
  titleKey: string
  /** Render options to hand to the chart provider. */
  render: ChartRenderOptions
  /** Summary stats shown beneath the chart. */
  stats: StreamStat[]
}

/**
 * Builds a renderable chart from a single stream, or `null` when the stream
 * type is unknown or carries no usable samples.
 *
 * @param stream - The metric stream.
 * @param activity - The activity domain model (type, distance, aggregate stats).
 * @param units - The user's unit system.
 * @param xAxis - The resolved x-axis (shared across the activity's charts).
 *   Defaults to one built from this stream alone for direct/tested calls.
 * @returns The chart model, or `null`.
 */
export function buildStreamChart(
  stream: ActivityStream,
  activity: Activity,
  units: Units,
  xAxis: XAxisResolver = buildXAxisResolver([stream], activity, units),
): StreamChart | null {
  const metric = METRIC_BY_TYPE[stream.streamType]
  if (!metric || stream.waypoints.length === 0) {
    return null
  }

  const type = activity.activityType
  const data = stream.waypoints.map((waypoint) => extractValue(waypoint, metric, type, units))
  if (data.every((value) => Number.isNaN(value))) {
    return null
  }

  return {
    metric,
    titleKey: METRIC_TITLE_KEY[metric],
    render: {
      // All metric charts render as lines with a gradient fill for visual
      // consistency. Pace is plotted on a normal (non-inverted) axis like every
      // other metric; the y-tick/tooltip formatter renders it as M:SS.
      kind: 'line',
      series: [{ label: METRIC_TITLE_KEY[metric], data, color: METRIC_COLOR[metric] }],
      // Numeric x-values drive a proportional linear axis (true distance/time)
      // with a titled, formatted scale; see buildXAxisResolver.
      xValues: xAxis.values(stream.waypoints),
      xLabel: xAxis.label || undefined,
      xFormat: xAxis.format,
      valueFormat: valueFormatter(metric, type, units),
      zoom: true,
    },
    stats: buildStreamStats(metric, activity, units),
  }
}

/**
 * Builds every metric chart for an activity, in display order and filtered by
 * (1) per-field privacy flags the viewer may see and (2) type relevance (pace
 * vs. speed, no elevation for swimming).
 *
 * @param streams - The activity's metric streams.
 * @param activity - The activity domain model.
 * @param units - The user's unit system.
 * @param isMetricVisible - Predicate deciding whether a metric is visible to
 *   the current viewer (owner vs. privacy flags).
 * @param xAxis - Optional x-axis selection shared by every chart: the requested
 *   basis (coerced to an available one) and translated axis words.
 * @returns The ordered, visible, type-relevant chart models.
 */
export function buildStreamCharts(
  streams: ActivityStream[],
  activity: Activity,
  units: Units,
  isMetricVisible: (metric: StreamMetric) => boolean,
  xAxis?: { basis?: XAxisBasis; text?: XAxisText },
): StreamChart[] {
  const type = activity.activityType
  // One resolver for the whole page so every chart shares the same x-axis
  // (distance derived from the GPS stream is available to metric streams).
  const resolver = buildXAxisResolver(streams, activity, units, xAxis?.basis, xAxis?.text)
  const byMetric = new Map<StreamMetric, StreamChart>()
  for (const stream of streams) {
    const metric = METRIC_BY_TYPE[stream.streamType]
    if (
      !metric ||
      byMetric.has(metric) ||
      !isMetricVisible(metric) ||
      !isMetricRelevantForType(metric, type)
    ) {
      continue
    }
    const chart = buildStreamChart(stream, activity, units, resolver)
    if (chart) {
      byMetric.set(metric, chart)
    }
  }
  return STREAM_METRIC_ORDER.flatMap((metric) => {
    const chart = byMetric.get(metric)
    return chart ? [chart] : []
  })
}

/**
 * Extracts the GPS track polyline from whichever stream carries coordinates.
 *
 * @param streams - The activity's metric streams.
 * @returns Ordered geo points, or an empty array when no coordinates exist.
 */
export function extractTrackPoints(streams: ActivityStream[]): GeoPoint[] {
  for (const stream of streams) {
    const points: GeoPoint[] = []
    for (const waypoint of stream.waypoints) {
      const lat = num(waypoint.lat)
      const lon = num(waypoint.lon)
      if (!Number.isNaN(lat) && !Number.isNaN(lon)) {
        // The map provider's GeoPoint uses `lng`; the backend stores `lon`.
        points.push({ lat, lng: lon })
      }
    }
    if (points.length > 0) {
      return points
    }
  }
  return []
}
