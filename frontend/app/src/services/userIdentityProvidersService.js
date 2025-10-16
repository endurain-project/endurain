/**
 * User Identity Providers Service
 *
 * Handles API communication for user-specific identity provider links.
 * These endpoints are used by administrators to view and manage which external
 * authentication providers (SSO) are linked to user accounts.
 *
 * Security:
 *   - Admin-only operations (backend enforces sessions:read, sessions:write scopes)
 *   - Does not expose refresh tokens (backend security)
 *   - All operations require valid JWT authentication
 *
 * Related Files:
 *   - Backend Router: backend/app/users/user_identity_providers/router.py
 *   - TypeScript Types: frontend/app/src/types/index.ts (UserIdentityProviderEnriched)
 *   - Usage: UsersListComponent.vue (admin panel)
 */

import { fetchGetRequest, fetchDeleteRequest } from '@/utils/serviceUtils'

export const userIdentityProviders = {
  /**
   * Get all identity provider links for a specific user
   *
   * Retrieves the list of external authentication providers (SSO) that are
   * linked to the user's account. The response includes IDP metadata such as
   * provider name, icon, and login history.
   *
   * Security:
   *   - Admin-only endpoint (sessions:read scope)
   *   - Refresh tokens are NOT included in response
   *   - Only metadata is exposed
   *
   * @param {number} userId - Target user ID
   * @returns {Promise<UserIdentityProviderEnriched[]>} Array of IDP links with enriched details
   *
   * @example
   * const idps = await userIdentityProviders.getUserIdentityProviders(123)
   * console.log(idps) // [{ id: 1, idp_name: "Google", ... }]
   *
   * @throws {Error} 404 if user not found
   * @throws {Error} 403 if insufficient permissions (non-admin)
   * @throws {Error} 401 if not authenticated
   */
  getUserIdentityProviders(userId) {
    return fetchGetRequest(`users/${userId}/identity-providers`)
  },

  /**
   * Delete a user's identity provider link
   *
   * Removes the connection between a user and an external authentication provider.
   * After deletion, the user will no longer be able to log in using this provider,
   * but can still use their password (if set) or other linked providers.
   *
   * Security:
   *   - Admin-only endpoint (sessions:write scope)
   *   - Audit logging performed on backend
   *   - Clears encrypted refresh tokens before deletion
   *
   * Side Effects:
   *   - Deletes user_identity_provider record from database
   *   - Clears stored refresh tokens (defense in depth)
   *   - Creates audit log entry on backend
   *
   * @param {number} userId - Target user ID whose IDP link will be deleted
   * @param {number} idpId - Identity provider ID to unlink from the user
   * @returns {Promise<void>} Promise that resolves when deletion is complete (204 No Content)
   *
   * @example
   * await userIdentityProviders.deleteUserIdentityProvider(123, 5)
   * // IDP link deleted, user can no longer log in with that provider
   *
   * @throws {Error} 404 if user, IDP, or link not found
   * @throws {Error} 403 if insufficient permissions (non-admin)
   * @throws {Error} 401 if not authenticated
   */
  deleteUserIdentityProvider(userId, idpId) {
    return fetchDeleteRequest(`users/${userId}/identity-providers/${idpId}`)
  }
}
