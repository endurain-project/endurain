/**
 * SSO Constants
 *
 * Centralized constants for Single Sign-On (SSO) functionality
 * including provider logos and configuration mappings.
 */

/**
 * Custom logo mapping for SSO providers
 * Maps provider icon names to image paths for custom logos
 */
export const PROVIDER_CUSTOM_LOGO_MAP: Record<string, string> = {
  keycloak: '/src/assets/sso/keycloak.svg',
  authentik: '/src/assets/sso/authentik.svg',
  authelia: '/src/assets/sso/authelia.svg'
} as const
