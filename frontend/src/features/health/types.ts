/**
 * Health domain models — the camelCased shapes the health feature works with.
 * The snake-cased DTOs from the generated OpenAPI types are mapped to these in
 * the service layer (see `services/health.ts`) so the raw API shapes never leak
 * into composables or components.
 */

import type { Schemas } from '@/types'

/** Bristol Stool Scale type (1–7), the backend's stool-consistency classification. */
export type BristolType = Schemas['BristolType']

/** A stool colour from the backend's fixed palette. */
export type PoopColor = Schemas['Color']

/** The user's configured health goals; `null` means "no target set". */
export interface HealthTargets {
  /** The targets record id (needed to PUT updates in later phases). */
  id: number
  /** The owning user's id. */
  userId: number
  /** Target sleep duration in seconds, or `null`. */
  sleepSeconds: number | null
  /** Target daily step count, or `null`. */
  steps: number | null
  /** Target weight in kilograms, or `null`. */
  weightKg: number | null
  /** Target fasting duration in seconds, or `null`. */
  fastingSeconds: number | null
  /** Target daily water intake in millilitres, or `null`. */
  waterMl: number | null
  /** Target daily bowel-movement count, or `null`. */
  poopCount: number | null
}

/** The active or most recent fasting session shown on the dashboard. */
export interface FastingSnapshot {
  /** ISO start timestamp of the fast. */
  startTime: string
  /** Backend status string (e.g. `in_progress`, `completed`). */
  status: string
  /** Recorded duration in seconds, or `null` while the fast is ongoing. */
  actualDurationSeconds: number | null
}

/** Today's consolidated health metrics for the dashboard zone. */
export interface HealthDashboard {
  /** Total sleep duration in seconds, or `null`. */
  sleepSeconds: number | null
  /** Resting heart rate in bpm, or `null`. */
  restingHeartRate: number | null
  /** Heart-rate-variability status string, or `null`. */
  hrvStatus: string | null
  /** Average skin-temperature deviation in °C, or `null`. */
  skinTempDeviation: number | null
  /** Latest weight in kilograms, or `null`. */
  weightKg: number | null
  /** Body Mass Index, or `null`. */
  bmi: number | null
  /** Today's step count, or `null`. */
  steps: number | null
  /** Active or most recent fasting session, or `null`. */
  fasting: FastingSnapshot | null
  /** Today's water intake in millilitres, or `null`. */
  waterMl: number | null
  /** Today's bowel-movement count, or `null`. */
  poopCount: number | null
}

/** The time window a paginated health history can be filtered to. */
export type HealthInterval =
  'last_7_days' | 'last_30_days' | 'last_90_days' | 'last_year' | 'all_time'

/** The time window the weight history can be filtered to. */
export type WeightInterval = HealthInterval

/**
 * A single weight measurement. All masses are stored in kilograms (the backend
 * canonical unit); the UI converts to the viewer's units at the boundary.
 */
export interface WeightEntry {
  /** The record id (needed to edit/delete). */
  id: number
  /** The owning user's id (echoed back on edit). */
  userId: number
  /** Measurement date as a `yyyy-mm-dd` string, or `null`. */
  date: string | null
  /** Body weight in kilograms, or `null`. */
  weightKg: number | null
  /** Body Mass Index, or `null`. */
  bmi: number | null
  /** Body fat as a percentage, or `null`. */
  bodyFatPct: number | null
  /** Body water as a percentage, or `null`. */
  bodyWaterPct: number | null
  /** Bone mass in kilograms, or `null`. */
  boneMassKg: number | null
  /** Muscle mass in kilograms, or `null`. */
  muscleMassKg: number | null
  /** Integration that supplied the record (e.g. `garmin`), or `null` if manual. */
  source: string | null
}

/**
 * Fields captured by the add/edit weight form, decoupled from the wire payload.
 * Masses are already normalized to kilograms regardless of the viewer's units.
 */
export interface WeightEntryInput {
  /** Measurement date as a `yyyy-mm-dd` string, or `null`. */
  date: string | null
  /** Body weight in kilograms, or `null`. */
  weightKg: number | null
  /** Body Mass Index, or `null`. */
  bmi: number | null
  /** Body fat as a percentage, or `null`. */
  bodyFatPct: number | null
  /** Body water as a percentage, or `null`. */
  bodyWaterPct: number | null
  /** Bone mass in kilograms, or `null`. */
  boneMassKg: number | null
  /** Muscle mass in kilograms, or `null`. */
  muscleMassKg: number | null
}

