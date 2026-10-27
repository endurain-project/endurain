/**
 * Health service — the DTO ↔ domain boundary for the `/health` area. Maps the
 * snake-cased generated OpenAPI shapes to the clean health models so the raw
 * DTOs never leak into composables or components.
 */

import type { Schemas } from '@/types'
import type {
  FastingEntry,
  FastingEntryInput,
  FastingPage,
  FastingSnapshot,
  FastingStats,
  FastingStatus,
  HealthDashboard,
  HealthInterval,
  HealthTargets,
  PoopEntry,
  PoopEntryInput,
  RestingHeartRateEntry,
  RestingHeartRatePage,
  SleepEntry,
  SleepEntryInput,
  SleepStage,
  StepsEntry,
  StepsEntryInput,
  WaterEntry,
  WaterEntryInput,
  WeightEntry,
  WeightEntryInput,
} from '@/features/health/types'

import { apiFetch } from '@/services/http'
import { ifMatchHeaders, rowVersion } from '@/services/ifMatch'

type HealthTargetsDto = Schemas['HealthTargetsRead']
type HealthDashboardDto = Schemas['HealthDashboardResponse']
type HealthFastingDto = Schemas['HealthFastingDashboard']
type HealthFastingReadDto = Schemas['HealthFastingRead']
type HealthFastingStatsDto = Schemas['HealthFastingStatsResponse']
type HealthWeightDto = Schemas['HealthWeightRead']
type HealthStepsDto = Schemas['HealthStepsRead']
type HealthWaterDto = Schemas['HealthWaterRead']
type HealthPoopDto = Schemas['HealthPoopRead']
type HealthSleepDto = Schemas['HealthSleepRead']

/** Maps a raw targets DTO to the clean {@link HealthTargets} model. */
function mapTargets(dto: HealthTargetsDto): HealthTargets {
  return {
    id: dto.id,
    userId: dto.user_id,
    version: rowVersion(dto.version),
    sleepSeconds: dto.sleep ?? null,
    steps: dto.steps ?? null,
    weightKg: dto.weight ?? null,
    fastingSeconds: dto.fasting ?? null,
    waterMl: dto.water_ml ?? null,
    poopCount: dto.poop_count ?? null,
  }
}

/** Maps the raw fasting snapshot, or `null` when no session is present. */
function mapFasting(dto: HealthFastingDto | null | undefined): FastingSnapshot | null {
  if (!dto) return null
  return {
    startTime: dto.fast_start_time,
    status: dto.status,
    actualDurationSeconds: dto.actual_duration_seconds ?? null,
  }
}

/** Maps the consolidated dashboard DTO to the clean {@link HealthDashboard} model. */
function mapDashboard(dto: HealthDashboardDto): HealthDashboard {
  return {
    sleepSeconds: dto.sleep?.total_sleep_seconds ?? null,
    restingHeartRate: dto.sleep?.resting_heart_rate ?? null,
    hrvStatus: dto.sleep?.hrv_status ?? null,
    skinTempDeviation: dto.sleep?.avg_skin_temp_deviation ?? null,
    weightKg: dto.weight?.weight ?? null,
    bmi: dto.weight?.bmi ?? null,
    steps: dto.steps?.steps ?? null,
    fasting: mapFasting(dto.fasting),
    waterMl: dto.water?.amount_ml ?? null,
    poopCount: dto.poop?.count ?? null,
    targets: dto.targets ? mapTargets(dto.targets) : null,
  }
}

/**
 * Fetches the authenticated user's health targets.
 *
 * @param signal - Optional abort signal for cancellation.
 * @returns The user's health targets.
 * @throws {HttpError} When the request fails.
 */
export async function fetchHealthTargets(signal?: AbortSignal): Promise<HealthTargets> {
  const dto = await apiFetch<HealthTargetsDto>('/health/targets', { signal })
  return mapTargets(dto)
}

/**
 * Fetches the authenticated user's consolidated daily health dashboard and targets.
 *
 * @param signal - Optional abort signal for cancellation.
 * @returns Today's health metrics and configured targets.
 * @throws {HttpError} When the request fails.
 */
