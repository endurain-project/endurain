import type { Schemas } from '@/types'

import { apiFetch, HttpError } from '@/services/http'
import { todayIsoDate } from '@/utils/datetime'

import type {
  ActivitiesPage,
  Activity,
  ActivityDto,
  ActivityEditDto,
  ActivityEditInput,
  ActivityExerciseTitle,
  ActivityExerciseTitleDto,
  ActivityLap,
  ActivityLapDto,
  ActivitySetDto,
  ActivityStats,
  ActivityStream,
  ActivityStreamDto,
  ActivityWorkoutSet,
  ActivityWorkoutStep,
  ActivityWorkoutStepDto,
  HrZoneBucket,
  StreamWaypoint,
} from '../types'

/** Context controlling whether to hit the authenticated or public endpoints. */
export interface ActivityFetchContext {
  /** Whether the viewer is authenticated. */
  authenticated: boolean
  /** Optional abort signal (e.g. TanStack Query cancellation). */
  signal?: AbortSignal
}

/** Builds the authenticated or public path for an activity sub-resource. */
function resourcePath(authenticated: boolean, authedPath: string, publicPath: string): string {
  return authenticated ? authedPath : publicPath
}

/**
 * Maps an activity DTO to the clean camelCase domain model, collapsing the
 * nullable wire fields into stable defaults.
 *
 * @param dto - The activity wire payload.
 * @returns The activity domain model.
 */
export function mapActivity(dto: ActivityDto): Activity {
  return {
    id: dto.id ?? 0,
    userId: dto.user_id ?? null,
    name: dto.name,
    description: dto.description ?? null,
    privateNotes: dto.private_notes ?? null,
    activityType: dto.activity_type,
    visibility: dto.visibility ?? 0,
    isHidden: dto.is_hidden,
    gearId: dto.gear_id ?? null,

    // The UTC instant plus the recording timezone. Views localize for display
    // via `formatZonedDateTime`, so the athlete's own wall clock is shown to
    // every viewer regardless of where they are.
    startTime: dto.start_time ?? null,
    timezone: dto.timezone ?? null,
    city: dto.city ?? null,
    town: dto.town ?? null,
    country: dto.country ?? null,

    distance: dto.distance,
    pace: dto.pace ?? null,
    averageSpeed: dto.average_speed ?? null,
    maxSpeed: dto.max_speed ?? null,
    averageHr: dto.average_hr ?? null,
    maxHr: dto.max_hr ?? null,
    averagePower: dto.average_power ?? null,
    maxPower: dto.max_power ?? null,
    normalizedPower: dto.normalized_power ?? null,
    averageCadence: dto.average_cad ?? null,
    maxCadence: dto.max_cad ?? null,
    elevationGain: dto.elevation_gain ?? null,
    elevationLoss: dto.elevation_loss ?? null,
    totalElapsedTime: dto.total_elapsed_time ?? null,
    totalTimerTime: dto.total_timer_time ?? null,
    calories: dto.calories ?? null,
    totalCycles: dto.total_cycles ?? null,

    stravaActivityId: dto.strava_activity_id ?? null,
    garminActivityId: dto.garminconnect_activity_id ?? null,

    mapThumbnailPath: dto.map_thumbnail_path ?? null,

    privacy: {
      hideStartTime: dto.hide_start_time ?? false,
      hideLocation: dto.hide_location ?? false,
      hideMap: dto.hide_map ?? false,
      hideHr: dto.hide_hr ?? false,
      hidePower: dto.hide_power ?? false,
      hideCadence: dto.hide_cadence ?? false,
      hideElevation: dto.hide_elevation ?? false,
      hideSpeed: dto.hide_speed ?? false,
      hidePace: dto.hide_pace ?? false,
      hideLaps: dto.hide_laps ?? false,
      hideWorkoutSetsSteps: dto.hide_workout_sets_steps ?? false,
      hideGear: dto.hide_gear ?? false,
    },
  }
}

