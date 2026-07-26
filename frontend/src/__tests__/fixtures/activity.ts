import type { Activity, ActivityPrivacy } from '@/features/activities/types'

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
    id: 1,
    userId: 7,
    name: 'Morning run',
    description: null,
    privateNotes: null,
    activityType: 1,
    visibility: 0,
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
    mapThumbnailPath: null,
    ...overrides,
    privacy: { ...NO_PRIVACY, ...overrides.privacy },
  }
}
