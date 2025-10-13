/**
 * Common type definitions for the Endurain application
 *
 * This file serves as a starting point for TypeScript type definitions.
 * As you migrate JavaScript code to TypeScript, add relevant types here.
 */

/**
 * Notification Types
 * Used by the notivue library for displaying different types of notifications
 */
export type NotificationType = 'warning' | 'success' | 'error' | 'info'

/**
 * Action Button Types
 * Bootstrap button style variants for action buttons in modals and forms
 */
export type ActionButtonType = 'success' | 'danger' | 'warning' | 'primary'

/**
 * Error object with optional response property
 * Common structure for API errors
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
 * Route Query Handler
 * Configuration for handling route query parameters with notifications
 */
export interface RouteQueryHandler {
  type: NotificationType
  key: string
}

/**
 * Route Query Handlers Map
 * Map of query parameter names to their handler configurations
 */
export interface RouteQueryHandlers {
  [key: string]: RouteQueryHandler
}

/**
 * Login Response
 * Response structure from authentication endpoints
 */
export interface LoginResponse {
  mfa_required?: boolean
  username?: string
  session_id: string
}

/**
 * Identity Provider Template
 * Configuration template for identity providers (OIDC, OAuth2, etc.)
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
 * Window Environment Extension
 * Extends the global Window interface to include custom env property
 */
declare global {
  interface Window {
    env: {
      ENDURAIN_HOST: string
    }
  }
}