export async function fetchHealthDashboard(signal?: AbortSignal): Promise<HealthDashboard> {
  const dto = await apiFetch<HealthDashboardDto | null>('/health/stats/daily', { signal })
  return mapDashboard(dto ?? {})
}

/** Shared page/filter shape for paginated health-history endpoints. */
interface HealthHistoryParams {
  /** 1-based page number. */
  page: number
  /** Page size (records per page). */
  numRecords: number
  /** Time window to filter the history to. */
  interval: string
}

/** Shared backend list response shape for health-history endpoints. */
interface HealthHistoryResponse<Dto> {
  /** Total matching rows across all pages. */
  total: number
  /** Records in the current page. */
  items: Dto[]
}

/** Shared clean page shape returned by health-history services. */
interface HealthHistoryPage<Entry> {
  /** Domain records in the current page. */
  records: Entry[]
  /** Total matching rows across all pages. */
  total: number
}

/**
 * Pagination + interval filter for a paginated health-history request — the
 * single shape every metric's list endpoint accepts. The interval is widened
 * per zone (e.g. {@link HealthInterval}).
 */
export interface HealthListParams<Interval extends string = HealthInterval> {
  /** 1-based page number. */
  page: number
  /** Page size (records per page). */
  numRecords: number
  /** Time window to filter the history to. */
  interval: Interval
}

/** Builds the query string for a paginated health-history endpoint. */
function buildHealthHistoryPath(resource: string, params: HealthHistoryParams): string {
  const search = new URLSearchParams({
    page_number: String(params.page),
    num_records: String(params.numRecords),
    interval: params.interval,
  })
  return `/health/${resource}?${search.toString()}`
}

/** Fetches and maps one paginated health-history page. */
async function fetchHealthHistoryPage<Dto, Entry>(
  resource: string,
  params: HealthHistoryParams,
  mapEntry: (dto: Dto) => Entry,
  signal?: AbortSignal,
): Promise<HealthHistoryPage<Entry>> {
  const response = await apiFetch<HealthHistoryResponse<Dto>>(
    buildHealthHistoryPath(resource, params),
    { signal },
  )
  return { records: response.items.map(mapEntry), total: response.total }
}