/**
 * Decodes the HR stream's `zone_percentages.hr` block into ordered zone buckets
 * (zones 1–5). Returns `null` when the payload is absent or malformed.
 *
 * Wire shape: `{ hr: { zone_1: { percent, hr, time_seconds }, … } }`.
 *
 * @param zonePercentages - The stream's raw `zone_percentages` field.
 * @returns Ordered zone buckets, or `null`.
 */
function mapHrZones(zonePercentages: ActivityStreamDto['zone_percentages']): HrZoneBucket[] | null {
  if (!zonePercentages || typeof zonePercentages !== 'object') {
    return null
  }
  const hr = (zonePercentages as Record<string, unknown>).hr
  if (!hr || typeof hr !== 'object') {
    return null
  }
  const block = hr as Record<string, unknown>
  const buckets: HrZoneBucket[] = []
  for (let zone = 1; zone <= 5; zone += 1) {
    const entry = block[`zone_${zone}`]
    if (entry && typeof entry === 'object') {
      const record = entry as Record<string, unknown>
      buckets.push({
        zone,
        percent: typeof record.percent === 'number' ? record.percent : 0,
        hrRange: typeof record.hr === 'string' ? record.hr : '',
        timeSeconds: typeof record.time_seconds === 'number' ? record.time_seconds : 0,
      })
    }
  }
  return buckets.length > 0 ? buckets : null
}

/**
 * Maps a stream DTO to the domain model. The wire `stream_waypoints` are an
 * untyped object array; they are narrowed to {@link StreamWaypoint} here and
 * read defensively downstream. The HR stream's zone percentages are decoded
 * into {@link HrZoneBucket}s.
 *
 * @param dto - The stream wire payload.
 * @returns The stream domain model.
 */
export function mapActivityStream(dto: ActivityStreamDto): ActivityStream {
  return {
    id: dto.id,
    streamType: dto.stream_type,
    waypoints: (dto.stream_waypoints ?? []) as StreamWaypoint[],
    hrZones: mapHrZones(dto.zone_percentages),
  }
}

/**
 * Maps a lap DTO to the domain model.
 *
 * @param dto - The lap wire payload.
 * @returns The lap domain model.
 */
export function mapActivityLap(dto: ActivityLapDto): ActivityLap {
  return {
    id: dto.id,
    totalDistance: dto.total_distance ?? null,
    totalElapsedTime: dto.total_elapsed_time ?? null,
    totalTimerTime: dto.total_timer_time ?? null,
    enhancedAvgPace: dto.enhanced_avg_pace ?? null,
    enhancedAvgSpeed: dto.enhanced_avg_speed ?? null,
    totalAscent: dto.total_ascent ?? null,
    avgHeartRate: dto.avg_heart_rate ?? null,
    avgCadence: dto.avg_cadence ?? null,
    totalCycles: dto.total_cycles ?? null,
    intensity: dto.intensity ?? null,
  }
}

/**
 * Fetches a single activity by id. Uses the authenticated endpoint when the
 * viewer is logged in, otherwise the public shareable-link endpoint. Returns
 * `null` when the activity is missing or not publicly shareable.
 *
 * @param id - Activity identifier.
 * @param context - Auth + cancellation context.
 * @returns The activity, or `null` when not found/accessible.
 */
export async function fetchActivity(
  id: number,
  context: ActivityFetchContext,
): Promise<Activity | null> {
  const path = resourcePath(context.authenticated, `/activities/${id}`, `/public/activities/${id}`)
  try {
    const dto = await apiFetch<ActivityDto | null>(path, {
      auth: context.authenticated,
      signal: context.signal,
    })
    return dto ? mapActivity(dto) : null
  } catch (error) {
    if (error instanceof HttpError && (error.status === 404 || error.status === 422)) {
      return null
    }
    throw error
  }
}

