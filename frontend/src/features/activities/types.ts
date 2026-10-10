import type { Schemas } from '@/types'

/**
 * Wire shapes from the generated OpenAPI schema. Kept as the boundary types so a
 * backend contract change surfaces here as a TypeScript error rather than a
 * silent runtime mismatch; the mappers in `services/activities.ts` translate
 * them into the camelCase domain models below.
 */
export type ActivityDto = Schemas['Activity']
export type ActivityStreamDto = Schemas['ActivityStreamsRead']
export type ActivityLapDto = Schemas['ActivityLapsRead']
export type ActivityEditDto = Schemas['ActivityEdit']
export type ActivityMediaDto = Schemas['ActivityMedia']
export type ActivityWorkoutStepDto = Schemas['ActivityWorkoutSteps']
export type ActivitySetDto = Schemas['ActivitySetsRead']
export type ActivityExerciseTitleDto = Schemas['ActivityExerciseTitles']

/**
 * Per-sport aggregated stats for a timeframe (this week / this month). Keys are
 * sport names (`run`, `bike`, `swim`, …); each value is a {@link ActivitySportStats}.
 * Used by the home dashboard's distance/time/calories summary. The wire shape is
 * already clean (sport-keyed, numeric defaults), so the domain model reuses it.
 */
export type ActivityStats = Schemas['ActivityStats']

/** Aggregated distance (m), time (s), and calories (kcal) for one sport. */
export type ActivitySportStats = Schemas['ActivitySportStats']

/** A sport key present in {@link ActivityStats}. */
export type ActivitySportKey = keyof ActivityStats

/**
 * Numeric stream-type codes used by the backend. A single activity exposes one
 * stream per available metric; the detail view fans these out into charts.
 */
export const STREAM_TYPE = {
  hr: 1,
  power: 2,
  cadence: 3,
  elevation: 4,
  velocity: 5,
  pace: 6,
  /**
   * 7 is the lat/lon (GPS) stream — not a chart metric. It is consumed by the
   * map (see `extractTrackPoints`), so it is intentionally absent here.
   */
  temperature: 8,
} as const

/** A metric kind that can be rendered as a stream chart. */
export type StreamMetric = keyof typeof STREAM_TYPE

/**
 * A single sampled point along a stream. The backend serializes waypoints as an
 * untyped object array; this is the subset of keys the detail view consumes.
 * Every field is optional because the present keys depend on the stream type.
 */
export interface StreamWaypoint {
  /** Heart rate in bpm. */
  hr?: number | null
  /** Power in watts. */
  power?: number | null
  /** Cadence (raw; running cadence is doubled for SPM at presentation time). */
  cad?: number | null
  /** Elevation in metres. */
  ele?: number | null
  /** Velocity in metres per second. */
  vel?: number | null
  /** Pace in seconds per metre. */
  pace?: number | null
  /** Temperature in degrees Celsius. */
  temp?: number | null
  /** Latitude in decimal degrees (present on the GPS/map stream, type 7). */
  lat?: number | null
  /** Longitude in decimal degrees (present on the GPS/map stream, type 7). */
  lon?: number | null
}

/** A single heart-rate zone bucket (zones 1–5). */
export interface HrZoneBucket {
  /** Zone number, 1–5. */
  zone: number
  /** Share of time spent in the zone, 0–100. */
  percent: number
  /** Human-readable bpm range for the zone (e.g. `120 - 139`). */
  hrRange: string
  /** Seconds spent in the zone (0 when unknown). */
  timeSeconds: number
}

/** One metric stream for an activity (e.g. the full heart-rate series). */
export interface ActivityStream {
  id: number
  streamType: number
  waypoints: StreamWaypoint[]
  /** Decoded heart-rate zone buckets, present only on the HR stream. */
  hrZones: HrZoneBucket[] | null
}

/** A single lap/split within an activity. */
export interface ActivityLap {
  id: number
  /** Distance in metres. */
  totalDistance: number | null
  /** Elapsed (wall-clock) time in seconds. */
  totalElapsedTime: number | null
  /** Moving time in seconds. */
  totalTimerTime: number | null
  /** Average pace in seconds per metre. */
  enhancedAvgPace: number | null
  /** Average speed in metres per second. */
  enhancedAvgSpeed: number | null
  /** Ascent in metres. */
  totalAscent: number | null
  /** Average heart rate in bpm. */
  avgHeartRate: number | null
  /** Average cadence (raw). */
  avgCadence: number | null
  /** Total cycles (e.g. strides, pedal revolutions, or swim strokes). */
  totalCycles: number | null
  /** Lap intensity label (e.g. `active`, `rest`). */
  intensity: string | null
}

/**
 * One planned step of a structured workout (strength reps, swim stroke, etc.).
 * `repeat_until_steps_cmplt` steps are expanded before display.
 */
export interface ActivityWorkoutStep {
  /** Duration kind: `time`, `reps`, `repeat_until_steps_cmplt`, etc. */
  durationType: string
  /** Duration value: seconds for `time`, repetition count for `reps`. */
  durationValue: number | null
  /** FIT exercise category code (pairs with {@link exerciseName} for lookup). */
  exerciseCategory: number | null
  /** FIT exercise name code. */
  exerciseName: number | null
  /** Prescribed weight (raw units). */
  exerciseWeight: number | null
  /** Step intensity label (e.g. `active`, `rest`, `warmup`). */
  intensity: string | null
  /** Backend message index (ordering / repeat target). */
  messageIndex: number
  /** Secondary target value (e.g. the swim stroke when `targetType` is `swim_stroke`). */
  secondaryTargetValue: string | null
  /** Target kind (e.g. `swim_stroke`). */
  targetType: string | null
  /** Target value (e.g. repeat count for `repeat_until_steps_cmplt`). */
  targetValue: number | null
}

