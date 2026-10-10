import type { Schemas } from '@/types'

/** Raw `GearRead` payload as returned by the backend (snake_case wire shape). */
export type GearDto = Schemas['GearRead']

/** Raw `GearDetailRead` payload, a gear enriched with computed totals. */
export type GearDetailDto = Schemas['GearDetailRead']

/**
 * Supported gear-type code (1–8), derived from the backend's generated
 * `GearType` schema so a change to the supported set surfaces here as a type
 * error instead of a silent mismatch.
 */
export type GearType = Schemas['GearType']

/**
 * The clean gear model consumed across the UI: camelCased, with the backend's
 * nullable optional fields normalized so components never branch on
 * `undefined`. Mapped from {@link GearDto} at the service boundary.
 *
 * @property id - Stable unique identifier.
 * @property userId - Owning user id.
 * @property gearType - Numeric gear-type identifier (1–8).
 * @property nickname - Display nickname.
 * @property brand - Manufacturer brand, or `null`.
 * @property model - Model name, or `null`.
 * @property active - Whether the gear is in active use.
 * @property createdAt - Acquisition/creation date (ISO string), or `null`.
 * @property initialKms - Initial distance offset in kilometres, or `null`.
 * @property purchaseValue - Purchase price in the user's currency, or `null`.
 * @property stravaGearId - Linked Strava gear id, or `null`.
 * @property garminConnectGearId - Linked Garmin Connect gear id, or `null`.
 */
export interface Gear {
  id: number
  userId: number
  gearType: GearType
  nickname: string
  brand: string | null
  model: string | null
  active: boolean
  createdAt: string | null
  initialKms: number | null
  purchaseValue: number | null
  stravaGearId: string | null
  garminConnectGearId: string | null
}

/**
 * A gear enriched with the computed totals returned by the detail endpoint.
 *
 * @property totalDistance - Total activity distance in metres.
 * @property totalTime - Total activity time in seconds.
 * @property totalComponentsCost - Sum of component purchase values.
 */
export interface GearDetail extends Gear {
  totalDistance: number
  totalTime: number
  totalComponentsCost: number
}

/**
 * Fields captured by the add/edit form, decoupled from the wire payload. The
 * service maps this to the backend's `GearCreate`/`GearUpdate` at the boundary.
 * `initialKms` is already normalized to kilometres regardless of the user's
 * display units.
 */
export interface GearInput {
  nickname: string
  gearType: GearType
  brand: string | null
  model: string | null
  active: boolean
  createdAt: string | null
  initialKms: number | null
  purchaseValue: number | null
}

/** One page of the paginated gears list. */
export interface GearsPage {
  records: Gear[]
  total: number
}

/** Raw `GearComponentRead` payload as returned by the backend. */
export type GearComponentDto = Schemas['GearComponentRead']

/** The four component-type catalogues, keyed by gear family. */
export type GearComponentTypeLists = Schemas['GearComponentTypesRead']

/**
 * The clean gear-component model consumed across the UI, mapped from
 * {@link GearComponentDto} at the service boundary.
 *
 * @property id - Stable unique identifier.
 * @property userId - Owning user id.
 * @property gearId - Parent gear id.
 * @property type - Component type id (snake_case, e.g. `chain`).
 * @property brand - Manufacturer brand.
 * @property model - Model name.
 * @property purchaseDate - Purchase date (ISO string), or `null`.
 * @property retiredDate - Retirement date (ISO string), or `null`.
 * @property active - Whether the component is currently in use.
 * @property expectedBaseUnits - Backend `expected_kms`: the wear threshold in
 *   base units — **metres** for distance-tracked gears and **seconds** for the
 *   time-tracked racquet family — or `null` when no threshold is set.
 * @property purchaseValue - Purchase price in the user's currency, or `null`.
 * @property currentDistance - Accumulated activity distance in metres.
 * @property currentTime - Accumulated activity time in seconds.
 */
export interface GearComponent {
  id: number
  userId: number
  gearId: number
  type: string
  brand: string
  model: string
  purchaseDate: string | null
  retiredDate: string | null
  active: boolean
  expectedBaseUnits: number | null
  purchaseValue: number | null
  currentDistance: number
  currentTime: number
}

/**
 * Fields captured by the component add/edit form, decoupled from the wire
 * payload. `expectedBaseUnits` is already normalized to metres (distance gears)
 * or seconds (racquet) regardless of the user's display units.
 */
export interface GearComponentInput {
  gearId: number
  type: string
  brand: string
  model: string
  purchaseDate: string | null
  retiredDate: string | null
  active: boolean
  expectedBaseUnits: number | null
  purchaseValue: number | null
}

/** Raw `Activity` payload as returned by the gear-activities endpoint. */
export type GearActivityDto = Schemas['Activity']

/**
 * The trimmed activity model used by the gear-detail activities list — only the
 * fields the read-only list renders, mapped at the service boundary.
 *
 * @property id - Stable unique identifier.
 * @property name - Activity display name.
 * @property activityType - Numeric sport-type identifier.
 * @property startTime - Activity start as a UTC instant (ISO 8601), or `null`.
 * @property timezone - IANA timezone the activity was recorded in, used to
 *   render {@link GearActivity.startTime} in the athlete's local time.
 * @property distance - Activity distance in metres.
 * @property totalTimerTime - Moving time in seconds, or `null`.
 */
export interface GearActivity {
  id: number
  name: string
  activityType: number
  startTime: string | null
  timezone: string | null
  distance: number
  totalTimerTime: number | null
}

/** One page of the paginated activities-for-a-gear list. */
export interface GearActivitiesPage {
  records: GearActivity[]
  total: number
}
