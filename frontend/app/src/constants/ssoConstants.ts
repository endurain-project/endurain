import keycloakLogo from '@/assets/sso/keycloak.svg'
import authentikLogo from '@/assets/sso/authentik.svg'
import autheliaLogo from '@/assets/sso/authelia.svg'

/**
 * Maps SSO provider names to their corresponding logo image paths.
 *
 * @remarks
 * Supported SSO providers:
 * - **keycloak**: Keycloak identity and access management
 * - **authentik**: Authentik authentication provider
 * - **authelia**: Authelia authentication and authorization server
 */
export const PROVIDER_CUSTOM_LOGO_MAP: Record<string, string> = {
  keycloak: keycloakLogo,
  authentik: authentikLogo,
  authelia: autheliaLogo
} as const