/** One performed set of a strength/structured workout. */
export interface ActivityWorkoutSet {
  id: number
  /** FIT exercise category code (pairs with {@link categorySubtype} for lookup). */
  category: number | null
  /** FIT exercise name code. */
  categorySubtype: number | null
  /** Set duration in seconds. */
  duration: number
  /** Repetition count. */
  repetitions: number | null
  /** Set type label (e.g. `active`, `rest`). */
  setType: string
  /** Weight lifted (raw units). */
  weight: number | null
}

/**
 * An entry in the exercise-name catalogue. Maps a FIT category/name code pair
 * to a human-readable workout-step name.
 */
export interface ActivityExerciseTitle {
  exerciseCategory: number
  exerciseName: number
  wktStepName: string
}

/**
 * Per-field privacy flags. For non-owners (and unauthenticated viewers) a `true`
 * flag hides the corresponding metric/section; owners always see everything.
 */
export interface ActivityPrivacy {
  hideStartTime: boolean
  hideLocation: boolean
  hideMap: boolean
  hideHr: boolean
  hidePower: boolean
  hideCadence: boolean
  hideElevation: boolean
  hideSpeed: boolean
  hidePace: boolean
  hideLaps: boolean
  hideWorkoutSetsSteps: boolean
  hideGear: boolean
}

/**
 * Clean camelCase activity domain model. Decoupled from the wire DTO via
 * {@link mapActivity} so views never touch snake_case and a schema change is
 * caught at the mapper boundary.
 */
export interface Activity {
  id: number
  userId: number | null
  name: string
  description: string | null
  privateNotes: string | null
  activityType: number
  /** 0 - public, 1 - followers, 2 - private. */
  visibility: number
  isHidden: boolean
  gearId: number | null

  /**
   * Row version behind the `ETag`. Sent back as `If-Match` on save so an edit
   * built from a stale copy is refused instead of overwriting whoever saved in
   * between. `null` when the activity came from a response that omits it.
   */
  version: number | null

  /**
   * Activity start as a UTC instant (ISO 8601 with offset), or `null` when the
   * owner hid it. Always render it through `formatZonedDateTime` with
   * {@link Activity.timezone} — never with the viewer's local zone — so the
   * activity reads in the timezone it was recorded in.
   */
  startTime: string | null
  /**
   * IANA timezone the activity was recorded in, resolved from its GPS track at
   * import time (or the server default for GPS-less indoor activities).
   */
  timezone: string | null
  city: string | null
  town: string | null
  country: string | null

  /** Total distance in metres. */
  distance: number
  /** Average pace in seconds per metre. */
  pace: number | null
  /** Average speed in metres per second. */
  averageSpeed: number | null
  /** Max speed in metres per second. */
  maxSpeed: number | null
  averageHr: number | null
  maxHr: number | null
  averagePower: number | null
  maxPower: number | null
  normalizedPower: number | null
  averageCadence: number | null
  maxCadence: number | null
  /** Elevation gain in metres. */
  elevationGain: number | null
  /** Elevation loss in metres. */
  elevationLoss: number | null
  /** Elapsed (wall-clock) time in seconds. */
  totalElapsedTime: number | null
  /** Moving time in seconds. */
  totalTimerTime: number | null
  calories: number | null
  /** Total cycles (e.g. jump-rope jumps, strides, pedal revolutions, or strokes). */
  totalCycles: number | null

  stravaActivityId: number | null
  garminActivityId: number | null

  /**
   * Path to the pre-rendered static map thumbnail, when one exists. The home
   * feed renders this lightweight image instead of mounting a live map per card.
   */
  mapThumbnailPath: string | null

  privacy: ActivityPrivacy
}

/** One page of a user's activities plus the server-reported total count. */
export interface ActivitiesPage {
  /** The activities on the current page, mapped to the clean model. */
  records: Activity[]
  /** Total activities matching the active filters across all pages. */
  total: number
}

/**
 * A photo attached to an activity. `url` is the servable image URL the backend
 * resolved from its storage key; the key itself is not addressable.
 */
export interface ActivityMedia {
  id: number
  activityId: number
  url: string
}

/** Minimal owner identity shown in the activity header. */
export interface ActivityOwner {
  name: string
  username: string
  avatarUrl: string | null
}

/** The editable fields of an activity, as bound by the edit form. */
export interface ActivityEditInput {
  name: string
  activityType: number
  description: string
  privateNotes: string
  /** 0 - public, 1 - followers, 2 - private. */
  visibility: number
  isHidden: boolean
  hideStartTime: boolean
  hideLocation: boolean
  hideMap: boolean
  hideHr: boolean
  hidePower: boolean
  hideCadence: boolean
  hideElevation: boolean
  hideSpeed: boolean
  hidePace: boolean
  hideLaps: boolean
  hideWorkoutSetsSteps: boolean
  hideGear: boolean
}

/**
 * One keyset slice of the following feed.
 *
 * @property items - The slice's activities, newest first.
 * @property nextCursor - Cursor for the next slice, or `null` at the end.
 */
export interface ActivityFeedSlice {
  items: Activity[]
  nextCursor: string | null
}
