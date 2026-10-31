import type {
  Goal,
  GoalCreateDto,
  GoalDto,
  GoalFilters,
  GoalInput,
  GoalProgress,
  GoalProgressDto,
  GoalUpdateDto,
} from '@/features/goals/types'

import { apiFetch } from '@/services/http'
import { ifMatchHeaders, rowVersion } from '@/services/ifMatch'
import { fetchAllPages } from '@/services/pagination'

/**
 * Maps a raw goal payload to the clean {@link Goal} model — the single boundary
 * where the backend wire format (snake_case) is normalized so components never
 * see the raw DTO. Absent optional targets collapse to `null`.
 *
 * @param dto - Raw goal payload from the backend.
 * @returns The normalized goal model.
 */
export function mapGoal(dto: GoalDto): Goal {
  return {
    id: dto.id,
    userId: dto.user_id,
    version: rowVersion(dto.version),
    interval: dto.interval,
    activityType: dto.activity_type,
    goalType: dto.goal_type,
    calories: dto.goal_calories ?? null,
    activitiesNumber: dto.goal_activities_number ?? null,
    distanceMeters: dto.goal_distance ?? null,
    elevationMeters: dto.goal_elevation ?? null,
    durationSeconds: dto.goal_duration ?? null,
  }
}

/**
 * Maps a raw goal-progress payload to the clean {@link GoalProgress} model,
 * collapsing the achieved/target pair for the goal's metric into `total` /
 * `target`. The backend emits a full set of `total_*` / `goal_*` fields; only
 * the pair matching `goal_type` is meaningful, so this selects it.
 *
 * @param dto - Raw goal-progress payload from the backend.
 * @returns The normalized goal-progress model.
 */
export function mapGoalProgress(dto: GoalProgressDto): GoalProgress {
  const byMetric: Record<GoalProgress['goalType'], { total: number; target: number | null }> = {
    calories: { total: dto.total_calories ?? 0, target: dto.goal_calories ?? null },
    activities: {
      total: dto.total_activities_number ?? 0,
      target: dto.goal_activities_number ?? null,
    },
    distance: { total: dto.total_distance ?? 0, target: dto.goal_distance ?? null },
    elevation: { total: dto.total_elevation ?? 0, target: dto.goal_elevation ?? null },
    duration: { total: dto.total_duration ?? 0, target: dto.goal_duration ?? null },
  }
  const selected = byMetric[dto.goal_type]
  return {
    goalId: dto.goal_id,
    interval: dto.interval,
    activityType: dto.activity_type,
    goalType: dto.goal_type,
    percentageCompleted: dto.percentage_completed ?? 0,
    total: selected.total,
    target: selected.target,
  }
}

/**
 * Fetches the authenticated user's goal progress for the current interval of
 * each goal, powering the home dashboard's goal-results panel.
 *
 * @param signal - Optional abort signal for cancellation.
 * @returns The per-goal progress, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function fetchGoalResults(signal?: AbortSignal): Promise<GoalProgress[]> {
  const dtos = await fetchAllPages<GoalProgressDto>('/profile/goals/results', undefined, signal)
  return dtos.map(mapGoalProgress)
}

/**
 * Builds the snake-cased target fields from a {@link GoalInput}. Every target
 * key is emitted (with `null` for the metrics that don't apply) so the backend
 * sees exactly one non-null value matching `goal_type`, as it requires.
 *
 * @param input - The clean goal input from the form.
 * @returns The snake-cased fields common to create and update.
 */
function toWire(input: GoalInput) {
  return {
    interval: input.interval,
    activity_type: input.activityType,
    goal_type: input.goalType,
    goal_calories: input.calories,
    goal_activities_number: input.activitiesNumber,
    goal_distance: input.distanceMeters,
    goal_elevation: input.elevationMeters,
    goal_duration: input.durationSeconds,
  }
}

/**
 * Fetches the authenticated user's goals, optionally narrowed by the same
 * interval / activity-type / goal-type filters the backend's list endpoint
 * accepts. Unset (`null`) filters are omitted from the query string.
 *
 * @param filters - The active goal filters; defaults to no filtering.
 * @param signal - Optional abort signal for cancellation.
 * @returns The goals, mapped to the clean model.
 * @throws {HttpError} When the request fails.
 */
export async function fetchGoals(
  filters: GoalFilters = { interval: null, activityType: null, goalType: null },
  signal?: AbortSignal,
): Promise<Goal[]> {
  const params = new URLSearchParams()
  if (filters.interval) {
    params.set('interval', filters.interval)
  }
  if (filters.activityType) {
    params.set('activity_type', filters.activityType)
  }
  if (filters.goalType) {
    params.set('goal_type', filters.goalType)
  }
  const dtos = await fetchAllPages<GoalDto>('/profile/goals', params, signal)
  return dtos.map(mapGoal)
}

/**
 * Creates a goal for the authenticated user.
 *
 * @param input - The clean goal input.
 * @returns The created goal, mapped to the clean model.
 * @throws {HttpError} When the request fails (e.g. a missing target value).
 */
export async function createGoal(input: GoalInput): Promise<Goal> {
  const payload: GoalCreateDto = toWire(input)
  const dto = await apiFetch<GoalDto>('/profile/goals', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return mapGoal(dto)
}

/**
 * Updates a goal for the authenticated user. The goal is named by the path and the body is
 * the whole goal.
 *
 * @param id - The goal id.
 * @param input - The clean goal input.
 * @param version - The goal version the form was loaded at, for `If-Match`.
 * @returns The updated goal, mapped to the clean model.
 * @throws {HttpError} When the request fails, including 412 when stale.
 */
export async function updateGoal(id: number, input: GoalInput, version: number): Promise<Goal> {
  const payload: GoalUpdateDto = toWire(input)
  const dto = await apiFetch<GoalDto>(`/profile/goals/${id}`, {
    method: 'PUT',
    headers: ifMatchHeaders(version),
    body: JSON.stringify(payload),
  })
  return mapGoal(dto)
}

/**
 * Deletes a goal for the authenticated user.
 *
 * @param id - The goal id.
 * @param version - The goal version the list item was read at, for `If-Match`.
 * @throws {HttpError} When the request fails (`412` when the goal changed since it was read).
 */
export async function deleteGoal(id: number, version: number): Promise<void> {
  await apiFetch(`/profile/goals/${id}`, {
    method: 'DELETE',
    headers: ifMatchHeaders(version),
    responseType: 'void',
  })
}