/**
 * Searches the viewer's activities whose name contains the given term. The
 * backend scopes the result to activities the caller may see (their own plus
 * any visible to them).
 *
 * @param name - The search term.
 * @param signal - Optional abort signal for cancellation.
 * @returns The matching activities, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function searchActivitiesByName(
  name: string,
  signal?: AbortSignal,
): Promise<Activity[]> {
  const params = new URLSearchParams({ name })
  const dtos = await apiFetch<ActivityDto[] | null>(`/activities?${params.toString()}`, { signal })
  return (dtos ?? []).map(mapActivity)
}

/** A timeframe accepted by the activity stats endpoints. */
export type ActivityStatsTimeframe = 'week' | 'month'

/**
 * Fetches one page of the authenticated viewer's own activities for the home
 * feed, newest first.
 *
 * @param page - 1-based page number.
 * @param numRecords - Page size.
 * @param signal - Optional abort signal for cancellation.
 * @returns The page's activities, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function fetchUserActivities(
  page: number,
  numRecords: number,
  signal?: AbortSignal,
): Promise<Activity[]> {
  const params = new URLSearchParams({
    page_number: String(page),
    num_records: String(numRecords),
  })
  const dtos = await apiFetch<ActivityDto[] | null>(`/activities?${params.toString()}`, { signal })
  return (dtos ?? []).map(mapActivity)
}

/**
 * Fetches one page of activities from the people the viewer follows (the
 * following feed), newest first. Authenticated-only.
 *
 * @param page - 1-based page number.
 * @param numRecords - Page size.
 * @param signal - Optional abort signal for cancellation.
 * @returns The page's activities, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function fetchFollowersActivities(
  page: number,
  numRecords: number,
  signal?: AbortSignal,
): Promise<Activity[]> {
  const params = new URLSearchParams({
    page_number: String(page),
    num_records: String(numRecords),
  })
  const page_ = await apiFetch<Schemas['ActivityPage']>(`/activities/feed?${params.toString()}`, {
    signal,
  })
  return (page_.items ?? []).map(mapActivity)
}

/** Formats a `Date` as a `YYYY-MM-DD` string using its local calendar fields. */
function isoDate(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

/**
 * Computes the inclusive Monday–Sunday date range for an ISO-week offset, where
 * `0` is the current week and each increment steps one week into the past.
 *
 * Uses the viewer's **local** calendar. Reading UTC fields meant a user far
 * enough east or west was shown the neighbouring week for part of every day —
 * for someone at UTC+13, all of Monday morning belonged to "last week".
 */
function weekDateRange(weekOffset: number): { startDate: string; endDate: string } {
  const now = new Date()
  const mondayIndex = (now.getDay() + 6) % 7 // 0 = Monday
  const monday = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate() - mondayIndex - weekOffset * 7,
  )
  const sunday = new Date(monday)
  sunday.setDate(monday.getDate() + 6)
  return { startDate: isoDate(monday), endDate: isoDate(sunday) }
}

/** Computes the inclusive first-of-month → today date range in the viewer's local calendar. */
function currentMonthRange(): { startDate: string; endDate: string } {
  const now = new Date()
  const first = new Date(now.getFullYear(), now.getMonth(), 1)
  return { startDate: isoDate(first), endDate: isoDate(now) }
}

/**
 * Fetches a user's activities for a single ISO week, newest first. Week `0` is
 * the current week and each increment steps one week into the past (mirrors
 * v1's public-profile week browser). Authenticated-only; the backend applies
 * the viewer's visibility rules.
 *
 * @param userId - The profile owner's user id.
 * @param week - Week offset (0 = this week).
 * @param signal - Optional abort signal for cancellation.
 * @returns That week's activities, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function fetchUserWeekActivities(
  userId: number,
  week: number,
  signal?: AbortSignal,
): Promise<Activity[]> {
  const { startDate, endDate } = weekDateRange(week)
  const params = new URLSearchParams({
    start_date: startDate,
    end_date: endDate,
    num_records: '200',
  })
  const page_ = await apiFetch<Schemas['ActivityPage']>(
    `/activities/users/${userId}?${params.toString()}`,
    { signal },
  )
  return (page_.items ?? []).map(mapActivity)
}

/** Backend-validated sortable columns for the user activities list. */
export type ActivitySortBy =
  | 'type'
  | 'name'
  | 'location'
  | 'start_time'
  | 'duration'
  | 'distance'
  | 'pace'
  | 'calories'
  | 'elevation'
  | 'average_hr'

