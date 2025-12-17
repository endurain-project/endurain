import autheliaLogo from '@/assets/sso/authelia.svg'
import authentikLogo from '@/assets/sso/authentik.svg'
import casdoorLogo from '@/assets/sso/casdoor.svg'
import keycloakLogo from '@/assets/sso/keycloak.svg'
import pocketidLogo from '@/assets/sso/pocketid.svg'

/**
 * Maps SSO provider names to their corresponding logo image paths.
 *
 * @remarks
 * Supported SSO providers:
 * - **authelia**: Authelia authentication and authorization server
 * - **authentik**: Authentik authentication provider
 * - **casdoor**: Casdoor identity and access management
 * - **keycloak**: Keycloak identity and access management
 */
export const PROVIDER_CUSTOM_LOGO_MAP: Record<string, string> = {
  authelia: autheliaLogo,
  authentik: authentikLogo,
  casdoor: casdoorLogo,
  keycloak: keycloakLogo,
  pocketid: pocketidLogo
} as const