/** Creates a health resource and maps the returned record. */
async function createHealthResource<Dto, Entry, Payload extends object>(
  resource: string,
  payload: Payload,
  mapEntry: (dto: Dto) => Entry,
): Promise<Entry> {
  const dto = await apiFetch<Dto>(`/health/${resource}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return mapEntry(dto)
}

/** Changes the given fields of a health resource record and maps the returned record. */
async function updateHealthResource<Dto, Entry, Payload extends object>(
  resource: string,
  id: number,
  payload: Payload,
  version: number,
  mapEntry: (dto: Dto) => Entry,
): Promise<Entry> {
  const dto = await apiFetch<Dto>(`/health/${resource}/${id}`, {
    method: 'PATCH',
    headers: ifMatchHeaders(version),
    body: JSON.stringify(payload),
  })
  return mapEntry(dto)
}

/** Deletes a single health-history record. */
async function deleteHealthResource(resource: string, id: number): Promise<void> {
  await apiFetch<void>(`/health/${resource}/${id}`, { method: 'DELETE', responseType: 'void' })
}

/** Updates a subset of the health-targets record and maps the response. */
async function updateHealthTargets(
  payload: Schemas['HealthTargetsUpdate'],
  version: number,
): Promise<HealthTargets> {
  const dto = await apiFetch<HealthTargetsDto>('/health/targets', {
    method: 'PATCH',
    headers: ifMatchHeaders(version),
    body: JSON.stringify(payload),
  })
  return mapTargets(dto)
}

/** The fetch/create/update/delete surface a standard paginated metric exposes. */
interface HealthCrudService<Entry, Input> {
  /** Fetches one filtered page of history and maps each record. */
  fetch: (params: HealthListParams, signal?: AbortSignal) => Promise<HealthHistoryPage<Entry>>
  /** Creates a record, which is refused when the day already has one, and maps the response. */
  create: (input: Input) => Promise<Entry>
  /** Changes an existing record, conditional on the version the caller read, and maps the response. */
  update: (id: number, input: Input, version: number) => Promise<Entry>
  /** Deletes a record by id. */
  remove: (id: number) => Promise<void>
}

/**
 * Builds the standard fetch/create/update/delete surface for a health metric
 * whose create and update share the same snake-cased wire fields (every metric
 * except fasting). Collapses each zone's service down to its unique `mapEntry`
 * and `toWireFields`.
 *
 * @param resource - The `/health/<resource>` path segment.
 * @param mapEntry - Maps a raw DTO to the clean domain entry.
 * @param toWireFields - Maps the clean input to the shared snake-cased payload.
 * @returns The metric's CRUD service.
 */
function createHealthCrudService<Dto, Entry, Wire extends object, Input>(
  resource: string,
  mapEntry: (dto: Dto) => Entry,
  toWireFields: (input: Input) => Wire,
): HealthCrudService<Entry, Input> {
  return {
    fetch: (params, signal) => fetchHealthHistoryPage(resource, params, mapEntry, signal),
    create: (input) => createHealthResource(resource, toWireFields(input), mapEntry),
    update: (id, input, version) =>
      updateHealthResource(resource, id, toWireFields(input), version, mapEntry),
    remove: (id) => deleteHealthResource(resource, id),
  }
}

/**
 * Builds an updater for a single health-targets field. The returned function
 * sends only the one field so a stale local copy never clobbers the user's other
 * targets, and names the version it read so a concurrent change is refused.
 *
 * @param field - The snake-cased targets field this updater writes.
 * @returns A `(version, value)` updater that PATCHes the single field.
 */
function createHealthTargetUpdater<Field extends keyof Schemas['HealthTargetsUpdate']>(
  field: Field,
) {
  return (version: number, value: Schemas['HealthTargetsUpdate'][Field]): Promise<HealthTargets> =>
    // The key is statically constrained to a valid targets field, so the
    // assembled object is a valid partial targets update.
    updateHealthTargets({ [field]: value } as Schemas['HealthTargetsUpdate'], version)
}

/** Maps a raw weight DTO to the clean {@link WeightEntry} model. */
function mapWeightEntry(dto: HealthWeightDto): WeightEntry {
  return {
    id: dto.id,
    userId: dto.user_id,
    version: rowVersion(dto.version),
    date: dto.date ?? null,
    weightKg: dto.weight ?? null,
    bmi: dto.bmi ?? null,
    bodyFatPct: dto.body_fat ?? null,
    bodyWaterPct: dto.body_water ?? null,
    boneMassKg: dto.bone_mass ?? null,
    muscleMassKg: dto.muscle_mass ?? null,
    source: dto.source ?? null,
  }
}

/**
 * Translates the clean weight input into the backend's shared wire fields
 * (snake_case) common to the create and update payloads.
 *
 * @param input - The clean weight input (masses already in kilograms).
 * @returns The snake-cased weight fields.
 */
function toWeightWireFields(input: WeightEntryInput): Schemas['HealthWeightCreate'] {
  return {
    date: input.date,
    weight: input.weightKg,
    bmi: input.bmi,
    body_fat: input.bodyFatPct,
    body_water: input.bodyWaterPct,
    bone_mass: input.boneMassKg,
    muscle_mass: input.muscleMassKg,
  }
}

const weightService = createHealthCrudService('weight', mapWeightEntry, toWeightWireFields)

/** Fetches one filtered page of the user's weight history. */
export const fetchWeightEntries = weightService.fetch
/** Creates (or updates the existing same-date) weight entry. */
export const createWeightEntry = weightService.create
/** Updates an existing weight entry (echoing id + user_id). */
export const updateWeightEntry = weightService.update
/** Deletes a weight entry. */
export const deleteWeightEntry = weightService.remove
/** Updates only the user's weight target, preserving the other targets. */
export const updateWeightTarget = createHealthTargetUpdater('weight')

/** Maps a raw steps DTO to the clean {@link StepsEntry} model. */
function mapStepsEntry(dto: HealthStepsDto): StepsEntry {
  return {
    id: dto.id,
    userId: dto.user_id,
    version: rowVersion(dto.version),
    date: dto.date ?? null,
    steps: dto.steps ?? null,
    source: dto.source ?? null,
  }
}

/**
 * Translates the clean steps input into the backend's shared wire fields
 * (snake_case) common to the create and update payloads.
 *
 * @param input - The clean steps input.
 * @returns The wire fields for a steps create/update payload.
 */
function toStepsWireFields(input: StepsEntryInput): Schemas['HealthStepsCreate'] {
  return {
    date: input.date,
    steps: input.steps,
  }
}

const stepsService = createHealthCrudService('steps', mapStepsEntry, toStepsWireFields)

/** Fetches one filtered page of the user's steps history. */
export const fetchStepsEntries = stepsService.fetch
/** Creates (or updates the existing same-date) steps entry. */
export const createStepsEntry = stepsService.create
/** Updates an existing steps entry (echoing id + user_id). */
export const updateStepsEntry = stepsService.update
/** Deletes a steps entry. */
export const deleteStepsEntry = stepsService.remove
/** Updates only the user's daily steps target, preserving the other targets. */
export const updateStepsTarget = createHealthTargetUpdater('steps')

/** Maps a raw water DTO to the clean {@link WaterEntry} model. */
function mapWaterEntry(dto: HealthWaterDto): WaterEntry {
  return {
    id: dto.id,
    userId: dto.user_id,
    version: rowVersion(dto.version),
    date: dto.date ?? null,
    amountMl: dto.amount_ml ?? null,
    source: dto.source ?? null,
  }
}

/**
 * Translates the clean water input into the backend's shared wire fields
 * (snake_case) common to the create and update payloads.
 *
 * @param input - The clean water input (amount already in millilitres).
 * @returns The wire fields for a water create/update payload.
 */
function toWaterWireFields(input: WaterEntryInput): Schemas['HealthWaterCreate'] {
  return {
    date: input.date,
    amount_ml: input.amountMl,
  }
}

const waterService = createHealthCrudService('water', mapWaterEntry, toWaterWireFields)

/** Fetches one filtered page of the user's water history. */
export const fetchWaterEntries = waterService.fetch
/** Creates (or updates the existing same-date) water entry. */
export const createWaterEntry = waterService.create
/** Updates an existing water entry (echoing id + user_id). */
export const updateWaterEntry = waterService.update
/** Deletes a water entry. */
export const deleteWaterEntry = waterService.remove
/** Updates only the user's daily water target, preserving the other targets. */
export const updateWaterTarget = createHealthTargetUpdater('water_ml')

/** Maps a raw poop DTO to the clean {@link PoopEntry} model. */
function mapPoopEntry(dto: HealthPoopDto): PoopEntry {
  return {
    id: dto.id,
    userId: dto.user_id,
    version: rowVersion(dto.version),
    dateTime: dto.date_time ?? null,
    bristolType: dto.bristol_type ?? null,
    color: dto.color ?? null,
    notes: dto.notes ?? null,
  }
}

/**
 * Translates the clean poop input into the backend's shared wire fields
 * (snake_case) common to the create and update payloads. The source is
 * intentionally omitted so the backend defaults it to manual.
 *
 * @param input - The clean poop input.
 * @returns The wire fields for a poop create/update payload.
 */
function toPoopWireFields(input: PoopEntryInput): Schemas['HealthPoopCreate'] {
  return {
    date_time: input.dateTime,
    bristol_type: input.bristolType,
    color: input.color,
    notes: input.notes,
  }
}

const poopService = createHealthCrudService('poop', mapPoopEntry, toPoopWireFields)

/** Fetches one filtered page of the user's bowel-movement history. */
export const fetchPoopEntries = poopService.fetch
/**
 * Creates a bowel-movement entry. Unlike the other metrics, many poop records
 * can exist per day, so the backend always inserts a new record.
 */
export const createPoopEntry = poopService.create
/** Updates an existing bowel-movement entry (echoing id + user_id). */
export const updatePoopEntry = poopService.update
/** Deletes a bowel-movement entry. */
export const deletePoopEntry = poopService.remove
/** Updates only the user's daily bowel-movement target, preserving the others. */
export const updatePoopTarget = createHealthTargetUpdater('poop_count')

/** Maps a raw sleep DTO to the clean {@link RestingHeartRateEntry} model. */
function mapRhrEntry(dto: HealthSleepDto): RestingHeartRateEntry {
  return {
    id: dto.id,
    date: dto.date ?? null,
    restingHeartRate: dto.resting_heart_rate ?? null,
    source: dto.source ?? null,
  }
}

/**
 * Fetches one page of the authenticated user's resting-heart-rate history.
 *
 * RHR has no endpoint of its own: the backend records it as a field on each
 * sleep session, so this reads the sleep history and keeps only the records
 * that carry a resting heart rate. The page `total` stays the backend's sleep
 * total so pagination still walks the full sleep history.
 *
 * @param params - Page number, size, and the interval filter.
 * @param signal - Optional abort signal for cancellation.
 * @returns The page's resting-heart-rate entries (mapped) plus the total count.
 * @throws {HttpError} When the request fails.
 */
export async function fetchRhrEntries(
  { page, numRecords, interval }: HealthListParams,
  signal?: AbortSignal,
): Promise<RestingHeartRatePage> {
  const response = await fetchHealthHistoryPage(
    'sleep',
    { page, numRecords, interval },
    mapRhrEntry,
    signal,
  )
  return {
    records: response.records.filter((entry) => entry.restingHeartRate !== null),
    total: response.total,
  }
}

/** Maps a raw fasting DTO to the clean {@link FastingEntry} model. */
function mapFastingEntry(dto: HealthFastingReadDto): FastingEntry {
  return {
    id: dto.id,
    userId: dto.user_id,
    version: rowVersion(dto.version),
    fastStartTime: dto.fast_start_time ?? null,
    fastEndTime: dto.fast_end_time ?? null,
    fastingType: dto.fasting_type ?? null,
    targetDurationSeconds: dto.target_duration_seconds ?? null,
    actualDurationSeconds: dto.actual_duration_seconds ?? null,
    status: dto.status ?? null,
    notes: dto.notes ?? null,
    source: dto.source ?? null,
  }
}

/** Maps the raw fasting-stats DTO to the clean {@link FastingStats} model. */
function mapFastingStats(dto: HealthFastingStatsDto): FastingStats {
  return {
    totalFasts: dto.total_fasts,
    currentStreak: dto.current_streak,
    longestStreak: dto.longest_streak,
    avgDurationSeconds: dto.avg_duration_seconds ?? null,
    totalFastingSeconds: dto.total_fasting_seconds,
    completionRate: dto.completion_rate,
  }
}

/**
 * Fetches one page of the authenticated user's fasting history.
 *
 * @param params - Page number, size, and the interval filter.
 * @param signal - Optional abort signal for cancellation.
 * @returns The page's fasting sessions (mapped) plus the total record count.
 * @throws {HttpError} When the request fails.
 */
export async function fetchFastingEntries(
  { page, numRecords, interval }: HealthListParams,
  signal?: AbortSignal,
): Promise<FastingPage> {
  return fetchHealthHistoryPage('fasting', { page, numRecords, interval }, mapFastingEntry, signal)
}

/**
 * Fetches the authenticated user's active (in-progress) fasting session.
 *
 * @param signal - Optional abort signal for cancellation.
 * @returns The active fasting session, or `null` when none is in progress.
 * @throws {HttpError} When the request fails.
 */
export async function fetchActiveFasting(signal?: AbortSignal): Promise<FastingEntry | null> {
  const dto = await apiFetch<HealthFastingReadDto | null>('/health/fasting/active', { signal })
  return dto ? mapFastingEntry(dto) : null
}

/**
 * Fetches the authenticated user's aggregate fasting statistics.
 *
 * @param signal - Optional abort signal for cancellation.
 * @returns The fasting statistics (streaks, totals, completion rate).
 * @throws {HttpError} When the request fails.
 */
export async function fetchFastingStats(signal?: AbortSignal): Promise<FastingStats> {
  const dto = await apiFetch<HealthFastingStatsDto>('/health/fasting/stats', { signal })
  return mapFastingStats(dto)
}

/**
 * Starts a new fasting session. The backend rejects a second active fast, so
 * the caller only exposes this when no session is in progress. The source is
 * fixed to manual for user-started fasts.
 *
 * @param input - The clean fasting input (start time, type, target, notes).
 * @returns The persisted fasting session.
 * @throws {HttpError} When the request fails (e.g. an active fast already exists).
 */
export async function createFastingEntry(input: FastingEntryInput): Promise<FastingEntry> {
  const payload: Schemas['HealthFastingCreate'] = {
    fast_start_time: input.fastStartTime,
    fasting_type: input.fastingType,
    target_duration_seconds: input.targetDurationSeconds,
    notes: input.notes,
    source: 'manual',
  }
  return createHealthResource('fasting', payload, mapFastingEntry)
}

/**
 * Updates an existing fasting session.
 *
 * @param id - The fasting record id.
 * @param userId - The owning user id (echoed back to the backend).
 * @param input - The clean fasting input.
 * @returns The persisted fasting session.
 * @throws {HttpError} When the request fails.
 */
export async function updateFastingEntry(
  id: number,
  input: FastingEntryInput,
  version: number,
): Promise<FastingEntry> {
  const payload: Schemas['HealthFastingUpdate'] = {
    fast_start_time: input.fastStartTime,
    fast_end_time: input.fastEndTime,
    fasting_type: input.fastingType,
    target_duration_seconds: input.targetDurationSeconds,
    actual_duration_seconds: input.actualDurationSeconds,
    status: input.status,
    notes: input.notes,
  }
  return updateHealthResource('fasting', id, payload, version, mapFastingEntry)
}

/**
 * Ends an in-progress fasting session, recording the end time and the final
 * status (completed when the goal was reached, broken when ended early, or
 * cancelled to discard it).
 *
 * @param id - The fasting record id.
 * @param fastEndTime - ISO end timestamp of the fast.
 * @param status - The final status to record.
 * @returns The persisted fasting session.
 * @throws {HttpError} When the request fails.
 */
export async function completeFastingEntry(
  id: number,
  fastEndTime: string,
  status: FastingStatus,
): Promise<FastingEntry> {
  const payload: Schemas['HealthFastingComplete'] = { fast_end_time: fastEndTime, status }
  const dto = await apiFetch<HealthFastingReadDto>(`/health/fasting/${id}/complete`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return mapFastingEntry(dto)
}

/**
 * Deletes a fasting session.
 *
 * @param id - The fasting record id.
 * @throws {HttpError} When the request fails.
 */
export async function deleteFastingEntry(id: number): Promise<void> {
  await deleteHealthResource('fasting', id)
}

/** Updates only the user's fasting-duration target, preserving the other targets. */
export const updateFastingTarget = createHealthTargetUpdater('fasting')

/** Maps a raw sleep-stage DTO to the clean {@link SleepStage} model. */
function mapSleepStage(dto: NonNullable<HealthSleepDto['sleep_stages']>[number]): SleepStage {
  return {
    stageType: dto.stage_type ?? null,
    startTimeGmt: dto.start_time_gmt ?? null,
    endTimeGmt: dto.end_time_gmt ?? null,
    durationSeconds: dto.duration_seconds ?? null,
  }
}

/** Maps a raw sleep DTO to the clean {@link SleepEntry} model. */
function mapSleepEntry(dto: HealthSleepDto): SleepEntry {
  return {
    id: dto.id,
    userId: dto.user_id,
    version: rowVersion(dto.version),
    date: dto.date ?? null,
    sleepStartTimeLocal: dto.sleep_start_time_local ?? null,
    sleepEndTimeLocal: dto.sleep_end_time_local ?? null,
    totalSleepSeconds: dto.total_sleep_seconds ?? null,
    deepSleepSeconds: dto.deep_sleep_seconds ?? null,
    lightSleepSeconds: dto.light_sleep_seconds ?? null,
    remSleepSeconds: dto.rem_sleep_seconds ?? null,
    awakeSleepSeconds: dto.awake_sleep_seconds ?? null,
    sleepScoreOverall: dto.sleep_score_overall ?? null,
    sleepScoreDuration: dto.sleep_score_duration ?? null,
    sleepScoreQuality: dto.sleep_score_quality ?? null,
    deepPercentageScore: dto.deep_percentage_score ?? null,
    lightPercentageScore: dto.light_percentage_score ?? null,
    remPercentageScore: dto.rem_percentage_score ?? null,
    awakeCountScore: dto.awake_count_score ?? null,
    restingHeartRate: dto.resting_heart_rate ?? null,
    avgHeartRate: dto.avg_heart_rate ?? null,
    minHeartRate: dto.min_heart_rate ?? null,
    maxHeartRate: dto.max_heart_rate ?? null,
    avgSkinTempDeviation: dto.avg_skin_temp_deviation ?? null,
    hrvStatus: dto.hrv_status ?? null,
    avgSpo2: dto.avg_spo2 ?? null,
    lowestSpo2: dto.lowest_spo2 ?? null,
    highestSpo2: dto.highest_spo2 ?? null,
    avgRespiration: dto.avg_respiration ?? null,
    lowestRespiration: dto.lowest_respiration ?? null,
    highestRespiration: dto.highest_respiration ?? null,
    avgSleepStress: dto.avg_sleep_stress ?? null,
    awakeCount: dto.awake_count ?? null,
    sleepStages: (dto.sleep_stages ?? []).map(mapSleepStage),
    source: dto.source ?? null,
  }
}

/**
 * Translates a clean {@link SleepStage} into the backend's wire shape. The
 * stage type is constrained to the backend enum (`0` deep … `3` awake) by the
 * form's stage-type selector, so a cast here is safe.
 */
function toSleepStageWire(
  stage: SleepStage,
): NonNullable<Schemas['HealthSleepCreate']['sleep_stages']>[number] {
  return {
    stage_type: stage.stageType as Schemas['SleepStageType'] | null | undefined,
    start_time_gmt: stage.startTimeGmt,
    end_time_gmt: stage.endTimeGmt,
    duration_seconds: stage.durationSeconds,
  }
}

/**
 * Translates the clean sleep input into the backend's shared wire fields
 * (snake_case) common to the create and update payloads. The source is
 * intentionally omitted so the backend keeps it manual for user-entered nights.
 *
 * @param input - The clean sleep input (durations already in seconds).
 * @returns The wire fields for a sleep create/update payload.
 */
function toSleepWireFields(input: SleepEntryInput): Schemas['HealthSleepCreate'] {
  return {
    date: input.date,
    sleep_start_time_local: input.sleepStartTimeLocal,
    sleep_end_time_local: input.sleepEndTimeLocal,
    total_sleep_seconds: input.totalSleepSeconds,
    deep_sleep_seconds: input.deepSleepSeconds,
    light_sleep_seconds: input.lightSleepSeconds,
    rem_sleep_seconds: input.remSleepSeconds,
    awake_sleep_seconds: input.awakeSleepSeconds,
    sleep_score_overall: input.sleepScoreOverall,
    resting_heart_rate: input.restingHeartRate,
    avg_heart_rate: input.avgHeartRate,
    min_heart_rate: input.minHeartRate,
    max_heart_rate: input.maxHeartRate,
    avg_skin_temp_deviation: input.avgSkinTempDeviation,
    avg_spo2: input.avgSpo2,
    lowest_spo2: input.lowestSpo2,
    highest_spo2: input.highestSpo2,
    awake_count: input.awakeCount,
    avg_sleep_stress: input.avgSleepStress,
    sleep_stages: input.sleepStages.map(toSleepStageWire),
  }
}

const sleepService = createHealthCrudService('sleep', mapSleepEntry, toSleepWireFields)

/** Fetches one filtered page of the user's sleep history. */
export const fetchSleepEntries = sleepService.fetch
/** Creates (or updates the existing same-date) sleep entry. */
export const createSleepEntry = sleepService.create
/** Updates an existing sleep entry (echoing id + user_id). */
export const updateSleepEntry = sleepService.update
/** Deletes a sleep entry. */
export const deleteSleepEntry = sleepService.remove
/** Updates only the user's sleep-duration target, preserving the other targets. */
export const updateSleepTarget = createHealthTargetUpdater('sleep')