/** Sort direction for the user activities list. */
export type ActivitySortOrder = 'asc' | 'desc'

/** Server-side filters for the user activities list. */
export interface ActivityListFilters {
  /** Activity-type code, or `0`/`null` for all types. */
  type: number | null
  /** Inclusive start date (`YYYY-MM-DD`), or `null`. */
  startDate: string | null
  /** Inclusive end date (`YYYY-MM-DD`), or `null`. */
  endDate: string | null
  /** Case-insensitive name/location search, or `null`. */
  nameSearch: string | null
}

/** Page + filter + sort input for a user activities list request. */
export interface ActivityListParams {
  /** The list owner's user id (the authenticated viewer). */
  userId: number
  /** 1-based page number. */
  page: number
  /** Page size (records per page). */
  numRecords: number
  /** The active server-side filters. */
  filters: ActivityListFilters
  /** The column to sort by. */
  sortBy: ActivitySortBy
  /** The sort direction. */
  sortOrder: ActivitySortOrder
}

/**
 * Appends the shared activity list/count filter query parameters in a stable
 * order, omitting empty values so the query string only carries active filters.
 *
 * @param params - The target search params (mutated in place).
 * @param filters - The active filters.
 */
function appendActivityFilters(params: URLSearchParams, filters: ActivityListFilters): void {
  if (filters.type !== null && filters.type > 0) {
    params.set('type', String(filters.type))
  }
  if (filters.startDate) {
    params.set('start_date', filters.startDate)
  }
  if (filters.endDate) {
    params.set('end_date', filters.endDate)
  }
  const name = filters.nameSearch?.trim()
  if (name) {
    params.set('name', name)
  }
}

/**
 * Fetches one filtered, sorted page of a user's own activities together with the
 * total matching count, powering the activities list view. The backend returns
 * both in a single page envelope, so the filters cannot drift between a list and
 * a separate count request. Authenticated-only.
 *
 * @param params - The list owner, page, size, filters, and sort.
 * @param signal - Optional abort signal for cancellation.
 * @returns The page's activities (mapped) plus the total matching count.
 * @throws {HttpError} When the request fails.
 */
export async function fetchUserActivitiesPage(
  { page, numRecords, filters, sortBy, sortOrder }: ActivityListParams,
  signal?: AbortSignal,
): Promise<ActivitiesPage> {
  const listParams = new URLSearchParams()
  appendActivityFilters(listParams, filters)
  listParams.set('sort_by', sortBy)
  listParams.set('sort_order', sortOrder)
  listParams.set('page_number', String(page))
  listParams.set('num_records', String(numRecords))

  const page_ = await apiFetch<Schemas['ActivityPage']>(`/activities?${listParams.toString()}`, {
    signal,
  })

  return { records: (page_.items ?? []).map(mapActivity), total: page_.total }
}

/**
 * Fetches the authenticated user's owned activity types as a `code → name` map.
 * The backend returns a `{ code: name }` object keyed by stringified codes; this
 * normalizes the keys to numbers and drops any non-numeric entries. Backs both
 * the activity-type filter options and the summary view's name-based type filter
 * (the summary endpoint filters by type name, not code).
 *
 * @param signal - Optional abort signal for cancellation.
 * @returns A map of activity-type code to backend type name.
 * @throws {HttpError} When the request fails.
 */