/** One page of the paginated weight history. */
export interface WeightPage {
  /** The weight entries on this page (newest first). */
  records: WeightEntry[]
  /** Total entries across all pages, for pagination. */
  total: number
}

/** A single daily step-count measurement. */
export interface StepsEntry {
  /** The record id (needed to edit/delete). */
  id: number
  /** The owning user's id (echoed back on edit). */
  userId: number
  /** Measurement date as a `yyyy-mm-dd` string, or `null`. */
  date: string | null
  /** Step count for the day, or `null`. */
  steps: number | null
  /** Integration that supplied the record (e.g. `garmin`), or `null` if manual. */
  source: string | null
}

/** Fields captured by the add/edit steps form, decoupled from the wire payload. */
export interface StepsEntryInput {
  /** Measurement date as a `yyyy-mm-dd` string, or `null`. */
  date: string | null
  /** Step count for the day, or `null`. */
  steps: number | null
}

/** One page of the paginated steps history. */
export interface StepsPage {
  /** The steps entries on this page (newest first). */
  records: StepsEntry[]
  /** Total entries across all pages, for pagination. */
  total: number
}

/** A single daily water-intake measurement (stored in millilitres). */
export interface WaterEntry {
  /** The record id (needed to edit/delete). */
  id: number
  /** The owning user's id (echoed back on edit). */
  userId: number
  /** Measurement date as a `yyyy-mm-dd` string, or `null`. */
  date: string | null
  /** Water consumed for the day in millilitres, or `null`. */
  amountMl: number | null
  /** Integration that supplied the record (e.g. `garmin`), or `null` if manual. */
  source: string | null
}

/** Fields captured by the add/edit water form, decoupled from the wire payload. */
export interface WaterEntryInput {
  /** Measurement date as a `yyyy-mm-dd` string, or `null`. */
  date: string | null
  /** Water consumed for the day in millilitres, or `null`. */
  amountMl: number | null
}

/** One page of the paginated water history. */
export interface WaterPage {
  /** The water entries on this page (newest first). */
  records: WaterEntry[]
  /** Total entries across all pages, for pagination. */
  total: number
}

/**
 * A single bowel-movement record. Unlike the other health metrics, poop is a
 * qualitative event log: many records can exist per day, each timestamped and
 * optionally annotated with a Bristol type, colour, and free-text notes. The
 * source is always manual, so it is omitted from the model.
 */
export interface PoopEntry {
  /** The record id (needed to edit/delete). */
  id: number
  /** The owning user's id (echoed back on edit). */
  userId: number
  /** ISO timestamp of the bowel movement, or `null`. */
  dateTime: string | null
  /** Bristol Stool Scale type (1–7), or `null` when not recorded. */
  bristolType: BristolType | null
  /** Stool colour, or `null` when not recorded. */
  color: PoopColor | null
  /** Optional free-text notes, or `null`. */
  notes: string | null
}

/** Fields captured by the add/edit poop form, decoupled from the wire payload. */
export interface PoopEntryInput {
  /** ISO timestamp of the bowel movement, or `null`. */
  dateTime: string | null
  /** Bristol Stool Scale type (1–7), or `null`. */
  bristolType: BristolType | null
  /** Stool colour, or `null`. */
  color: PoopColor | null
  /** Optional free-text notes, or `null`. */
  notes: string | null
}

/** One page of the paginated bowel-movement history. */
export interface PoopPage {
  /** The poop entries on this page (newest first). */
  records: PoopEntry[]
  /** Total entries across all pages, for pagination. */
  total: number
}

/**
 * A single resting-heart-rate reading. Unlike the other zones, RHR is a
 * read-only view derived from the sleep records (the backend stores resting
 * heart rate as a field on each sleep session), so there is no input shape.
 */
export interface RestingHeartRateEntry {
  /** The underlying sleep record id (used as the list key). */
  id: number
  /** Measurement date as a `yyyy-mm-dd` string, or `null`. */
  date: string | null
  /** Resting heart rate in beats per minute, or `null`. */
  restingHeartRate: number | null
  /** Integration that supplied the record (e.g. `garmin`), or `null` if manual. */
  source: string | null
}

/** One page of the paginated resting-heart-rate history. */
export interface RestingHeartRatePage {
  /** The resting-heart-rate entries on this page (newest first). */
  records: RestingHeartRateEntry[]
  /** Total entries across all pages, for pagination. */
  total: number
}

/** A fasting protocol (e.g. `16:8`) or `custom` for a user-defined duration. */
export type FastingType = Schemas['FastingType']

/** The lifecycle status of a fasting session. */
export type FastingStatus = Schemas['FastingStatus']

