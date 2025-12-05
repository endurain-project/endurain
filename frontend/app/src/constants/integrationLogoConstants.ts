import stravaLogo from '@/assets/strava/api_logo_cptblWith_strava_horiz_light.png'
import garminConnectBadge from '@/assets/garminconnect/Garmin_connect_badge_print_RESOURCE_FILE-01.png'
import garminConnectApp from '@/assets/garminconnect/Garmin_Connect_app_1024x1024-02.png'

/**
 * Logo and badge images for third-party fitness integrations.
 *
 * @remarks
 * Contains logos for:
 * - **strava**: Strava horizontal logo (compatible with light backgrounds)
 * - **garminConnectBadge**: Garmin Connect badge for print resources
 * - **garminConnectApp**: Garmin Connect app icon (1024x1024)
 */
export const INTEGRATION_LOGOS = {
  strava: stravaLogo,
  garminConnectBadge: garminConnectBadge,
  garminConnectApp: garminConnectApp
} as const