export async function fetchUserActivityTypeMap(signal?: AbortSignal): Promise<Map<number, string>> {
  const types = await apiFetch<Record<string, string> | null>('/activities/types', { signal })
  const map = new Map<number, string>()
  if (!types) {
    return map
  }
  for (const [code, name] of Object.entries(types)) {
    const numericCode = Number(code)
    if (Number.isFinite(numericCode)) {
      map.set(numericCode, name)
    }
  }
  return map
}

/**
 * Fetches the distinct activity-type codes the authenticated user owns, sorted
 * ascending. Backs the activity-type filter so it only offers types the user
 * actually has. Derives from {@link fetchUserActivityTypeMap}; the labels are
 * localized client-side via `presentActivityType`.
 *
 * @param signal - Optional abort signal for cancellation.
 * @returns The user's distinct activity-type codes, ascending.
 * @throws {HttpError} When the request fails.
 */
export async function fetchUserActivityTypeCodes(signal?: AbortSignal): Promise<number[]> {
  const map = await fetchUserActivityTypeMap(signal)
  return [...map.keys()].sort((a, b) => a - b)
}

/**
 * Fetches a user's per-sport aggregated stats for the current week or month,
 * powering the home dashboard's distance/time/calories summary.
 *
 * Sends the viewer's local calendar date so the backend resolves "this week" /
 * "this month" against their calendar rather than the server's UTC one.
 *
 * @param userId - The user whose stats to fetch.
 * @param timeframe - `week` (this week) or `month` (this month).
 * @param signal - Optional abort signal for cancellation.
 * @returns The per-sport stats (an empty object when the user has no activity).
 * @throws {HttpError} When the request fails.
 */
export async function fetchActivityStats(
  userId: number,
  timeframe: ActivityStatsTimeframe,
  signal?: AbortSignal,
): Promise<ActivityStats> {
  const params = new URLSearchParams({ period: timeframe, date: todayIsoDate() })
  const stats = await apiFetch<ActivityStats | null>(
    `/activities/users/${userId}/stats?${params.toString()}`,
    { signal },
  )
  return stats ?? {}
}

/**
 * Fetches the number of activities a user recorded in the current month,
 * surfaced as the headline figure on the public-profile header.
 *
 * @param userId - The user whose monthly activity count to load.
 * @param signal - Optional abort signal for cancellation.
 * @returns The count of this-month activities (`0` when none).
 * @throws {HttpError} When the request fails.
 */
export async function fetchUserThisMonthActivityCount(
  userId: number,
  signal?: AbortSignal,
): Promise<number> {
  const { startDate, endDate } = currentMonthRange()
  const params = new URLSearchParams({
    start_date: startDate,
    end_date: endDate,
    num_records: '200',
  })
  const page_ = await apiFetch<Schemas['ActivityPage']>(
    `/activities/users/${userId}?${params.toString()}`,
    { signal },
  )
  // The envelope's total is the real match count. This previously returned the
  // length of the returned page, so any week with more than num_records
  // activities under-reported.
  return page_.total
}

/**
 * Triggers a refresh of the viewer's linked-integration activities (Strava /
 * Garmin Connect) and returns the freshly imported ones. Authenticated-only.
 *
 * @param signal - Optional abort signal for cancellation.
 * @returns The newly imported activities, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function refreshActivities(signal?: AbortSignal): Promise<Activity[]> {
  const dtos = await apiFetch<ActivityDto[] | null>('/activities/refresh', { signal })
  return (dtos ?? []).map(mapActivity)
}

/**
 * Fetches all metric streams for an activity (auth or public endpoint).
 *
 * @param id - Activity identifier.
 * @param context - Auth + cancellation context.
 * @returns The activity's streams.
 */