/**
 * A single fasting session — either the one in progress or a historical record.
 * Fasting is unlike the metric zones: a session spans a start/end window, has a
 * lifecycle status, and tracks both a target and the actual elapsed duration.
 */
export interface FastingEntry {
  /** The record id (needed to edit/delete/complete). */
  id: number
  /** The owning user's id (echoed back on edit). */
  userId: number
  /** ISO start timestamp of the fast, or `null`. */
  fastStartTime: string | null
  /** ISO end timestamp of the fast, or `null` while ongoing. */
  fastEndTime: string | null
  /** The fasting protocol, or `null`. */
  fastingType: FastingType | null
  /** Target fasting duration in seconds, or `null`. */
  targetDurationSeconds: number | null
  /** Actual elapsed duration in seconds, or `null` while ongoing. */
  actualDurationSeconds: number | null
  /** Current lifecycle status, or `null`. */
  status: FastingStatus | null
  /** Optional free-text notes, or `null`. */
  notes: string | null
  /** Integration that supplied the record (e.g. `garmin`), or `null` if manual. */
  source: string | null
}

/**
 * Fields captured by the start/edit fasting form, decoupled from the wire
 * payload. The end time, status, and actual duration are only meaningful when
 * editing an existing fast (a freshly started fast is still in progress).
 */
export interface FastingEntryInput {
  /** ISO start timestamp of the fast, or `null`. */
  fastStartTime: string | null
  /** ISO end timestamp of the fast, or `null`. */
  fastEndTime: string | null
  /** The fasting protocol, or `null`. */
  fastingType: FastingType | null
  /** Target fasting duration in seconds, or `null`. */
  targetDurationSeconds: number | null
  /** Actual elapsed duration in seconds, or `null`. */
  actualDurationSeconds: number | null
  /** Lifecycle status, or `null` (only set when editing). */
  status: FastingStatus | null
  /** Optional free-text notes, or `null`. */
  notes: string | null
}

/** One page of the paginated fasting history. */
export interface FastingPage {
  /** The fasting sessions on this page (newest first). */
  records: FastingEntry[]
  /** Total sessions across all pages, for pagination. */
  total: number
}

/** Aggregate fasting statistics shown above the history. */
export interface FastingStats {
  /** Total number of completed fasts. */
  totalFasts: number
  /** Current consecutive-day fasting streak. */
  currentStreak: number
  /** Longest consecutive-day fasting streak. */
  longestStreak: number
  /** Average fasting duration in seconds, or `null` when there are no fasts. */
  avgDurationSeconds: number | null
  /** Total time spent fasting, in seconds. */
  totalFastingSeconds: number
  /** Percentage of started fasts that were completed (0–100). */
  completionRate: number
}

/**
 * One stage segment of a night's sleep (a contiguous span in a single stage).
 * Drives the hypnogram timeline. `stageType` follows the backend enum:
 * `0` deep, `1` light, `2` REM, `3` awake.
 */
export interface SleepStage {
  /** Stage classification (`0` deep, `1` light, `2` REM, `3` awake), or `null`. */
  stageType: number | null
  /** ISO start timestamp of the segment (GMT), or `null`. */
  startTimeGmt: string | null
  /** ISO end timestamp of the segment (GMT), or `null`. */
  endTimeGmt: string | null
  /** Segment length in seconds, or `null`. */
  durationSeconds: number | null
}

/**
 * A single night's sleep session. The backend captures a rich set of metrics
 * (stage breakdown, heart rate, SpO2, respiration, sub-scores, the stage
 * timeline) that Garmin populates and a manual entry can fill in part. All
 * durations are stored in seconds.
 */
