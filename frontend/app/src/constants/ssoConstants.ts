/**
 * SSO Constants
 *
 * Centralized constants for Single Sign-On (SSO) functionality
 * including provider logos and configuration mappings.
 */

import keycloakLogo from '@/assets/sso/keycloak.svg'
import authentikLogo from '@/assets/sso/authentik.svg'
import autheliaLogo from '@/assets/sso/authelia.svg'

/**
 * Custom logo mapping for SSO providers
 * Maps provider icon names to image paths for custom logos
 */
export const PROVIDER_CUSTOM_LOGO_MAP: Record<string, string> = {
  keycloak: keycloakLogo,
  authentik: authentikLogo,
  authelia: autheliaLogo
} as const