export async function fetchActivityStreams(
  id: number,
  context: ActivityFetchContext,
): Promise<ActivityStream[]> {
  const path = resourcePath(
    context.authenticated,
    `/activities/${id}/streams`,
    `/public/activities/${id}/streams`,
  )
  const dtos = await apiFetch<ActivityStreamDto[] | null>(path, {
    auth: context.authenticated,
    signal: context.signal,
  })
  return (dtos ?? []).map(mapActivityStream)
}

/**
 * Fetches all laps for an activity (auth or public endpoint).
 *
 * @param id - Activity identifier.
 * @param context - Auth + cancellation context.
 * @returns The activity's laps.
 */
export async function fetchActivityLaps(
  id: number,
  context: ActivityFetchContext,
): Promise<ActivityLap[]> {
  const path = resourcePath(
    context.authenticated,
    `/activities/${id}/laps`,
    `/public/activities/${id}/laps`,
  )
  const dtos = await apiFetch<ActivityLapDto[] | null>(path, {
    auth: context.authenticated,
    signal: context.signal,
  })
  return (dtos ?? []).map(mapActivityLap)
}

/**
 * Maps a workout-step DTO to the domain model.
 *
 * @param dto - The workout-step wire payload.
 * @returns The workout-step domain model.
 */
export function mapActivityWorkoutStep(dto: ActivityWorkoutStepDto): ActivityWorkoutStep {
  return {
    durationType: dto.duration_type,
    durationValue: dto.duration_value ?? null,
    exerciseCategory: dto.exercise_category ?? null,
    exerciseName: dto.exercise_name ?? null,
    exerciseWeight: dto.exercise_weight ?? null,
    intensity: dto.intensity ?? null,
    messageIndex: dto.message_index,
    secondaryTargetValue: dto.secondary_target_value ?? null,
    targetType: dto.target_type ?? null,
    targetValue: dto.target_value ?? null,
  }
}

/**
 * Maps a workout-set DTO to the domain model.
 *
 * @param dto - The workout-set wire payload.
 * @returns The workout-set domain model.
 */
export function mapActivitySet(dto: ActivitySetDto): ActivityWorkoutSet {
  return {
    id: dto.id,
    category: dto.category ?? null,
    categorySubtype: dto.category_subtype ?? null,
    duration: dto.duration,
    repetitions: dto.repetitions ?? null,
    setType: dto.set_type,
    weight: dto.weight ?? null,
  }
}

/**
 * Maps an exercise-title DTO to the domain model.
 *
 * @param dto - The exercise-title wire payload.
 * @returns The exercise-title domain model.
 */
export function mapActivityExerciseTitle(dto: ActivityExerciseTitleDto): ActivityExerciseTitle {
  return {
    exerciseCategory: dto.exercise_category,
    exerciseName: dto.exercise_name,
    wktStepName: dto.wkt_step_name,
  }
}

/**
 * Fetches an activity's planned workout steps (auth or public endpoint).
 *
 * @param id - Activity identifier.
 * @param context - Auth + cancellation context.
 * @returns The activity's workout steps.
 */
export async function fetchActivityWorkoutSteps(
  id: number,
  context: ActivityFetchContext,
): Promise<ActivityWorkoutStep[]> {
  const path = resourcePath(
    context.authenticated,
    `/activities/${id}/workout-steps`,
    `/public/activities/${id}/workout-steps`,
  )
  const dtos = await apiFetch<ActivityWorkoutStepDto[] | null>(path, {
    auth: context.authenticated,
    signal: context.signal,
  })
  return (dtos ?? []).map(mapActivityWorkoutStep)
}

/**
 * Fetches an activity's performed workout sets (auth or public endpoint).
 *
 * @param id - Activity identifier.
 * @param context - Auth + cancellation context.
 * @returns The activity's workout sets.
 */
export async function fetchActivitySets(
  id: number,
  context: ActivityFetchContext,
): Promise<ActivityWorkoutSet[]> {
  const path = resourcePath(
    context.authenticated,
    `/activities/${id}/sets`,
    `/public/activities/${id}/sets`,
  )
  const dtos = await apiFetch<ActivitySetDto[] | null>(path, {
    auth: context.authenticated,
    signal: context.signal,
  })
  return (dtos ?? []).map(mapActivitySet)
}

