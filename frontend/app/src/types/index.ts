/**
 * Notification type for the notivue library.
 */
export type NotificationType = 'warning' | 'success' | 'error' | 'info'

/**
 * Bootstrap button style variant for action buttons.
 */
export type ActionButtonType = 'success' | 'danger' | 'warning' | 'primary'

/**
 * Error object structure for API errors.
 *
 * @property response - Optional response object from the API.
 * @property response.status - HTTP status code.
 * @property response.data - Response data payload.
 * @property message - Optional error message.
 * @property toString - Converts the error to a string representation.
 */
export interface ErrorWithResponse {
  response?: {
    status?: number
    data?: unknown
  }
  message?: string
  toString: () => string
}

/**
 * Configuration for handling route query parameters with notifications.
 *
 * @property type - The notification type to display.
 * @property key - The query parameter key name.
 */
export interface RouteQueryHandler {
  type: NotificationType
  key: string
}

/**
 * Map of query parameter names to their handler configurations.
 */
export interface RouteQueryHandlers {
  [key: string]: RouteQueryHandler
}

/**
 * Response structure from authentication endpoints.
 *
 * @property mfa_required - Whether MFA verification is required.
 * @property username - The authenticated username.
 * @property session_id - The session identifier token.
 * @property access_token - The JWT access token (OAuth 2.1).
 * @property csrf_token - The CSRF token for request validation (OAuth 2.1).
 * @property token_type - The token type (always "bearer").
 * @property expires_in - Token expiration timestamp.
 */
export interface LoginResponse {
  mfa_required?: boolean
  username?: string
  session_id: string
  access_token?: string
  csrf_token?: string
  token_type?: string
  expires_in?: number
}

/**
 * Response from SSO token exchange endpoint.
 *
 * @property session_id - The session identifier.
 * @property access_token - The JWT access token.
 * @property csrf_token - The CSRF token.
 * @property token_type - The token type (always "bearer").
 * @property expires_in - Token expiration timestamp.
 */
export interface TokenExchangeResponse {
  session_id: string
  access_token: string
  csrf_token: string
  token_type: string
  expires_in: number
}

/**
 * Configuration template for identity providers.
 *
 * @property name - The display name of the provider.
 * @property provider_type - The type of provider (OIDC, OAuth2, etc.).
 * @property issuer_url - The issuer URL for the identity provider.
 * @property scopes - The OAuth scopes requested.
 * @property icon - The icon identifier for the provider.
 * @property description - A description of the provider.
 * @property configuration_notes - Additional configuration notes.
 */
export interface IdentityProviderTemplate {
  name: string
  provider_type: string
  issuer_url: string
  scopes: string
  icon: string
  description: string
  configuration_notes: string
}

/**
 * Configured external identity provider for SSO authentication.
 *
 * @property id - Unique identifier for the provider.
 * @property name - The display name of the provider.
 * @property slug - URL-friendly identifier for the provider.
 * @property provider_type - The type of provider (OIDC, OAuth2, etc.).
 * @property icon - Optional icon identifier for the provider.
 * @property enabled - Whether the provider is currently enabled.
 * @property issuer_url - The issuer URL for the identity provider.
 * @property client_id - The OAuth client ID.
 * @property client_secret - The OAuth client secret (edit only).
 * @property scopes - The OAuth scopes requested (edit only).
 * @property auto_create_users - Whether to automatically create users (edit only).
 * @property sync_user_info - Whether to sync user information (edit only).
 * @property authorization_endpoint - The authorization endpoint URL (display only).
 * @property token_endpoint - The token endpoint URL (display only).
 * @property userinfo_endpoint - The userinfo endpoint URL (display only).
 */
export interface IdentityProvider {
  id: number
  name: string
  slug: string
  provider_type: string
  icon?: string
  enabled: boolean
  issuer_url?: string
  client_id?: string
  // Edit-specific fields
  client_secret?: string
  scopes?: string
  auto_create_users?: boolean
  sync_user_info?: boolean
  // Display-specific fields
  authorization_endpoint?: string
  token_endpoint?: string
  userinfo_endpoint?: string
}

/**
 * Public identity provider information for the login page.
 *
 * @property id - Unique identifier for the provider.
 * @property name - The display name of the provider.
 * @property slug - URL-friendly identifier for the provider.
 * @property icon - Optional icon identifier for the provider.
 */
export interface SSOProvider {
  id: number
  name: string
  slug: string
  icon?: string
}

/**
 * User's connection to an external identity provider (SSO).
 *
 * @property id - Unique identifier for the link.
 * @property user_id - The user's unique identifier.
 * @property idp_id - The identity provider's unique identifier.
 * @property idp_subject - The subject identifier from the identity provider.
 * @property linked_at - ISO 8601 datetime when the link was created.
 * @property last_login - ISO 8601 datetime of last login, or null if never logged in.
 * @property idp_access_token_expires_at - ISO 8601 datetime when the access token expires, or null.
 * @property idp_refresh_token_updated_at - ISO 8601 datetime when the refresh token was last updated, or null.
 *
 * @remarks
 * Refresh tokens are NOT included in this interface and are handled securely on the backend.
 */
export interface UsersIdentityProvider {
  id: number
  user_id: number
  idp_id: number
  idp_subject: string
  linked_at: string // ISO 8601 datetime string
  last_login: string | null
  idp_access_token_expires_at: string | null
  idp_refresh_token_updated_at: string | null
}

/**
 * Extended user identity provider with IDP details for display.
 *
 * @property idp_name - The name of the identity provider.
 * @property idp_slug - URL-friendly identifier for the identity provider.
 * @property idp_icon - Optional icon identifier for the identity provider.
 * @property idp_provider_type - The type of the identity provider.
 *
 * @remarks
 * The backend enriches responses with IDP information from the identity_providers table.
 * Used in UserIdentityProviderListComponent and UsersListComponent.
 */
export interface UserIdentityProviderEnriched extends UsersIdentityProvider {
  idp_name: string
  idp_slug: string
  idp_icon?: string
  idp_provider_type: string
}

/**
 * Activity data structure from the backend.
 *
 * @property activity_type - Numeric identifier for the activity type.
 * @property distance - Total distance in meters.
 */
export interface Activity {
  activity_type: number
  distance: number
}

/**
 * Single waypoint in an activity stream.
 *
 * @property hr - Heart rate value (as string).
 * @property power - Power value in watts (as string).
 * @property cad - Cadence value in RPM or stroke rate in SPM (as string).
 * @property ele - Elevation value in meters (as string).
 * @property vel - Velocity value in m/s.
 * @property pace - Pace value in seconds per meter, or null if unavailable.
 */
export interface StreamWaypoint {
  hr?: string
  power?: string
  cad?: string
  ele?: string
  vel?: number
  pace?: number | null
}

/**
 * Activity stream containing time-series data.
 *
 * @property stream_type - Numeric identifier for the stream type (1=HR, 2=Power, 3=Cadence, 4=Elevation, 5=Velocity, 6=Pace).
 * @property stream_waypoints - Array of waypoint data for this stream.
 */
export interface ActivityStream {
  stream_type: number
  stream_waypoints: StreamWaypoint[]
}

/**
 * Global Window interface extension for environment configuration.
 *
 * @property env - Environment configuration object.
 * @property env.ENDURAIN_HOST - The host URL for the Endurain API.
 */
declare global {
  interface Window {
    env: {
      ENDURAIN_HOST: string
    }
  }
}
