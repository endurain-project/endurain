import type { Schemas } from '@/types'

/** Strava client-credentials body (snake_case wire shape). */
export type StravaClientDto = Schemas['StravaClientCredentials']

/** Strava authorization-code callback body (snake_case wire shape). */
export type StravaLinkDto = Schemas['StravaLinkRequest']
export type StravaStateDto = Schemas['StravaState']

/** Where a queued Strava gear sync or unlink is, as the status endpoint reports it. */
export type StravaSyncStatus = Schemas['StravaSyncStatus']

/** Garmin Connect login body. */
export type GarminLoginDto = Schemas['GarminLogin']

/** Garmin Connect MFA-code body. */
export type GarminMfaDto = Schemas['modules__garmin__schema__MFARequest']

/** Where a Garmin Connect link attempt is, as the status endpoint reports it. */
export type GarminLinkStatus = Schemas['GarminLinkStatus']

/** The clean credentials the Strava connect dialog collects. */
export interface StravaClientInput {
  clientId: number
  clientSecret: string
}

/** The clean credentials the Garmin Connect login dialog collects. */
export interface GarminLoginInput {
  username: string
  password: string
  /** Whether to authenticate against Garmin's China region (connect.garmin.cn). */
  isCn: boolean
}

/** An inclusive start/end date window, each formatted `YYYY-MM-DD`. */
export interface DateRange {
  startDate: string
  endDate: string
}