/**
 * Fetches the exercise-name catalogue used to resolve workout step/set exercise
 * names (auth or public endpoint). The public endpoint returns `null` when the
 * activity is not publicly shareable.
 *
 * @param context - Auth + cancellation context.
 * @returns The exercise-title catalogue.
 */
export async function fetchActivityExerciseTitles(
  context: ActivityFetchContext,
): Promise<ActivityExerciseTitle[]> {
  const path = resourcePath(
    context.authenticated,
    `/activities_exercise_titles/all`,
    `/public/activities_exercise_titles/all`,
  )
  const dtos = await apiFetch<ActivityExerciseTitleDto[] | null>(path, {
    auth: context.authenticated,
    signal: context.signal,
  })
  return (dtos ?? []).map(mapActivityExerciseTitle)
}

/**
 * Sets the gear associated with an activity, or clears it when `gearId` is
 * `null`, via a partial `PATCH /activities/{id}` update.
 *
 * @param activity - The activity to update (supplies its id).
 * @param gearId - The gear to associate, or `null` to remove the association.
 * @returns The updated activity domain model.
 * @throws {HttpError} When the update fails.
 */
export async function setActivityGear(
  activity: Activity,
  gearId: number | null,
): Promise<Activity> {
  const body: ActivityEditDto = { gear_id: gearId }
  const dto = await apiFetch<ActivityDto>(`/activities/${activity.id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
  return mapActivity(dto)
}

/**
 * Permanently deletes an activity owned by the current user.
 *
 * @param id - Activity identifier.
 * @throws {HttpError} When the delete fails (e.g. not found or not owned).
 */
export async function deleteActivity(id: number): Promise<void> {
  await apiFetch(`/activities/${id}`, { method: 'DELETE' })
}

/**
 * Changes the visibility of every existing activity owned by the current user.
 * New activities keep using the profile default configured separately.
 *
 * @param visibility - The visibility to apply to all existing activities.
 * @throws {HttpError} When the update fails.
 */
export async function updateUserActivitiesVisibility(
  visibility: Schemas['ActivityVisibility'],
): Promise<void> {
  await apiFetch<void>(`/activities/visibility/${visibility}`, {
    method: 'PUT',
    responseType: 'void',
  })
}

/**
 * Applies a full edit to an activity via `PATCH /activities/{id}`. Empty
 * description / private notes are sent as `null` to clear them; the remaining
 * fields are sent so the partial update (backend `exclude_unset`) applies every
 * editable value, mirroring v1.
 *
 * @param id - Activity identifier.
 * @param input - The edited field values from the form.
 * @returns The updated activity domain model.
 * @throws {HttpError} When the update fails.
 */
export async function editActivity(id: number, input: ActivityEditInput): Promise<Activity> {
  const body: ActivityEditDto = {
    name: input.name,
    activity_type: input.activityType,
    description: input.description.trim() ? input.description : null,
    private_notes: input.privateNotes.trim() ? input.privateNotes : null,
    visibility: input.visibility,
    is_hidden: input.isHidden,
    hide_start_time: input.hideStartTime,
    hide_location: input.hideLocation,
    hide_map: input.hideMap,
    hide_hr: input.hideHr,
    hide_power: input.hidePower,
    hide_cadence: input.hideCadence,
    hide_elevation: input.hideElevation,
    hide_speed: input.hideSpeed,
    hide_pace: input.hidePace,
    hide_laps: input.hideLaps,
    hide_workout_sets_steps: input.hideWorkoutSetsSteps,
    hide_gear: input.hideGear,
  }
  const dto = await apiFetch<ActivityDto>(`/activities/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
  return mapActivity(dto)
}