export interface SleepEntry {
  /** The record id (needed to edit/delete). */
  id: number
  /** The owning user's id (echoed back on edit). */
  userId: number
  /** Calendar date of the session as a `yyyy-mm-dd` string, or `null`. */
  date: string | null
  /** Local start-of-sleep timestamp (`yyyy-mm-ddThh:mm`), or `null`. */
  sleepStartTimeLocal: string | null
  /** Local end-of-sleep timestamp (`yyyy-mm-ddThh:mm`), or `null`. */
  sleepEndTimeLocal: string | null
  /** Total sleep duration in seconds, or `null`. */
  totalSleepSeconds: number | null
  /** Deep-sleep duration in seconds, or `null`. */
  deepSleepSeconds: number | null
  /** Light-sleep duration in seconds, or `null`. */
  lightSleepSeconds: number | null
  /** REM-sleep duration in seconds, or `null`. */
  remSleepSeconds: number | null
  /** Awake duration in seconds, or `null`. */
  awakeSleepSeconds: number | null
  /** Overall sleep score (0–100), or `null`. */
  sleepScoreOverall: number | null
  /** Sleep-duration sub-score (`EXCELLENT`/`GOOD`/`FAIR`/`POOR`), or `null`. */
  sleepScoreDuration: string | null
  /** Sleep-quality sub-score, or `null`. */
  sleepScoreQuality: string | null
  /** Deep-sleep percentage sub-score, or `null`. */
  deepPercentageScore: string | null
  /** Light-sleep percentage sub-score, or `null`. */
  lightPercentageScore: string | null
  /** REM-sleep percentage sub-score, or `null`. */
  remPercentageScore: string | null
  /** Awake-count sub-score, or `null`. */
  awakeCountScore: string | null
  /** Resting heart rate in bpm, or `null`. */
  restingHeartRate: number | null
  /** Average heart rate during sleep in bpm, or `null`. */
  avgHeartRate: number | null
  /** Minimum heart rate during sleep in bpm, or `null`. */
  minHeartRate: number | null
  /** Maximum heart rate during sleep in bpm, or `null`. */
  maxHeartRate: number | null
  /** Average skin-temperature deviation in °C, or `null`. */
  avgSkinTempDeviation: number | null
  /** Heart-rate-variability status string, or `null`. */
  hrvStatus: string | null
  /** Average blood-oxygen saturation as a percentage, or `null`. */
  avgSpo2: number | null
  /** Lowest blood-oxygen saturation as a percentage, or `null`. */
  lowestSpo2: number | null
  /** Highest blood-oxygen saturation as a percentage, or `null`. */
  highestSpo2: number | null
  /** Average respiration rate in breaths/min, or `null`. */
  avgRespiration: number | null
  /** Lowest respiration rate in breaths/min, or `null`. */
  lowestRespiration: number | null
  /** Highest respiration rate in breaths/min, or `null`. */
  highestRespiration: number | null
  /** Average sleep stress (0–100), or `null`. */
  avgSleepStress: number | null
  /** Number of times awake during the night, or `null`. */
  awakeCount: number | null
  /** Per-stage timeline driving the hypnogram. Empty when none recorded. */
  sleepStages: SleepStage[]
  /** Integration that supplied the record (e.g. `garmin`), or `null` if manual. */
  source: string | null
}

/** Fields captured by the add/edit sleep form, decoupled from the wire payload. */
export interface SleepEntryInput {
  /** Calendar date of the session as a `yyyy-mm-dd` string, or `null`. */
  date: string | null
  /** Local start-of-sleep timestamp (`yyyy-mm-ddThh:mm`), or `null`. */
  sleepStartTimeLocal: string | null
  /** Local end-of-sleep timestamp (`yyyy-mm-ddThh:mm`), or `null`. */
  sleepEndTimeLocal: string | null
  /** Total sleep duration in seconds, or `null`. */
  totalSleepSeconds: number | null
  /** Deep-sleep duration in seconds, or `null`. */
  deepSleepSeconds: number | null
  /** Light-sleep duration in seconds, or `null`. */
  lightSleepSeconds: number | null
  /** REM-sleep duration in seconds, or `null`. */
  remSleepSeconds: number | null
  /** Awake duration in seconds, or `null`. */
  awakeSleepSeconds: number | null
  /** Overall sleep score (0–100), or `null`. */
  sleepScoreOverall: number | null
  /** Resting heart rate in bpm, or `null`. */
  restingHeartRate: number | null
  /** Average heart rate during sleep in bpm, or `null`. */
  avgHeartRate: number | null
  /** Minimum heart rate during sleep in bpm, or `null`. */
  minHeartRate: number | null
  /** Maximum heart rate during sleep in bpm, or `null`. */
  maxHeartRate: number | null
  /** Average skin-temperature deviation in °C, or `null`. */
  avgSkinTempDeviation: number | null
  /** Average blood-oxygen saturation as a percentage, or `null`. */
  avgSpo2: number | null
  /** Lowest blood-oxygen saturation as a percentage, or `null`. */
  lowestSpo2: number | null
  /** Highest blood-oxygen saturation as a percentage, or `null`. */
  highestSpo2: number | null
  /** Average sleep stress (0–100), or `null`. */
  avgSleepStress: number | null
  /** Number of times awake during the night, or `null`. */
  awakeCount: number | null
  /** Per-stage timeline segments to persist. Empty when none entered. */
  sleepStages: SleepStage[]
}

/** One page of the paginated sleep history. */
export interface SleepPage {
  /** The sleep entries on this page (newest first). */
  records: SleepEntry[]
  /** Total entries across all pages, for pagination. */
  total: number
}
