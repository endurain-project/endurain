/**
 * Integration Logo Constants
 *
 * Centralized constants for third-party integration logos.
 * Maps integration services to their logo images.
 */

import stravaLogo from '@/assets/strava/api_logo_cptblWith_strava_horiz_light.png'
import garminConnectBadge from '@/assets/garminconnect/Garmin_connect_badge_print_RESOURCE_FILE-01.png'
import garminConnectApp from '@/assets/garminconnect/Garmin_Connect_app_1024x1024-02.png'

/**
 * Integration logo mapping
 */
export const INTEGRATION_LOGOS = {
    strava: stravaLogo,
    garminConnectBadge: garminConnectBadge,
    garminConnectApp: garminConnectApp
} as const
