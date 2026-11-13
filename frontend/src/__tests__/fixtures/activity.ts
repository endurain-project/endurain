import type { Activity, ActivityPrivacy, ActivitySummary } from '@/features/activities/types'

/** Builds a stable activity-scoped UUID from a small number so ids stay readable in assertions. */
export function activityUuid(n: number): string {
  return `00000000-0000-4000-8000-${String(n).padStart(12, '0')}`
}

/** Builds a stable user-scoped UUID from a small number so ids stay readable in assertions. */
export function userUuid(n: number): string {
  return `00000000-0000-4000-9000-${String(n).padStart(12, '0')}`
}

/** All-false privacy flags (nothing hidden). */
export const NO_PRIVACY: ActivityPrivacy = {
  hideStartTime: false,
  hideLocation: false,
  hideMap: false,
  hideHr: false,
  hidePower: false,
  hideCadence: false,
  hideElevation: false,
  hideSpeed: false,
  hidePace: false,
  hideLaps: false,
  hideWorkoutSetsSteps: false,
  hideGear: false,
}

/**
 * Builds an activity domain fixture with overridable fields for tests.
 *
 * @param overrides - Fields to override on the default running activity.
 * @returns A complete {@link Activity}.
 */
export function makeActivity(overrides: Partial<Activity> = {}): Activity {
  return {
    id: activityUuid(1),
    userId: userUuid(7),
    version: 1,
    name: 'Morning run',
    description: null,
    privateNotes: null,
    activityType: 'run',
    visibility: 'public',
    isHidden: false,
    gearId: null,
    startTime: '2024-05-01T07:00:00Z',
    timezone: 'Europe/Lisbon',
    city: 'Lisbon',
    town: null,
    country: 'Portugal',
    distance: 10000,
    pace: 0.3,
    averageSpeed: null,
    maxSpeed: null,
    averageHr: 150,
    maxHr: 175,
    averagePower: null,
    maxPower: null,
    normalizedPower: null,
    averageCadence: 85,
    maxCadence: 95,
    elevationGain: 120,
    elevationLoss: 110,
    totalElapsedTime: 3600,
    totalTimerTime: 3500,
    calories: 600,
    totalCycles: null,
    stravaActivityId: null,
    garminActivityId: null,
    mapThumbnailUrl: null,
    media: [],
    ...overrides,
    privacy: { ...NO_PRIVACY, ...overrides.privacy },
  }
}

/**
 * Builds an activity summary fixture, the shape every list response returns: a full activity
 * without the private notes.
 *
 * @param overrides - Fields to override on the default running activity.
 * @returns A complete {@link ActivitySummary}.
 */
export function makeActivitySummary(overrides: Partial<ActivitySummary> = {}): ActivitySummary {
  const { privateNotes: _privateNotes, ...summary } = makeActivity(overrides)
  return summary
}
